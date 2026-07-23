# Overview 2 — Media Management Model

How each project models libraries, series, one-shots, volumes/chapters, collections, and pages.
Per-project detail: [komga](komga/README.md) · [kamiyomu](kamiyomu/README.md) · [mango](mango/README.md) · [lanraragi](lanraragi/README.md).

## Comparison

| Aspect | Komga | KamiYomu | Mango | LANraragi |
|---|---|---|---|---|
| Hierarchy | Library → **Series** → **Book** → Media/Page | Library(=1 manga) → Chapter → (Page) | Library → **Title** → **Entry** → Page | **flat**: Archive (one file = one entry) |
| Unit of "a book" | `Book` (one file) | `ChapterDownloadRecord` (one CBZ) | `Entry` (archive file *or* image dir) | `Archive` (one file) |
| Series concept | first-class `SERIES` table | implicit (the Library *is* the series) | `Title` = a directory (recursively nestable) | **none** (emergent via tags/tankoubon) |
| One-shot handling | first-class: virtual series in `oneshotsDirectory`, `oneshot` bool on both Series & Book | n/a (everything is a series of chapters) | just a Title with one Entry (no special model) | natural (every archive is standalone) |
| Volume vs chapter | `Volume` from metadata appended to series title; chapter = `Book.number` | `Chapter.Volume` + `Chapter.Number` (both decimal) | inferred by ChapterSorter keys ("Vol."/"Ch.") | none (single archive; `toc` marks chapters *inside*) |
| Number type | `NUMBER` (display str) + `NUMBER_SORT` (float) | `decimal` | BigDecimal in sorter | n/a |
| Cross-series grouping | **Collection** (of series), **ReadList** (of books), both orderable | — | nested Titles only | **Category** (static list / dynamic saved-search), **Tankoubon** (ordered archive group) |
| Page model | `MEDIA_PAGE` rows (name, number, w/h, hash) | ephemeral (read from CBZ live) | counted, read live | listed from archive live; `toc` for chapters |
| ID scheme | TSID (time-sortable) | GUID | random UUID (hex) | SHA-1 of first 512 KB (content) |
| Nesting depth | 1 (every dir = a Series; no sub-series) | flat | **unbounded** (`parent_id` recursion) | flat |

## Patterns & divergences

- **Relational tree vs flat tags.** Komga's `Library→Series→Book` is the canonical shelf model most users expect. LANraragi is the opposite pole: no hierarchy at all, organization purely by **namespaced tags** + **categories** + **tankoubon**. Mango sits between: a **recursive Title tree** where a directory can be *both* a child Title and an Entry of its parent. KamiYomu is degenerate (one Library = one manga).
- **One-shots need a real answer.** Komga is the only one that treats one-shots as first-class, via a clever trick: a book in the configured `oneshotsDirectory` gets wrapped in a **synthetic Series whose URL points at the file itself**, and both `Series.oneshot` and `Book.oneshot` are set. This lets the same UI/list code handle series and standalone books uniformly.
- **Display vs sort is always split.** Komga `NUMBER`/`NUMBER_SORT`; Mango `title`/`sort_title`; KamiYomu decimal + padded template. A display string ("1.5 SP") and a numeric sort key are genuinely different fields.
- **Volumes are rarely first-class.** Only implied: Komga appends `Volume` to the series title; KamiYomu carries `Volume` as a property on `Chapter`; Mango/LANraragi don't model volumes at all. A dedicated `Volume` entity between Series and Book is a gap in all four — a design opportunity, but also a warning that it adds complexity everyone else avoided.
- **Collections vs reading order.** Komga cleanly separates **Collection** (a set of *series*, e.g. "Shonen Jump") from **ReadList** (an ordered set of *books* across series, e.g. a crossover reading order). LANraragi's **Tankoubon** ≈ ReadList (ordered books read as one unit, with a single global progress cursor). LANraragi's **dynamic Category** (a saved search) is a "smart collection" idea none of the others have.
- **Pages: materialized vs live.** Komga materializes pages as `MEDIA_PAGE` rows (enabling per-page hashing/dedup and dimension storage); the others read the archive live each request. Materializing costs scan time and storage but enables features (dedup, precise page dimensions, partial re-analysis).

## Recommendation for lychee

Adopt a **Komga-shaped relational hierarchy** with two borrowed ideas:

- **Core tree:** `Library → Series → Book → Page`.
  - `Series`: `id, library_id, title, sort_name, is_oneshot, book_count(denormalized), file_last_modified, deleted_at`.
  - `Book`: `id, series_id, library_id, title, number (display str), number_sort (float), file_path, file_size, partial_hash, is_oneshot, deleted_at`.
  - `Page`: materialize them (`book_id, index, file_name, media_type, width, height`) — the storage is cheap and it unlocks per-page features later.
- **One-shot** as a first-class flag using Komga's virtual-series trick, so lists/readers stay uniform.
- **Grouping:** `Collection` (ordered set of Series) **and** `ReadList` (ordered set of Books) — mirror Komga; treat LANraragi's Tankoubon as a ReadList with a global progress cursor.
- **Namespaced tags** (`artist:`, `series:`, `character:`, `language:` …) as a relational M2M with a `namespace` column (LANraragi's model, but relational not comma-string). Allow tags on both Series and Book.
- **Decimal-safe numbers:** `number_sort` float distinct from `number` display string, populated from metadata when present, else from the filename parser (see [06](06-scan-and-filenames.md)).
- **Consider but defer** a `Volume` entity — none of the four found it worth the complexity; add it only if the UI genuinely needs volume shelves.
- **IDs:** surrogate keys (UUID/TSID-style, time-sortable is a nice free win). Do **not** use a content hash as the primary key (LANraragi's 512 KB SHA-1 causes false collisions and couples identity to bytes).
