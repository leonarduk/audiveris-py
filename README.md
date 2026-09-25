# audiveris-py

Thin Python wrapper around the Audiveris command line, for converting PDF or image
scores to MusicXML. It does not reimplement any recognition: it runs
`audiveris -batch -export` and returns the files that run produced.

## Requirements

- An installed [Audiveris](https://github.com/Audiveris/audiveris). It is found via
  `--audiveris`/the `audiveris=` argument, the `AUDIVERIS_BIN` environment variable,
  `audiveris` or `Audiveris` on `PATH`, or the installer's default location
  (`/opt/audiveris/bin/Audiveris`, `C:\Program Files\Audiveris\Audiveris.exe`,
  `/Applications/Audiveris.app/Contents/MacOS/Audiveris`).
- Python 3.9+. No third-party runtime dependencies.

## Install

```sh
pip install audiveris-py
```

Or the latest development version:

```sh
pip install git+https://github.com/leonarduk/audiveris-py.git
```

## Check your setup

```sh
audiveris-py doctor
```

```
[ OK ] Audiveris executable: /opt/audiveris/bin/Audiveris
[ OK ] Audiveris starts: version 5.7.1
[WARN] OCR language data: no *.traineddata in ~/.config/AudiverisLtd/audiveris/tessdata; lyrics and other text will not be recognised
       -> Download e.g. eng.traineddata from https://github.com/tesseract-ocr/tessdata into ~/.config/AudiverisLtd/audiveris/tessdata.
```

It exits non-zero if Audiveris can't be found or won't start. Missing OCR language
files are only a warning: notes are still recognised, text isn't.

## Command line

```sh
audiveris-py score.pdf -o out/
audiveris-py score.pdf -o out/ --sheets 1 2 --uncompressed --timeout 900
```

Each input `name.pdf` is exported as `out/name/name.mxl`, or `out/name/name.mvtN.mxl`
when the book holds several movements. `--uncompressed` also writes a plain
`.musicxml` next to each `.mxl`.

## Library

```python
from audiveris_py import convert, read_musicxml

files = convert("score.pdf", "out/")
xml = read_musicxml(files[0])
```

`convert` raises `AudiverisError` when Audiveris exits non-zero (status 1 = failure,
2 = timeout, 3 = both) or exports nothing. The error carries `returncode` and the
full console `output`.

## Tests

```sh
pip install -e '.[test]'
pytest
```

The unit tests use a fake Audiveris executable. To also run against a real install:

```sh
AUDIVERIS_BIN=/path/to/Audiveris pytest
```

`tests/data/chula.png` is a sample score from the Audiveris project (AGPL-3.0).

## Releasing

Publishing uses PyPI trusted publishing, so no API token is stored in GitHub.

1. Bump `version` in `pyproject.toml` and merge to `main`.
2. Create a GitHub release with tag `v<version>` (e.g. `v0.1.0`).
3. The `Publish to PyPI` workflow checks the tag matches the version, builds,
   and uploads.
