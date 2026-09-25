from __future__ import annotations

import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

from test_core import CONTAINER, MUSICXML, make_fake_audiveris

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "pdf_to_musicxml.py"


def make_selective_audiveris(tmp_path: Path) -> Path:
    """Fake Audiveris that exports every input except ones named bad.pdf, and exits 1 if any were bad."""
    script = tmp_path / "selective-audiveris"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import sys, zipfile
            from pathlib import Path
            args = sys.argv[1:]
            out = Path(args[args.index("-output") + 1])
            failed = False
            for f in args[args.index("--") + 1:]:
                radix = Path(f).stem
                if radix == "bad":
                    print("ERROR cannot read", f)
                    failed = True
                    continue
                (out / radix).mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(out / radix / (radix + ".mxl"), "w") as z:
                    z.writestr("META-INF/container.xml", {CONTAINER!r}.format(name=radix + ".xml"))
                    z.writestr(radix + ".xml", {MUSICXML!r})
            sys.exit(1 if failed else 0)
            """
        )
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def run_example(tmp_path: Path, *args: str, audiveris: Path | None = None) -> subprocess.CompletedProcess[str]:
    exe = audiveris or make_fake_audiveris(tmp_path)
    env = {**os.environ, "AUDIVERIS_BIN": str(exe)}
    return subprocess.run(
        [sys.executable, str(EXAMPLE), *args], env=env, capture_output=True, text=True, check=False
    )


def make_pdfs(folder: Path, *names: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"%PDF fake")


def test_example_converts_a_folder(tmp_path):
    scores = tmp_path / "scores"
    make_pdfs(scores, "a.pdf", "B.PDF", "notes.txt")
    out = tmp_path / "out"

    proc = run_example(tmp_path, str(scores), "-o", str(out))

    assert proc.returncode == 0, proc.stderr
    for radix in ("a", "B"):
        assert (out / radix / f"{radix}.mxl").is_file()
        assert "<score-partwise" in (out / radix / f"{radix}.musicxml").read_text(encoding="utf-8")
    assert not (out / "notes").exists()


def test_example_converts_a_single_pdf(tmp_path):
    make_pdfs(tmp_path, "solo.pdf")
    out = tmp_path / "out"

    proc = run_example(tmp_path, str(tmp_path / "solo.pdf"), "-o", str(out))

    assert proc.returncode == 0, proc.stderr
    assert (out / "solo" / "solo.mxl").is_file()
    assert (out / "solo" / "solo.musicxml").is_file()


def test_example_continues_past_a_bad_scan(tmp_path):
    scores = tmp_path / "scores"
    make_pdfs(scores, "a.pdf", "bad.pdf", "c.pdf")
    out = tmp_path / "out"

    proc = run_example(tmp_path, str(scores), "-o", str(out), audiveris=make_selective_audiveris(tmp_path))

    assert proc.returncode == 1
    assert "bad.pdf: FAILED: Audiveris exited with status 1" in proc.stderr
    assert (out / "a" / "a.musicxml").is_file()
    assert (out / "c" / "c.musicxml").is_file()


def test_example_reports_missing_file(tmp_path):
    proc = run_example(tmp_path, str(tmp_path / "nope.pdf"))
    assert proc.returncode == 1
    assert "file not found" in proc.stderr
