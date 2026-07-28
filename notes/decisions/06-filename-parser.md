# 06 — Filename / volume-chapter parser

**Status:** Implemented.

## What this is

Since there's no embedded-metadata source ([05](05-domain-model.md) — no
ComicInfo/OPF reading exists), `volume`/`number`/`number_sort` come entirely
from names on disk: a hand-written regex cascade
(`backend/src/ingest/parser.py`), not a ported/adopted community pattern set
(`comicfn2dict` and Kavita/Mihon's `ChapterRecognition` were considered but
not used — the shipped parser was written from scratch).

## Interface

```python
parse(segments: list[str], series_name: str, kind: str = "manga") -> ParsedName
# ParsedName(number, number_sort, volume, year, special, label)
```

`segments` are the path components below the series folder plus the
filename, so a `Vol. 03/` grouping folder supplies the volume per the
hybrid filesystem mapping in ADR 05.

## Pipeline

1. Strip the extension.
2. Extract a year — **only** for `kind == "comic"` (manga filenames aren't
   checked for a year at all).
3. Normalize each segment: lowercase, `_`→space, strip bracketed
   group/quality noise, collapse whitespace, then **subtract the known
   series name as a literal substring** before hunting for numbers — this
   kills classic false positives (`Gundam 0079`, `7 Seeds`) where the title
   itself contains a number.
4. `_find_volume()` — checks the grouping-folder segments first, then the
   filename; handles combined forms like `v03c021`.
5. `_find_number()` — tries combined → range (first number wins,
   `"c001-004"` → `1.0`) → chapter-marker → a bare-number fallback after
   volume tokens are stripped.
6. `_find_special()` — substring match against a fixed marker list:
   `omake, extra, epilogue, prologue, bonus, special, side story, sp`.

The volume/chapter regexes are **identical for manga and comic** — `kind`
only gates the year extraction, not a genuinely separate cascade per kind.

## Specials sort as the next whole integer, not a decimal offset

This is the one place the original design and the shipped behavior diverge,
confirmed by `backend/tests/test_parser.py`:

- A special **with** a base number (`"Chapter 30 Omake.cbz"`) keeps that
  number as-is — `number_sort = 30.0`, not `30.1`.
- A **base-less** special (`"Omake.cbz"`) gets `number_sort = None` from the
  parser; the series-level ordering pass (`ingest/scanner.py`'s
  `order_chapters()`) then assigns it the **next whole integer** after the
  running max, not a decimal offset. A decimal-offset scheme for specials
  was the original plan but was never built.

## Config-tunable variant, for local import only

`parse_pattern(filename, pattern)` — a `{series}`/`{chapter}`/`{volume}`/…
token-template DSL — is a separate function used only by the **local-import**
feature (`ingest/importer.py`, driven by `ImportConfig.filename_pattern`),
not a general per-`Library` setting applied during ordinary directory scans.

## Why a hand-written cascade

Kavita's parser and Mihon's `ChapterRecognition` were the strongest prior
art considered, but a native cascade kept the dependency surface minimal and
made the series-name-subtraction step (folder-derived series name,
subtracted before number-hunting) straightforward to integrate rather than
retrofitting it onto someone else's pattern set. `backend/tests/test_parser.py`
is the regression suite this decision is validated against: nested
vol/chapter, combined `v03c021`, decimal chapters, ranges, specials with and
without a base number, group-tag stripping.
