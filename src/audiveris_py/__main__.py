from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import AudiverisError, convert, read_musicxml
from .doctor import FAIL, format_report, run_checks


def _positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError(f"must be greater than 0, got {value}")
    return number


def doctor_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="audiveris-py doctor",
        description="Check that Audiveris is installed and usable.",
    )
    parser.add_argument("--audiveris", help="path to the Audiveris executable")
    parser.add_argument(
        "--timeout", type=_positive_float, default=120, help="seconds to wait for Audiveris to start"
    )
    args = parser.parse_args(argv)

    checks = run_checks(args.audiveris, timeout=args.timeout)
    print(format_report(checks))
    return 1 if any(c.status == FAIL for c in checks) else 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["doctor"]:
        return doctor_main(argv[1:])

    parser = argparse.ArgumentParser(
        prog="audiveris-py",
        description="Convert PDF/image scores to MusicXML using Audiveris.",
        epilog="Run 'audiveris-py doctor' to check your Audiveris installation.",
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="PDF or image files")
    parser.add_argument("-o", "--output", type=Path, default=Path("."), help="output folder")
    parser.add_argument("--audiveris", help="path to the Audiveris executable")
    parser.add_argument("--sheets", type=int, nargs="+", help="sheet numbers to process")
    parser.add_argument("--timeout", type=float, help="timeout in seconds")
    parser.add_argument(
        "--uncompressed",
        action="store_true",
        help="also write an uncompressed .musicxml next to each .mxl",
    )
    args = parser.parse_args(argv)

    try:
        produced = convert(
            args.inputs,
            args.output,
            audiveris=args.audiveris,
            sheets=args.sheets,
            timeout=args.timeout,
        )
    except (AudiverisError, FileNotFoundError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 1

    for path in produced:
        print(path)
        if args.uncompressed and path.suffix == ".mxl":
            target = path.with_suffix(".musicxml")
            target.write_text(read_musicxml(path), encoding="utf-8")
            print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
