# 06 — Filename / volume-chapter parser

**Status:** ✅ Accepted

## Context

Layer 2 of the resolution order from [05](05-domain-model.md): when embedded metadata is absent, the parser fills `volume` / `number` / `number_sort` (and, without a folder, a series name) from names on disk.

Reference approaches ([../06-scan-and-filenames.md]): Komga does **no** filename parsing (metadata-only); Mango's `ChapterSorter` infers **relative ordering**; LANraragi's `RegexParse` targets **doujinshi tagging**. The real prior art for absolute number extraction is **Kavita's parser** and **Mihon/Tachiyomi's `ChapterRecognition`**, both **prioritized regex cascades** with manga vs comic profiles.

Decisions by review: **adopt-and-extend a proven pattern set (don't reinvent)**; **represent specials as decimals** (e.g. 30.1, 30.2).

## Decision

### 1. Adopt-and-extend, don't reinvent
Base the parser on a community-hardened pattern set rather than authoring cold. Candidates to evaluate/benchmark during implementation:
- `comicfn2dict` (Python — comic filename → dict),
- ported regex sets from **Kavita** and **Mihon `ChapterRecognition`**.

Extend the chosen base with manga specifics (combined `v03c021`, scanlation/group tags) and lychee's **series-name-subtraction** step. Final selection is validated against a real-world **test corpus** (below), not chosen blind.

### 2. Resolution order (from 05)
embedded metadata (ComicInfo/OPF) → **this parser** → Mango-style `ChapterSorter` ordering → natural-sort ordinal (guaranteed fallback).

### 3. Inputs & the series-name advantage
Parse the **path segments below the series folder + the filename** (so a `Vol. 03/` grouping folder supplies the volume — [05](05-domain-model.md) hybrid model). Because the **series name comes from the folder**, the parser **subtracts the known series name first**, then hunts for numbers in the remainder — this kills the classic title-number false positives (`Gundam 0079`, `7 Seeds`).

### 4. Extraction
Normalize (`_`→space, strip `[group]` / `(Digital)` / `(f)` / quality noise, collapse whitespace — **preserve decimal points**), then a **prioritized regex cascade** (profile chosen by `library.kind`: manga vs comic) extracts: volume, chapter/number, range (→ first number), comic year, and any **special marker**.

### 5. Outputs
- `number_sort` — **float, decimal-safe** — the ordering key.
- `number` — display string preserving the human label (`"10.5"`, `"Omake 1"`).
- plus `volume`, optional `year`, and a `special` flag/label.

### 6. Specials as decimals
A special (Omake / Extra / Epilogue / SP / Prologue / Bonus) is placed as a **decimal offset after its preceding chapter** → `30.1`, `30.2`, …:
- If the name carries a base number (`Chapter 30 Omake`, `30.5`), offset from it.
- If it carries only a marker (`Omake.cbz`), the **series-level ordering pass** assigns the decimal from its sorted neighbours (this couples the parser to the ordering step — handoff to ADR 07).
- **Source-assigned decimals** (`Chapter 10.5`) are honoured as-is; a `special` flag + label are retained for display.

### 7. Config-tunable per library
An optional user-supplied regex / override (LANraragi `RegexParse` style) lets users fix oddball naming without a code change.

### 8. Swappable interface
`parse(path_segments, series_name, kind) -> ParsedName{volume, number, number_sort, year, special, label}` — behind an interface so the underlying pattern set can be replaced/upgraded.

### Test corpus (required)
Assemble a fixture of real-world names as the parser's regression suite and benchmark adopt-candidates against it before committing: nested `Vol/Ch`, decimals, ranges (`c001-004`), specials (with and without a base number), group tags, comics with `(year)`, and tricky series whose titles contain numbers.

## Consequences

- Reuses years of community edge-case work instead of rediscovering it.
- Series-name-subtraction + folder-derived volume make parses more robust than filename-only parsers.
- Specials sort sensibly and stably as decimals, alongside real source decimals.
- Parser + ordering are coupled at the **series level** for specials placement → feeds ADR 07 (scan/ordering).

## Alternatives considered

- **Build a native cascade cold** — rejected (reinvents solved edge cases).
- **Komga's metadata-only / no-parse** — rejected (fails on raw untagged libraries); metadata still takes precedence when present.
- **Specials dumped to the end / a separate special-index scheme** — rejected in favour of decimals (simpler, sorts naturally, matches common conventions).
