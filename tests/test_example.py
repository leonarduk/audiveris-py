from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from test_core import make_fake_audiveris

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "pdf_to_musicxml.py"


def run_example(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "AUDIVERIS_BIN": str(make_fake_audiveris(tmp_path))}
    return subprocess.run(
        [sys.executable, str(EXAMPLE), *args], env=env, capture_output=True, text=True, check=False
    )


def test_example_converts_a_folder(tmp_path):
    scores = tmp_path / "scores"
    scores.mkdir()
    for name in ("a", "b"):
        (scores / f"{name}.pdf").write_bytes(b"%PDF fake")
    out = tmp_path / "out"

    proc = run_example(tmp_path, str(scores), "-o", str(out))

    assert proc.returncode == 0, proc.stderr
    for name in ("a", "b"):
        assert (out / name / f"{name}.mxl").is_file()
        assert "<score-partwise" in (out / name / f"{name}.musicxml").read_text(encoding="utf-8")


def test_example_reports_missing_file(tmp_path):
    proc = run_example(tmp_path, str(tmp_path / "nope.pdf"))
    assert proc.returncode == 1
    assert "file not found" in proc.stderr
