# Overview 6 — Media Scan & Filename Structure

The scan pipeline, expected directory layouts, and how names are parsed into series/volume/chapter.
Per-project detail: [komga](komga/README.md) · [kamiyomu](kamiyomu/README.md) · [mango](mango/README.md) · [lanraragi](lanraragi/README.md).

## Comparison

| Aspect | Komga | KamiYomu | Mango | LANraragi |
|---|---|---|---|---|
| Scan model | walk tree → reconcile with DB | n/a (creates files from crawler) | recursive `Title.examine` with signature short-circuit | `update_filemap` diff FS vs filemap |
| Directory → entity | every dir = a **Series**; files = Books | fixed `{manga}/{manga} Ch.{n}.cbz` | dir = **Title** (recursive); file/img-dir = Entry | folder structure **ignored** (flat) |
| Sub-series nesting | not supported (flat, 1 level) | n/a | **unbounded** recursion | n/a |
| Number source | **metadata** (ComicInfo/OPF); filename only for natural-sort ordering | crawler `Chapter.Number` | **ChapterSorter** parses filenames | **RegexParse** plugin parses filenames |
| Filename parser | **none** (no regex) | none | `ChapterSorter` (prefix+number keys) | doujinshi regex `(Event)[Artist]Title(Series)[Lang]` |
| Ordering within a set | natural sort of `Book.name` → 1-based ordinal → default `numberSort` | `Chapter.Number` asc | ChapterSorter multi-key numeric | natural sort of pages; archives unordered |
| Decimal chapters | via metadata `numberSort` | `decimal` | BigDecimal (`Ch. 10.5`) | n/a (per-archive) |
| Sidecar handling | prefilter + exact match (series.json, cover.*, artwork) | writes ComicInfo into CBZ | `info.json` per dir | — |
| Short-circuit / perf | dir mtime gate; `scanForceModifiedTime` for NFS | `File.Exists` check | `contents_signature` unchanged → skip subtree | filemap diff; per-file lock |
| Folder→group tooling | Collections via `SeriesGroup`/Mylar | path template | nested titles | `FolderToCat` script plugin (folder → category) |

## Two philosophies of "where does the chapter number come from?"

- **Metadata-authoritative (Komga).** The filename is used *only* to derive a stable natural-sort order; the ordinal position becomes the default `numberSort`, and any real number/volume/chapter comes from **embedded metadata** (ComicInfo.xml `Number`/`Volume`, EPUB `group-position`). No regex filename parsing at all. Pragmatic and unambiguous *if* files carry metadata — but weak for raw scanned collections with no ComicInfo.
- **Filename-parsing (Mango, LANraragi).** No embedded metadata assumed, so the name is parsed:
  - **Mango `ChapterSorter`** (`src/util/chapter_sort.cr`): scans *all* entry names in a title, extracts `(prefix, number)` pairs via `([^0-9\n\r ]*)[ ]*([0-9]*\.*[0-9]+)`, builds a table of candidate "keys" (e.g. `"Vol."`, `"Ch."`, `""`), discards keys present in <half the entries, ranks keys by frequency then range, and does a **multi-key numeric comparison** (BigDecimal, so `Ch. 10.5` sorts correctly). This is the most reusable ordering algorithm across all four projects.
  - **LANraragi `RegexParse`** (`Plugin/Metadata/RegexParse.pm`): the **doujinshi convention** `(Event) [Artist] Title (Series) [Language]` with named capture groups → tag namespaces; `Circle (Artist)` splits into `group:` + `artist:`. Underscores→spaces before matching. Aimed at tagging, not volume/chapter numbering.
- **Neither handles both well.** Komga assumes metadata; the parsers assume convention. A real scanner needs a **layered fallback**: embedded metadata → filename structural parse (volume/chapter, Kavita/Komga-style regexes) → natural-sort ordinal.

## Directory layouts seen

- **Komga:** `Library/Series Dir/Book files…`; a configured `Oneshots/` dir turns each file into its own series. One level (dirs don't nest into sub-series).
- **Mango:** flexible — flat (`Berserk/Berserk v01.cbz`), nested (`One Punch Man/Vol. 1/Ch. 001.cbz`), or loose images (`My Manga/Chapter 1/page001.jpg`); a dir can be both a sub-Title and a DirEntry.
- **KamiYomu:** generated only — `{manga_title}/{manga_title} Ch.{chapter_padded_4}.cbz` (path template configurable).
- **LANraragi:** flat content folder; subfolders are scanned but **not** used for grouping (optional `FolderToCat` maps top-level folders to categories).

## Recommendation for lychee

- **Scan pipeline:** walk the library root → for each directory decide Series (and support Mango-style loose-image "directory entries") → reconcile against DB (add/update/soft-delete) → enqueue per-book analysis + thumbnail tasks (serialized per series). Use a **cheap gate then confirm**: directory `mtime` / a `contents_signature` (Mango) to skip unchanged subtrees; `scanForceModifiedTime`-style recompute for NFS/SMB (Komga).
- **Number/metadata resolution order (layered):**
  1. Embedded **ComicInfo.xml** / **EPUB OPF** (authoritative — Komga).
  2. **Filename structural parse** — port a Kavita/Komga-style regex set for `Vol.`/`Ch.`/`Chapter`/`v01`/`c001`/decimal/one-shot markers, plus **Mango's `ChapterSorter`** for series-relative ordering when numbers are ambiguous.
  3. **Natural-sort ordinal** as the final fallback (Komga) so order is always defined.
- **Directory conventions:** support flat and nested layouts; treat a configured one-shots directory specially (Komga); optionally infer Series/Volume from `Series/Volume/file.cbz` nesting (a gap in LANraragi worth filling). Allow an explicit sidecar (`ComicInfo.xml` or a `lychee.json`) to override directory-name inference (Mango's "title = dirname" is too rigid).
- **Doujinshi mode:** offer LANraragi's `(Event)[Artist]Title(Series)[Language]` parser as an optional per-library filename-to-tags rule for doujinshi collections.
- **Ports to write in Python:** `ChapterSorter` (Mango) and the doujinshi `RegexParse` regex (LANraragi) are both directly translatable and immediately useful.
