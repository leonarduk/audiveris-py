from __future__ import annotations

import os
import stat
import sys
import textwrap
import zipfile
from pathlib import Path

import pytest

from audiveris_py import AudiverisError, convert, find_audiveris, read_musicxml
from audiveris_py.__main__ import main

MUSICXML = '<?xml version="1.0"?><score-partwise version="4.0"><part-list/></score-partwise>'
CONTAINER = (
    '<?xml version="1.0"?><container><rootfiles>'
    '<rootfile full-path="{name}"/></rootfiles></container>'
)
SAMPLE_IMAGE = Path(__file__).resolve().parent / "data" / "chula.png"


def write_mxl(path: Path, inner: str = "score.xml") -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("META-INF/container.xml", CONTAINER.format(name=inner))
        z.writestr(inner, MUSICXML)


def make_fake_audiveris(tmp_path: Path, exit_code: int = 0, export: bool = True) -> Path:
    """Mimic Audiveris batch export: write <output>/<radix>/<radix>.mxl per input."""
    script = tmp_path / "fake-audiveris"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import sys, zipfile
            from pathlib import Path
            args = sys.argv[1:]
            Path(sys.argv[0] + ".args").write_text("\\n".join(args))
            out = Path(args[args.index("-output") + 1])
            for f in args[args.index("--") + 1:]:
                radix = Path(f).stem
                if {export!r}:
                    (out / radix).mkdir(parents=True, exist_ok=True)
                    with zipfile.ZipFile(out / radix / (radix + ".mxl"), "w") as z:
                        z.writestr("META-INF/container.xml", {CONTAINER!r}.format(name=radix + ".xml"))
                        z.writestr(radix + ".xml", {MUSICXML!r})
            print("INFO  processed", len(args))
            sys.exit({exit_code})
            """
        )
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


@pytest.fixture
def score(tmp_path: Path) -> Path:
    path = tmp_path / "sonata.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    return path


def test_convert_returns_exported_files_and_passes_expected_args(tmp_path, score):
    fake = make_fake_audiveris(tmp_path)
    out = tmp_path / "out"

    produced = convert(score, out, audiveris=fake, sheets=[1, 3])

    assert produced == [out / "sonata" / "sonata.mxl"]
    args = Path(str(fake) + ".args").read_text().splitlines()
    assert args == ["-batch", "-export", "-output", str(out), "-sheets", "1", "3", "--", str(score)]


def test_convert_ignores_files_from_previous_runs(tmp_path, score):
    out = tmp_path / "out"
    stale = out / "old" / "old.mxl"
    stale.parent.mkdir(parents=True)
    write_mxl(stale)

    produced = convert(score, out, audiveris=make_fake_audiveris(tmp_path))

    assert stale not in produced
    assert produced == [out / "sonata" / "sonata.mxl"]


@pytest.mark.parametrize("code,reason", [(1, "failure"), (2, "timeout"), (3, "failure + timeout")])
def test_convert_raises_on_nonzero_exit(tmp_path, score, code, reason):
    with pytest.raises(AudiverisError) as info:
        convert(score, tmp_path / "out", audiveris=make_fake_audiveris(tmp_path, exit_code=code))
    assert info.value.returncode == code
    assert reason in str(info.value)
    assert "processed" in info.value.output


def test_convert_raises_when_nothing_exported(tmp_path, score):
    with pytest.raises(AudiverisError, match="exported no MusicXML"):
        convert(score, tmp_path / "out", audiveris=make_fake_audiveris(tmp_path, export=False))


def test_convert_rejects_missing_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        convert(tmp_path / "missing.pdf", tmp_path / "out", audiveris=make_fake_audiveris(tmp_path))


def test_find_audiveris_uses_env_var(tmp_path, monkeypatch):
    fake = make_fake_audiveris(tmp_path)
    monkeypatch.setenv("AUDIVERIS_BIN", str(fake))
    assert find_audiveris() == str(fake)


def test_find_audiveris_reports_bad_explicit_path(tmp_path):
    with pytest.raises(AudiverisError, match="not found"):
        find_audiveris(tmp_path / "nope")


def test_read_musicxml_uses_container_rootfile(tmp_path):
    mxl = tmp_path / "a.mxl"
    write_mxl(mxl, inner="nested/real.musicxml")
    assert read_musicxml(mxl) == MUSICXML


def test_read_musicxml_plain_file(tmp_path):
    xml = tmp_path / "a.xml"
    xml.write_text(MUSICXML, encoding="utf-8")
    assert read_musicxml(xml) == MUSICXML


def test_cli_writes_uncompressed_copy(tmp_path, score, capsys):
    out = tmp_path / "out"
    rc = main([str(score), "-o", str(out), "--audiveris", str(make_fake_audiveris(tmp_path)), "--uncompressed"])

    assert rc == 0
    assert (out / "sonata" / "sonata.musicxml").read_text(encoding="utf-8") == MUSICXML
    assert "sonata.mxl" in capsys.readouterr().out


def test_cli_returns_error_code_on_failure(tmp_path, score, capsys):
    rc = main([str(score), "-o", str(tmp_path / "out"), "--audiveris", str(make_fake_audiveris(tmp_path, exit_code=1))])
    assert rc == 1
    assert "status 1" in capsys.readouterr().err


@pytest.mark.skipif(not os.environ.get("AUDIVERIS_BIN"), reason="set AUDIVERIS_BIN to run against real Audiveris")
def test_real_audiveris_on_example(tmp_path):
    produced = convert(SAMPLE_IMAGE, tmp_path, timeout=600)
    assert produced
    assert "<score-partwise" in read_musicxml(produced[0])
