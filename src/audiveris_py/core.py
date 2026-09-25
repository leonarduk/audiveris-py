from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Sequence
from xml.etree import ElementTree

EXPORT_SUFFIXES = (".mxl", ".xml")
ENV_VAR = "AUDIVERIS_BIN"

# Exit status bits set by org.audiveris.omr.Main in batch mode.
_EXIT_FAILURE = 1
_EXIT_TIMEOUT = 2


class AudiverisError(RuntimeError):
    def __init__(self, message: str, returncode: int | None = None, output: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.output = output


def find_audiveris(explicit: str | os.PathLike[str] | None = None) -> str:
    candidates = [explicit, os.environ.get(ENV_VAR)]
    for candidate in candidates:
        if candidate:
            resolved = shutil.which(str(candidate))
            if resolved:
                return resolved
            raise AudiverisError(f"Audiveris executable not found or not executable: {candidate}")
    for name in ("audiveris", "Audiveris"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise AudiverisError(
        f"Audiveris executable not found on PATH; install Audiveris or set {ENV_VAR}"
    )


def _snapshot(folder: Path) -> dict[Path, int]:
    if not folder.exists():
        return {}
    return {
        p: p.stat().st_mtime_ns
        for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in EXPORT_SUFFIXES
    }


def _describe_exit(returncode: int) -> str:
    reasons = []
    if returncode & _EXIT_FAILURE:
        reasons.append("failure")
    if returncode & _EXIT_TIMEOUT:
        reasons.append("timeout")
    return " + ".join(reasons) or "unknown error"


def _tail(text: str, lines: int = 40) -> str:
    return "\n".join(text.splitlines()[-lines:])


def convert(
    inputs: str | os.PathLike[str] | Sequence[str | os.PathLike[str]],
    output_dir: str | os.PathLike[str],
    *,
    audiveris: str | os.PathLike[str] | None = None,
    sheets: Sequence[int] | None = None,
    extra_args: Sequence[str] = (),
    timeout: float | None = None,
) -> list[Path]:
    """Run Audiveris in batch mode and return the MusicXML files written by this run."""
    if isinstance(inputs, (str, os.PathLike)):
        inputs = [inputs]
    input_paths = [Path(p) for p in inputs]
    if not input_paths:
        raise ValueError("No input files given")
    for path in input_paths:
        if not path.is_file():
            raise FileNotFoundError(path)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    cmd = [find_audiveris(audiveris), "-batch", "-export", "-output", str(out)]
    if sheets:
        cmd += ["-sheets", *(str(s) for s in sheets)]
    cmd += [*extra_args, "--", *(str(p) for p in input_paths)]

    before = _snapshot(out)
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as ex:
        output = ex.output if isinstance(ex.output, str) else ""
        raise AudiverisError(f"Audiveris timed out after {timeout}s", None, output) from ex

    if proc.returncode != 0:
        raise AudiverisError(
            f"Audiveris exited with status {proc.returncode} ({_describe_exit(proc.returncode)})\n"
            f"{_tail(proc.stdout)}",
            proc.returncode,
            proc.stdout,
        )

    produced = sorted(p for p, mtime in _snapshot(out).items() if before.get(p) != mtime)
    if not produced:
        raise AudiverisError(
            f"Audiveris finished but exported no MusicXML\n{_tail(proc.stdout)}",
            proc.returncode,
            proc.stdout,
        )
    return produced


def read_musicxml(path: str | os.PathLike[str]) -> str:
    """Return the MusicXML document text from a .mxl container or a plain .xml file."""
    path = Path(path)
    if not zipfile.is_zipfile(path):
        return path.read_text(encoding="utf-8")

    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        root_name = None
        if "META-INF/container.xml" in names:
            container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
            rootfile = next((el for el in container.iter() if el.tag.endswith("rootfile")), None)
            if rootfile is not None:
                root_name = rootfile.get("full-path")
        if root_name is None:
            root_name = next(
                (n for n in names if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF/")),
                None,
            )
        if root_name is None:
            raise AudiverisError(f"No MusicXML document found inside {path}")
        return archive.read(root_name).decode("utf-8")
