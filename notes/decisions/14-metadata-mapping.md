# 14 — Metadata field mapping & lock-merge rules

**Status:** ✅ Accepted

## Context

Several sources want to write series/book metadata: embedded **ComicInfo.xml** (CBZ/CBR), **EPUB OPF**, **PDF info**, the **filename parser** ([06](06-filename-parser.md)), **external providers** ([13](13-metadata-providers.md)), and **manual edits**. We need one deterministic **merge** with a clear precedence and **field locking** — the follow-up flagged in [05](05-domain-model.md) / [07](07-scan-pipeline.md) / [10](10-tagging-content-rating.md). This is Komga's provider → patch → apply-to-unlocked model, made explicit.

## Decision

### Every source emits a `MetadataPatch`
A patch is a **partial** set of fields (only what that source knows) targeting a series and/or book, plus multi-value bundles (tags, authors, alt titles, links). Sources never write the DB directly — they produce patches.

### Precedence (highest wins per **unlocked** field)
1. **Manual user edit** — always wins, and **auto-locks** that field ([05](05-domain-model.md) `locked_fields`).
2. **Embedded metadata** — ComicInfo.xml, EPUB OPF, PDF info.
3. **External provider** — MangaDex etc. ([13](13-metadata-providers.md)).
4. **Filename/path parser** ([06](06-filename-parser.md)).
5. **Derived defaults** — natural-sort ordinal, folder name.

Default **embedded > provider** (a file's own ComicInfo is usually intentional), with a **per-library toggle to prefer provider** (for raw libraries whose embedded data is absent/stale).

### Merge mechanism
`apply(entity, patches)`:
- For each **scalar** field, take the value from the **highest-precedence patch that provides it** — **unless the field is in `locked_fields`**, in which case the stored value is kept untouched.
- For **multi-value** fields: **union** across sources for `tags` and `authors` (accumulate; de-duplicate by id/name+role); **replace** for scalars and for `alt_titles`/`links` a merge-by-key. (Union-vs-replace is per-field policy, tabled below.)
- **Locks survive** move/rename restore ([07](07-scan-pipeline.md)) and every re-scan/refresh. A field is locked either by a manual edit (auto) or an explicit lock toggle. (We use a single `locked_fields` set per entity, not Komga's one-bool-per-field — same effect, less schema noise.)

### Source → schema field mapping

**ComicInfo.xml** (the interop standard — read on scan, and **written on export/download**):

| ComicInfo | lychee | notes |
|---|---|---|
| `Series` (+`Volume`) | `series.title` | optional "append volume" |
| `Title` | `book.title` | |
| `Number` | `book.number` / `number_sort` | decimal-safe |
| `Count` | series total book count | |
| `Year`/`Month`/`Day` | `book.release_date` | |
| `Writer`/`Penciller`/`Inker`/`Colorist`/`Letterer`/`CoverArtist`/`Editor`/`Translator` | `book_author(name, role)` | union |
| `Publisher` | `series.publisher` | |
| `Genre` | `series_tag` (genre group) | union → [10](10-tagging-content-rating.md) |
| `Tags` | series/book tags | union |
| `LanguageISO` | `series.language` | |
| `Manga` (`YesAndRightToLeft`) | `series.reading_direction` | |
| `AgeRating` | → `content_rating` via best-effort table | see below |
| `SeriesGroup` | collections | |
| `StoryArc`/`StoryArcNumber`, `AlternateSeries`/`AlternateNumber` | read lists | |
| `GTIN` | `book.isbn` | validated |
| `Web` | links | |

**EPUB OPF (Dublin Core):** `dc:title`→title, `dc:creator`(+role)→author, `dc:description`→summary, `dc:language`→language, `dc:date`→release_date, `dc:identifier`(ISBN)→isbn, `dc:publisher`→publisher, `dc:subject`→tags, calibre `series`/`belongs-to-collection`→series + number.

**MangaDex provider:** full table in [../mangadex-api/README.md](../mangadex-api/README.md) §5 (title/altTitles/description/status/year/contentRating/demographic/tags/authors/cover).

**Filename parser ([06](06-filename-parser.md)):** volume, number, number_sort, year, special.

### Content rating vs age rating (two different axes)
- **`content_rating`** ([10](10-tagging-content-rating.md), MangaDex enum `safe/suggestive/erotica/pornographic`) is the **canonical explicitness axis**.
- **ComicInfo `AgeRating`** (`Everyone`, `Teen`, `Mature 17+`, `Adults Only 18+`, …) is mapped into `content_rating` via a **best-effort, configurable table** (e.g. Everyone/Teen→safe/suggestive, Mature→erotica, Adults Only→pornographic); the raw string may also be retained. This keeps one canonical rating while accepting either source.

### ComicInfo read **and** write
lychee **reads** ComicInfo on scan and **writes** it on export and on download ([13](13-metadata-providers.md)) — a round-trip serializer — so libraries stay interoperable with Komga/Kavita/Mihon.

## Consequences

- Deterministic, lock-protected metadata: manual edits are sacred; automated sources never clobber them.
- Multiple sources coexist cleanly via patches + precedence; `union` keeps tags/authors from all sources.
- ComicInfo read/write makes lychee a good citizen in the existing ecosystem.

## Follow-ups

- The exact **`AgeRating` → `content_rating`** table (and whether to keep a raw `age_rating` field).
- **Mylar `series.json`** provider (Komga supports it) as another embedded source.
- Default of the **per-library embedded-vs-provider** precedence toggle.

## Alternatives considered

- **One `*_lock` boolean per field** (Komga) — rejected for a single `locked_fields` set (05): same guarantee, less schema noise.
- **Provider-authoritative always** — rejected: embedded wins by default, per-library configurable.
- **Ignoring embedded metadata / parser-only** — rejected: ComicInfo is the interop baseline.
