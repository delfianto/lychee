# 04 — Database: SQLite (WAL) + FTS5 trigram

**Status:** Implemented, with one confirmed production gap — see "Known gap" below.

## What this is

SQLite via SQLAlchemy 2.0 + Alembic, in WAL mode. Media and thumbnails live
on the filesystem, never in the DB ([09](09-image-serving.md)) — the DB only
ever holds metadata, which is why even a very large library stays a small
database (metadata is ~1-2 KB/row; the filesystem carries the actual weight).

## Connection tuning

Set on every connection (`backend/src/core/persistence/database.py`, a
SQLAlchemy `connect` event listener):

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 30000;   -- raised from an initially-planned 5000 —
                                -- scans + cover warming can contend, 5s
                                -- was too short under a stuck writer
PRAGMA synchronous  = NORMAL;
```

No `cache_size`/`mmap_size`/`temp_store` tuning, no periodic `PRAGMA
optimize`/`VACUUM` — none of that materialized; the four pragmas above are
the whole tuning surface today.

## No per-page table

`Book.page_count` (int, set from listing the container's image entries at
scan time) + `ReadingProgress.current_page` are the only two integers this
needs — "how many pages" and "resume at page Y." Serving page N maps to a
container entry by listing + natural-sorting on demand, cached via
`functools.lru_cache` keyed on `(path, mtime)` (`media/containers.py`) —
no persisted page rows, no migration risk if per-page metadata is ever
wanted later.

## Full-text search: FTS5 `trigram`

`series_fts` (`backend/src/catalog/search_index.py`) is a **standalone,
own-content** FTS5 virtual table — not SQLite's `content=` external-content
mechanism, despite that being the original plan; it duplicates the indexed
text via insert/update/delete triggers on `series`, `title_variant`, and
`series_credit`:

```sql
CREATE VIRTUAL TABLE series_fts USING fts5(
  series_id UNINDEXED, title, alt_titles, authors,
  tokenize = 'trigram'
);
```

Three columns only — no `tags`, no `summary`/description; those aren't
searchable. `tokenize = 'trigram'` with no explicit options (not `trigram
case_sensitive 0 remove_diacritics 1` as originally planned — that
[17](17-search-fts.md) covers in more detail). Queried via `bm25(series_fts,
0.0, 10.0, 4.0, 1.0)` — title weighted highest, then alt-titles, then
authors. Queries under 3 characters (below trigram's minimum) fall back to a
plain `LIKE` title match (`catalog/repository.py:search_series`).

**Why `trigram`, not the default `unicode61` tokenizer:** `unicode61` has no
CJK word segmentation — a whole run of Japanese/Chinese/Korean text becomes
one token, so substring/partial matches fail, which matters a lot for manga
titles. `trigram` (built into SQLite since 3.34, bundled in Python 3.14's
SQLite) indexes 3-character sequences instead, giving CJK-capable substring
matching with no extra runtime dependency (no `pysqlite3-binary` pin needed
or present).

## Known gap: the FTS5 table is never created outside tests

`create_search_index()` (`catalog/search_index.py`) is called from
`tests/conftest.py` only. It is **not** called from `bootstrap()`
(`backend/src/bootstrap.py`), not from `seed.py`, and there's no Alembic
migration creating the virtual table either (`alembic/env.py` only
*excludes* `series_fts*` from autogenerate diffing — it doesn't create it).
So on a real deployed instance, `series_fts` likely never exists,
`fts_available()` returns `False`, and `/api/search` silently falls back to
`LIKE`-only matching — full-text search works in tests but not in
production. Worth fixing (wire `create_search_index` into `bootstrap()`) as
a follow-up; flagged here rather than silently documented as "done."

## Why SQLite over Postgres

Read-heavy, low-write-concurrency, one-or-a-few-users self-hosted workload —
SQLite's sweet spot. WAL gives concurrent readers alongside the one real
writer (the scan, serialized through the task queue in batched
transactions). A single-file DB means trivial backup and deploy, matching
the self-hosted ethos; Postgres's operational overhead (a service to run,
not a file to copy) buys concurrency/scale this workload doesn't need.
SQLAlchemy keeps a Postgres migration path open if that ever changes, but
nothing points that direction today.
