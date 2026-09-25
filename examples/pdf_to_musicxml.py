"""Convert a PDF (or a folder of PDFs) to MusicXML with audiveris-py.

    python examples/pdf_to_musicxml.py score.pdf -o out/
    python examples/pdf_to_musicxml.py scores/ -o out/ --timeout 900

Writes Audiveris's compressed .mxl files plus an uncompressed .musicxml next to each.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from audiveris_py import AudiverisError, convert, read_musicxml


def convert_one(pdf: Path, out_dir: Path, timeout: float | None) -> list[Path]:
    written = []
    for mxl in convert(pdf, out_dir, timeout=timeout):
        target = mxl.with_suffix(".musicxml")
        target.write_text(read_musicxml(mxl), encoding="utf-8")
        written += [mxl, target]
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="a PDF file or a folder of PDFs")
    parser.add_argument("-o", "--output", type=Path, default=Path("out"), help="output folder")
    parser.add_argument("--timeout", type=float, help="seconds allowed per PDF")
    args = parser.parse_args()

    pdfs = sorted(args.source.glob("*.pdf")) if args.source.is_dir() else [args.source]
    if not pdfs:
        print(f"no PDFs found in {args.source}", file=sys.stderr)
        return 1

    failures = 0
    # One Audiveris run per PDF, so a bad scan doesn't sink the whole batch.
    for pdf in pdfs:
        try:
            for path in convert_one(pdf, args.output, args.timeout):
                print(f"{pdf.name}: {path}")
        except FileNotFoundError:
            failures += 1
            print(f"{pdf}: FAILED: file not found", file=sys.stderr)
        except AudiverisError as ex:
            failures += 1
            print(f"{pdf.name}: FAILED: {str(ex).splitlines()[0]}", file=sys.stderr)
            if ex.output:
                print(ex.output, file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
