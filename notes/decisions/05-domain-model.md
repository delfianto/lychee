# 05 — Domain data model & filesystem mapping

**Status:** Implemented.

## Core hierarchy

```
Library ─1:N─ Series ─1:N─ Book ─1:N─ Chapter   (today, effectively 1 Book : 1 Chapter)

Collection ─M:N(ordered)─ Series      (logical grouping — no book-level ReadList exists)
Tag        ─M:N─ Series               (series-level only; no book-level tags)
ReadingProgress ─1:1─ Chapter          (single implicit user — no User table at all)
```

The database tree is bound to the directory tree (a scan-and-index server,
not a content-hash or DB-owns-files design). **`Book` and `Chapter` are
split**, not one entity:

- **Book** — the physical container the scanner finds (archive or image
  directory): path, size, partial hash, page count. Move-tracking happens
  here via `(file_size, partial_hash)` + a soft `deleted_at`.
- **Chapter** — the logical reading unit the API serves
  (`/api/chapters/{id}`): a Book plus a page range, with display metadata
  (volume, number, group, language). A **gallery** Series has a Book but no
  Chapter at all — served via `/api/series/{id}/images` instead.

Splitting them leaves room for multi-chapter archives (one Book containing
several Chapters) without a schema change, even though today's scanner
produces exactly one Chapter per Book (`ingest/scanner.py`'s own docstring
lists multi-chapter archives as a deferred follow-up).

## Filesystem mapping

- **Library** = a registered root folder, `kind ∈ {manga, comic, gallery,
  mixed}`.
- **Series** = the first directory level beneath a library root (manga/comic
  libraries), *or* — for `kind=gallery` — a **two-level** scan:
  `<Artist>/<Work>/<files>`, where each work folder becomes its own Series,
  credited to the artist folder (`SeriesCredit(role="artist")`) and
  auto-grouped into a `Collection` named after the artist.
- **Book** = a readable item found walking a series folder to any depth: an
  archive file (`.cbz`/`.zip` only — see below) → a Book; a folder whose
  direct children are images → a loose-image Book (`ImageDirContainer`).
  Intermediate folders containing archives/sub-folders are grouping levels
  only, feeding volume/chapter parsing ([06](06-filename-parser.md)).
- **Only `.cbz`/`.zip` archives and image directories are supported** (plus
  `avif_dir` for downloaded content). RAR/7z/PDF/EPUB were decided **not
  planned** — no native-dep/licensing baggage for formats CBZ + directories
  already cover.
- **No embedded-metadata override.** There's no ComicInfo.xml/OPF-in-archive
  reading at all (`ingest/scanner.py` lists it as an explicit deferred
  follow-up) — the "ambiguity escape hatch" this ADR originally described
  for that purpose is instead `lychee.info` ([20](20-lychee-info-metadata.md)),
  a sibling YAML file, not an embedded override.

```
Library "Manga"  (root = /data/manga, kind = manga)
└── One Piece/                 → Series "One Piece"
    ├── Vol. 01/               → grouping only (feeds volume=1)
    │   ├── Ch.001.cbz         → Book + Chapter (volume 1, number 1)
    │   └── Ch.002.cbz         → Book + Chapter (volume 1, number 2)
    └── Extra/                 → grouping
        └── page01.jpg …       → Book + Chapter (loose-image directory)

Library "Cosplay"  (root = /data/cosplay, kind = gallery)
└── Some Cosplayer/            → Collection "Some Cosplayer" (artist credit)
    └── 2B (NieR:Automata)/    → Series "Some Cosplayer — 2B (NieR:Automata)"
        └── *.avif             → one Book, no Chapter (served as images)
```

## Physical binding & identity

- **Paths are stored relative to the library root** (`Book.path_rel`) so the
  library can be moved/remounted/Docker-remapped without rewriting rows.
- **Identity is a nanoid, never the path.** Move/rename resilience comes from
  `(file_size, partial_hash)` matching against soft-deleted `Book` rows —
  `partial_hash` is `xxh3_128` over the first 64 KiB + last 64 KiB + size
  (`ingest/scanner.py`). On restore, reading progress is snapshotted before
  soft-delete (`Book.restore_progress_json`) and re-applied on match.

## Schema (as built)

`backend/src/catalog/models.py`, `backend/src/progress/models.py`,
`backend/src/taxonomy/models.py`:

```python
library(id, name, path, kind[manga|comic|gallery|mixed], enabled,
        last_scan_at, options_json)

series(id, library_id→library, kind, title, sort_title, description,
       status[ongoing|completed|hiatus|cancelled],
       content_rating, demographic,               # system Tag ids — ADR 10
       year, origin_country, rating, user_rating,
       favorite, library_status,                  # per-user state, single-user v1
       total_chapters, available_chapters, chapter_index_at,
       path_rel, cover_source, provider, provider_series_id, external_ids_json,
       image_count, source, characters_json,       # gallery-only extras
       locked_fields_json, file_last_modified,
       metadata_file_hash, metadata_file_version)   # lychee.info gating

series_credit(id, series_id→series, name, role[author|artist], position)
title_variant(id, series_id→series, title, language,
              variant_type[native|romanized|english|alt], is_primary)

book(id, series_id→series, library_id→library, path_rel,
     content_kind[cbz|zip|image_dir|avif_dir],
     file_size, partial_hash, page_count, file_last_modified,
     deleted_at, restore_progress_json)

chapter(id, series_id→series, book_id→book, volume, number, number_sort,
        title, language, group_name, page_start, page_count,
        source_uploaded_at, comment_count, provider, provider_chapter_id)

provider_chapter(id, series_id→series, provider, provider_chapter_id,
                  volume, number, number_sort, title, language, group_name,
                  published_at, last_seen_at)   # cached remote chapter index

tag(id slug, name, group[genre|theme|content|format|content_rating|demographic],
    enabled, system)
tag_alias(id slug, name, tag_id→tag)
series_tag(series_id→series, tag_id→tag)         # series-level only, no book_tag

collection(id, name, description, provider, provider_list_id)
collection_series(collection_id→collection, series_id→series, position)

reading_progress(id, chapter_id→chapter UNIQUE, series_id→series,
                  current_page, completed)        # no user_id anywhere
```

Notably absent from the original sketch of this ADR: no `User` table (single
implicit user throughout — [12](12-auth-users.md)), no `ReadList` (only
series-level `Collection`), no `is_oneshot` flag (a loose archive directly
under a library root still becomes its own Series structurally, just without
an explicit boolean), no denormalized `book_count`/rollup columns (counts are
computed live in queries).

## Why this shape

Real nested layouts (`Series/Volume/Chapter.cbz`) resolve to one Series with
path-parsed volumes — no Volume entity, no per-volume Series explosion.
Paths relative to the library root plus hash-based move detection mean
reorganizing files on disk doesn't lose progress or metadata. Splitting
`Book`/`Chapter` keeps "physical container" and "reading unit" independent,
so multi-chapter archives are a future data-population problem, not a future
schema migration.
