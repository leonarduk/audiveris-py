from __future__ import annotations

import stat
import sys
import textwrap
from pathlib import Path

import pytest

from audiveris_py import core
from audiveris_py.__main__ import main
from audiveris_py.doctor import (
    FAIL,
    OK,
    WARN,
    audiveris_config_dir,
    check_runs,
    check_tessdata,
    format_report,
    run_checks,
    tessdata_dir,
)

VERSION_OUTPUT = """Audiveris
- Version:      5.7.1
- Commit:       abc123
- OCR Engine:   Tesseract 5.5.0
"""


def make_launcher(tmp_path: Path, output: str = VERSION_OUTPUT, exit_code: int = 0) -> Path:
    script = tmp_path / "Audiveris"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import sys
            assert sys.argv[1:] == ["-version"], sys.argv
            sys.stdout.write({output!r})
            sys.exit({exit_code})
            """
        )
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """No Audiveris on PATH or in default locations; config under tmp_path."""
    monkeypatch.delenv("AUDIVERIS_BIN", raising=False)
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.setattr(core, "default_install_locations", lambda platform=sys.platform: [])
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    return tmp_path


@pytest.mark.parametrize(
    "platform,env,expected",
    [
        ("linux", {"HOME": "/h"}, Path("/h/.config/AudiverisLtd/audiveris")),
        ("linux", {"HOME": "/h", "XDG_CONFIG_HOME": "/x"}, Path("/x/AudiverisLtd/audiveris")),
        ("darwin", {"HOME": "/h"}, Path("/h/Library/Application Support/AudiverisLtd/audiveris")),
        ("win32", {"APPDATA": "/a"}, Path("/a/AudiverisLtd/audiveris/config")),
        ("win32", {}, None),
        ("linux", {}, None),
    ],
)
def test_config_dir_mirrors_audiveris(platform, env, expected):
    assert audiveris_config_dir(platform, env) == expected


def test_tessdata_prefix_wins_only_when_it_is_a_directory(tmp_path):
    env = {"HOME": str(tmp_path), "TESSDATA_PREFIX": str(tmp_path / "tess")}
    fallback = tmp_path / ".config" / "AudiverisLtd" / "audiveris" / "tessdata"
    assert tessdata_dir("linux", env) == fallback
    (tmp_path / "tess").mkdir()
    assert tessdata_dir("linux", env) == tmp_path / "tess"


def test_tessdata_lists_languages(tmp_path):
    (tmp_path / "eng.traineddata").write_bytes(b"")
    (tmp_path / "deu.traineddata").write_bytes(b"")
    check = check_tessdata("linux", {"TESSDATA_PREFIX": str(tmp_path)})
    assert check.status == OK
    assert check.detail.startswith("deu, eng in ")


def test_tessdata_missing_is_a_warning_with_download_hint(tmp_path):
    check = check_tessdata("linux", {"HOME": str(tmp_path)})
    assert check.status == WARN
    assert "tessdata" in check.hint


def test_check_runs_parses_version(tmp_path):
    check = check_runs(str(make_launcher(tmp_path)), timeout=30)
    assert (check.status, check.detail) == (OK, "version 5.7.1")


def test_check_runs_fails_on_nonzero_exit(tmp_path):
    launcher = make_launcher(tmp_path, output="Error: could not find Java\n", exit_code=1)
    check = check_runs(str(launcher), timeout=30)
    assert check.status == FAIL
    assert "could not find Java" in check.detail


def test_check_runs_warns_without_version_line(tmp_path):
    check = check_runs(str(make_launcher(tmp_path, output="hello\n")), timeout=30)
    assert check.status == WARN


def test_missing_executable_skips_start_check(isolated):
    checks = run_checks()
    assert [c.name for c in checks] == ["Audiveris executable", "OCR language data"]
    assert checks[0].status == FAIL
    assert checks[0].detail.startswith("not found on PATH")
    assert "AUDIVERIS_BIN" in checks[0].hint


def test_bad_explicit_path_is_reported_as_given(isolated):
    check = run_checks(isolated / "nope")[0]
    assert check.status == FAIL
    assert str(isolated / "nope") in check.detail


def test_find_audiveris_uses_default_install_location(isolated, monkeypatch):
    launcher = make_launcher(isolated)
    monkeypatch.setattr(core, "default_install_locations", lambda platform=sys.platform: [launcher])
    assert core.find_audiveris() == str(launcher)


@pytest.mark.parametrize(
    "platform,expected",
    [
        ("linux", Path("/opt/audiveris/bin/Audiveris")),
        ("darwin", Path("/Applications/Audiveris.app/Contents/MacOS/Audiveris")),
        ("win32", Path("/pf/Audiveris/Audiveris.exe")),
    ],
)
def test_default_install_locations(platform, expected, monkeypatch):
    monkeypatch.setenv("ProgramFiles", "/pf")
    assert core.default_install_locations(platform) == [expected]


def test_check_runs_times_out(tmp_path):
    script = tmp_path / "slow"
    script.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(10)\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    check = check_runs(str(script), timeout=0.5)
    assert check.status == FAIL
    assert "within 0.5s" in check.detail


def test_tessdata_reports_ignored_prefix(tmp_path):
    check = check_tessdata("linux", {"HOME": str(tmp_path), "TESSDATA_PREFIX": str(tmp_path / "missing")})
    assert "TESSDATA_PREFIX=" in check.detail
    assert "ignored" in check.detail


@pytest.mark.parametrize("value", ["0", "-5"])
def test_cli_doctor_rejects_non_positive_timeout(value, capsys):
    with pytest.raises(SystemExit) as info:
        main(["doctor", "--timeout", value])
    assert info.value.code == 2
    assert "must be greater than 0" in capsys.readouterr().err


def test_dotted_doctor_path_is_converted_not_diagnosed(isolated, capsys):
    assert main(["./doctor"]) == 1
    assert "error:" in capsys.readouterr().err


def test_format_report_shows_hints_only_for_problems():
    from audiveris_py.doctor import Check

    report = format_report([Check("a", OK, "fine", "unused"), Check("b", WARN, "meh", "do this")])
    assert report == "[ OK ] a: fine\n[WARN] b: meh\n       -> do this"


def test_cli_doctor_all_good(isolated, capsys):
    launcher = make_launcher(isolated)
    tess = isolated / "xdg" / "AudiverisLtd" / "audiveris" / "tessdata"
    tess.mkdir(parents=True)
    (tess / "eng.traineddata").write_bytes(b"")

    rc = main(["doctor", "--audiveris", str(launcher)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "[ OK ] Audiveris starts: version 5.7.1" in out
    assert "[ OK ] OCR language data: eng in" in out


def test_cli_doctor_warning_only_still_exits_zero(isolated, capsys):
    rc = main(["doctor", "--audiveris", str(make_launcher(isolated))])
    assert rc == 0
    assert "[WARN] OCR language data" in capsys.readouterr().out


def test_cli_doctor_fails_without_audiveris(isolated, capsys):
    assert main(["doctor"]) == 1
    assert "[FAIL] Audiveris executable" in capsys.readouterr().out
