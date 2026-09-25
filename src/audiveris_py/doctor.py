from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from . import core
from .core import ENV_VAR, AudiverisError, find_audiveris

OK, WARN, FAIL = "ok", "warn", "fail"

RELEASES_URL = "https://github.com/Audiveris/audiveris/releases"
TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata"
_VERSION_RE = re.compile(r"^\s*-\s*Version:\s*(\S+)", re.MULTILINE)


@dataclass
class Check:
    name: str
    status: str
    detail: str
    hint: str = ""


def audiveris_config_dir(
    platform: str = sys.platform, env: Mapping[str, str] = os.environ
) -> Path | None:
    """Mirror org.audiveris.omr.WellKnowns CONFIG_FOLDER resolution."""
    if platform.startswith("win"):
        appdata = env.get("APPDATA")
        return Path(appdata, "AudiverisLtd", "audiveris", "config") if appdata else None
    home = env.get("HOME")
    if platform == "darwin":
        return Path(home, "Library", "Application Support", "AudiverisLtd", "audiveris") if home else None
    xdg = env.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg, "AudiverisLtd", "audiveris")
    return Path(home, ".config", "AudiverisLtd", "audiveris") if home else None


def tessdata_dir(platform: str = sys.platform, env: Mapping[str, str] = os.environ) -> Path | None:
    """Mirror TesseractOCR.findOcrFolder: TESSDATA_PREFIX if it is a directory, else config/tessdata."""
    prefix = env.get("TESSDATA_PREFIX")
    if prefix and Path(prefix).is_dir():
        return Path(prefix)
    config = audiveris_config_dir(platform, env)
    return config / "tessdata" if config else None


def check_executable(audiveris: str | os.PathLike[str] | None) -> tuple[Check, str | None]:
    try:
        exe = find_audiveris(audiveris)
    except AudiverisError as ex:
        hint = f"Install Audiveris from {RELEASES_URL}, or set {ENV_VAR} to its launcher."
        if audiveris or os.environ.get(ENV_VAR):
            detail = str(ex)
        else:
            places = ", ".join(str(p) for p in core.default_install_locations())
            detail = f"not found on PATH ('audiveris'/'Audiveris') or at {places or 'no default location'}"
        return Check("Audiveris executable", FAIL, detail, hint), None
    return Check("Audiveris executable", OK, exe), exe


def check_runs(exe: str, timeout: float) -> Check:
    name = "Audiveris starts"
    try:
        proc = subprocess.run(
            [exe, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Check(name, FAIL, f"no response to -version within {timeout:g}s")
    except OSError as ex:
        return Check(name, FAIL, str(ex), "Check the launcher is a working Audiveris install.")

    if proc.returncode != 0:
        last = proc.stdout.strip().splitlines()[-1:] or ["no output"]
        return Check(
            name,
            FAIL,
            f"-version exited with status {proc.returncode}: {last[0]}",
            "Audiveris needs a working Java runtime; the official installers bundle one.",
        )
    match = _VERSION_RE.search(proc.stdout)
    if not match:
        return Check(name, WARN, "ran, but printed no version line")
    return Check(name, OK, f"version {match.group(1)}")


def check_tessdata(platform: str = sys.platform, env: Mapping[str, str] = os.environ) -> Check:
    name = "OCR language data"
    folder = tessdata_dir(platform, env)
    if folder is None:
        return Check(name, WARN, "could not work out the Audiveris config folder",
                     "Set TESSDATA_PREFIX to a folder containing *.traineddata files.")
    languages = sorted(p.stem for p in folder.glob("*.traineddata")) if folder.is_dir() else []
    if not languages:
        return Check(
            name,
            WARN,
            f"no *.traineddata in {folder}; lyrics and other text will not be recognised",
            f"Download e.g. eng.traineddata from {TESSDATA_URL} into {folder}.",
        )
    return Check(name, OK, f"{', '.join(languages)} in {folder}")


def run_checks(audiveris: str | os.PathLike[str] | None = None, timeout: float = 120) -> list[Check]:
    exe_check, exe = check_executable(audiveris)
    checks = [exe_check]
    if exe:
        checks.append(check_runs(exe, timeout))
    checks.append(check_tessdata())
    return checks


def format_report(checks: list[Check]) -> str:
    labels = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}
    lines = []
    for check in checks:
        lines.append(f"{labels[check.status]} {check.name}: {check.detail}")
        if check.hint and check.status != OK:
            lines.append(f"       -> {check.hint}")
    return "\n".join(lines)
