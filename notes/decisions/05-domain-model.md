# 05 — Domain data model & filesystem mapping

**Status:** ✅ Accepted

## Context

lychee is a scan-and-index server, so the database tree is **bound to the directory tree** (camp 1 in the research — Komga/Mango, not LANraragi's content-hash or KamiYomu's DB-owns-files). This ADR fixes the domain entities and, crucially, **how they map to physical files**. Builds on [01](01-repo-structure-monorepo.md) (monorepo), [04](04-database-sqlite.md) (SQLite; no page table), and the file-identity strategy in [../03-file-management-sync.md].

Decisions taken by review:
- **Hybrid folder mapping** — first folder level = Series; everything beneath = its Books.
- **Loose-image folders are Books** (Mango's `DirEntry`).

## Decision

### Core hierarchy

```
Library ─1:N─ Series ─1:N─ Book        (Book carries page_count only — no Page rows, per 04)

Collection ─M:N(ordered)─ Series        (logical grouping)
ReadList   ─M:N(ordered)─ Book          (logical reading order, incl. cross-series)
Tag        ─M:N─ Series | Book          (namespaced: artist:, series:, language: …)
User       ─1:N─ ReadingProgress ─N:1─ Book
```

### Filesystem mapping — the hybrid rule

- **Library** = a registered root folder (has `kind` + scan options).
- **Series** = the **first directory level** beneath a library root.
- **Book** = a readable item found by walking a series folder to **any depth**:
  - an **archive file** (`.cbz .cbr .zip .rar .7z .pdf .epub`) → a Book;
  - a **folder whose direct children are images** (`DirEntry`) → a loose-image Book;
  - intermediate folders that contain archives or book-folders are **grouping levels only** (not entities); their names feed volume/chapter parsing.
- **One-shot** = a Book sitting directly under the library root (in no series folder) → wrapped in its **own virtual Series** with `is_oneshot = true` (Komga's trick, keeps list/reader code uniform).
- **Volume is not an entity** — it is parsed from the path/filename into `book.volume` (plus `book.number` / `number_sort`).
- **Embedded `ComicInfo.xml` `Series` overrides** the folder-derived series name — the ambiguity escape hatch (and lets a correctly-tagged file live anywhere).

```
Library "Manga"  (root = /data/manga, kind = manga)
└── One Piece/                 → Series "One Piece"        (first level = Series)
    ├── Vol. 01/               → grouping only (feeds volume=1)
    │   ├── Ch.001.cbz         → Book  (volume 1, number 1)
    │   └── Ch.002.cbz         → Book  (volume 1, number 2)
    ├── Vol. 02/
    │   └── Ch.010.cbz         → Book  (volume 2, number 10)
    └── Extra/                 → grouping
        └── page01.jpg …       → Book  (loose-image DirEntry)
AKIRA.cbz                      → one-shot → virtual Series "AKIRA"
```

**Folder → entity resolution (the one tricky rule):** when walking a series folder, a sub-folder is a **loose-image Book** if its *direct* children are image files; it is a **grouping level** if it contains archives or other folders. (This is Mango's `DirEntry.is_valid?` test.) `ComicInfo.xml` always wins over inference.

### Physical binding & identity

- **Paths are stored relative to the library root** (Mango's practice) so the whole library can be moved/remounted/Docker-remapped without rewriting rows.
- **Identity is a surrogate id, never the path.** Move/rename resilience comes from `(file_size, partial_hash)` matching against soft-deleted rows (see [../03-file-management-sync.md]); `deleted_at` + a trash step preserve progress/metadata across reorganizations.
- A renamed **series folder** has no content hash, so it is reconciled by **re-grouping its (move-tracked) books**; series metadata + collection membership are restored by matching the stable, lock-respecting series title.

### Schema sketch (SQLite via SQLAlchemy; illustrative)

```
user(id, username UNIQUE, password_hash, roles, age_restriction?, created_at)

library(id, name, root_path, kind[manga|comic|ebook|mixed], options_json, created_at)

series(id, library_id→library, path_rel, name, sort_name,
       is_oneshot, book_count,                       -- denormalized
       -- metadata (inline) + lock set:
       summary, status, reading_direction, publisher, age_rating, language,
       total_book_count, locked_fields_json,
       file_last_modified, created_at, updated_at, deleted_at)

book(id, series_id→series, library_id→library,        -- library_id denormalized for filters
     path_rel, content_kind[cbz|cbr|zip|rar|7z|pdf|epub|image_dir],
     file_size, partial_hash, page_count,
     volume, number, number_sort,                     -- number_sort = float (decimal-safe)
     is_oneshot,
     title, summary, release_date, isbn, locked_fields_json,
     file_last_modified, created_at, updated_at, deleted_at)

book_author(book_id→book, name, role)                 -- writer/penciller/…

tag(id, namespace, value, UNIQUE(namespace, value))     -- ⚠ REFINED by 10:
series_tag(series_id→series, tag_id→tag)                 --   managed id-based taxonomy (tag_group +
book_tag(book_id→book, tag_id→tag)                       --   content_rating + demographic), series-level

collection(id, name, ordered)
collection_series(collection_id→collection, series_id→series, position)
read_list(id, name)
read_list_book(read_list_id→read_list, book_id→book, position)

reading_progress(user_id→user, book_id→book, current_page, completed,
                 locator_json NULL, last_read_at, PRIMARY KEY(user_id, book_id))
series_read_progress(user_id, series_id, read_count, in_progress_count)  -- rollup for shelves
```

## Consequences

- Real nested manga layouts (`Series/Volume/Chapter.cbz`) resolve to **one Series with path-parsed volumes** — no Volume-entity complexity, and no per-volume "series" explosion (the flat-model failure).
- Loose-image (un-zipped) chapter folders are first-class Books.
- The DB is decoupled from exact paths → reorganizations/relocations are safe.
- `page_count` on the book satisfies "resume at page Y" with no Page rows (per [04](04-database-sqlite.md)).

## Follow-ups (not this ADR)

- **Filename/volume-chapter parser** → [06](06-filename-parser.md). ✅
- **Scan pipeline + the folder→entity resolution algorithm** in detail → ADR 07.
- **Metadata field mapping & lock semantics** → [14](14-metadata-mapping.md) (full ComicInfo/OPF mapping + `locked_fields` merge rules).
- **Multilingual title storage** (native / romanized / English) → [18](18-title-variants.md) — `series.name` here becomes the denormalized `display_title` over a language-tagged `series_title` table.

## Alternatives considered

- **Flat (Komga)** and **fully recursive (Mango)** folder mappings — rejected in review in favor of hybrid.
- **Volume as an entity** — deferred; modeled as a parsed attribute on Book instead.
- **Content-hash as primary key** (LANraragi) — rejected as identity; used only as a move-restore signal.
