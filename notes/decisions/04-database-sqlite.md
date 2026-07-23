# 04 — Database: SQLite (WAL) + FTS5 trigram

**Status:** ✅ Accepted (with the tuning + search plan below)

## Context

We want a zero-ops, single-file, self-hosted-friendly database, consistent with the two mature scan-index references (Komga, Kavita both ship **SQLite** in production). Two real questions drove this ADR:

1. Can SQLite handle **lots of books / huge collections**?
2. Can it provide **proper, fast full-text search**?

Short answers: **yes**, and **yes with the right tokenizer** — details below.

## Decision

- **SQLite** via SQLAlchemy 2.0 + Alembic, in **WAL mode**.
- **Media and thumbnails live on the filesystem**, never in the DB (see [07](../07-image-decoding.md)) — so the DB only ever holds *metadata*.
- **No per-page rows** — store `page_count` on the `book` and the current page on the reading-progress row; derive the page↔archive-entry mapping on demand (see below).
- **A single serialized writer** for scans/imports (run in the task queue, batched in transactions); many concurrent readers.
- **Full-text search via FTS5 using the `trigram` tokenizer** (CJK-capable), kept behind a small swappable search interface so we can move to Tantivy/Meilisearch later if ever needed.

---

## Can SQLite handle huge collections?

**Yes, comfortably, for this workload.** Reasons:

- **It stores metadata only.** Files stay on disk, thumbnails stay on disk. So even a very large library is a *small* database. Rough sizing: ~1–2 KB/row of metadata → **200k books ≈ a few hundred MB**; the theoretical SQLite size ceiling (hundreds of TB) is irrelevant here.
- **Proven in the field.** Komga and Kavita both run SQLite for large real-world comic/manga libraries (hundreds of thousands of books). This is the *exact* workload, already validated.
- **Read-heavy, low write-concurrency.** A media server is browse/read dominated with bursty writes (a scan, the occasional progress update) from **one or a few users**. That is SQLite's sweet spot:
  - **WAL mode** gives concurrent readers + one writer without blocking each other.
  - The only heavy writer is the **scan** — run it as a **single serialized worker** and wrap inserts in **batched transactions** (thousands of rows per commit). This avoids `SQLITE_BUSY` and is dramatically faster than autocommit.
  - Use `busy_timeout` so any incidental writer waits rather than errors.

**Tuning baseline** (set on every connection / at startup):

```sql
PRAGMA journal_mode = WAL;        -- concurrent reads + 1 writer
PRAGMA synchronous  = NORMAL;     -- safe with WAL, much faster than FULL
PRAGMA busy_timeout = 5000;       -- wait up to 5s instead of erroring
PRAGMA foreign_keys = ON;
PRAGMA cache_size   = -65536;     -- ~64 MB page cache (negative = KiB)
PRAGMA mmap_size    = 268435456;  -- 256 MB memory-mapped I/O
PRAGMA temp_store   = MEMORY;
-- periodically: PRAGMA optimize;  (and ANALYZE; occasional VACUUM)
```

Plus: correct **indexes** on the hot query paths (library/series FKs, `number_sort`, `updated_at`, tag joins), and `PRAGMA optimize` on close.

### <a id="open-page-storage"></a>Page storage — DECIDED: no page table

The row count that could get large is **pages**: one row per page means `200k books × ~180 pages ≈ 36M rows` — multiple GB that dwarfs every other table and makes scans and backups heavier.

**Decision: do not store per-page rows.** lychee's actual requirement is only "this book has X pages" and "resume at page Y", which needs just two integers:

- `book.page_count` — obtained by listing the archive's image entries at scan time (cheap).
- `reading_progress.current_page` per (user, book), plus a `locator` JSON for reflowable EPUB where "page" is ill-defined.

Serving page N maps "page N" → an archive entry by **listing + natural-sorting the container on demand**, with the sorted entry list **cached** per open book (memory/disk) — no persisted rows. This is what Mango, LANraragi, and KamiYomu do; only Komga materializes pages, and it gates the expensive parts (`analyzeDimensions`, `hashPages`) behind opt-in flags anyway.

**Deferred, and all addable later without a schema break:** per-page dimensions (spread/webtoon layout — the client learns them as it loads each image, or compute on demand), per-page thumbnails (generate on demand → filesystem cache, LANraragi-style), and cross-book duplicate-page detection. If any becomes a real requirement, add a **rebuildable `page` *cache* table** then — it is fully derivable from the archive, so it's a non-breaking additive change, not a migration risk.

### When SQLite would *not* be enough

Only if lychee grows into **many concurrent writers**, **multi-node/HA**, or **millions of books with heavy write churn** — none of which are in the self-hosted scope. That's the Postgres threshold (and TBM already shows our Postgres pattern if we ever need it). The SQLAlchemy layer keeps that migration path open.

---

## <a id="fts"></a>Can it do proper, fast full-text search?

**Yes — SQLite's built-in FTS5 is a real inverted-index search engine**, not a `LIKE` hack:

- BM25 relevance ranking, prefix (`term*`), phrase (`"a b"`), boolean (`AND/OR/NOT`) queries, and `MATCH` syntax.
- **External-content tables** index existing columns without duplicating the data; triggers keep the index in sync.
- Millisecond queries over hundreds of thousands of documents — more than enough here.

**The one real gotcha (and how we solve it):** Komga *tried FTS5 in 2021 and dropped it after 9 days for Lucene* — because the default `unicode61` tokenizer has **no CJK word segmentation** (Japanese/Chinese/Korean text has no spaces, so a whole run becomes one token and substring/partial matches fail). For manga titles this matters a lot.

**Solution: the FTS5 `trigram` tokenizer** (built into SQLite since **3.34.0**, Dec 2020 — it did not exist when Komga chose Lucene). It indexes 3-character sequences, giving **substring and CJK partial matching** that `unicode61` can't. Options:

- **`trigram` everywhere** — simplest; great CJK + substring; caveat: queries need ≥3 chars for the fast path, and the index is larger.
- **Hybrid** — `unicode61` (word/prefix search for Latin titles, tags, authors) + a `trigram` index for CJK/substring. Best quality, a bit more plumbing. → **Resolved: `trigram` everywhere** ([17](17-search-fts.md)); hybrid kept as an escape hatch.

**Practicalities:**
- **FTS5 must be compiled into the SQLite build.** It is enabled by default in the SQLite amalgamation and in CPython's bundled `sqlite3` on modern builds; `trigram` needs SQLite ≥ 3.34 (Python 3.14 bundles a much newer SQLite). If a target platform's SQLite is old/without FTS5, ship **`pysqlite3-binary`** (bundles a current SQLite with FTS5 + trigram) to pin it.
- **SQLAlchemy** doesn't model FTS5 virtual tables natively — create them and their sync triggers via **raw DDL in an Alembic migration**, and query with `... MATCH :q ORDER BY rank`.
- Pair FTS with a typed **faceted filter API** (Komga's `SearchCondition` idea) for structured filters (library, tag, author, status, language, read-state).

### Escape hatch

Keep search behind an interface (`search_books(query, filters) -> ids`). If we ever outgrow FTS5 — needing typo tolerance, synonyms, advanced CJK analysis, or very large scale — swap the implementation for **Tantivy** (`tantivy-py`, embeddable, Lucene-like — closest to Komga's choice) or **Meilisearch/Typesense** (external service). No schema change to the rest of the app.

## Consequences

- Single-file DB: trivial backup (`VACUUM INTO` / file copy), trivial deploy — matches the self-hosted ethos.
- FTS5 + trigram gives proper, fast, **CJK-capable** search with **zero extra runtime dependencies**.
- Migration paths (Postgres for scale, Tantivy/Meili for search) are pre-identified and isolated behind SQLAlchemy + the search interface.

## Alternatives considered (from research)

- **PostgreSQL** (TBM's DB; `tsvector`/`pg_trgm`): more capable and better at heavy concurrency/CJK, but operational overhead that's overkill for single-user self-hosting. Reserved as the scale escape hatch.
- **Redis-only** (LANraragi): rejected — no relations, no migrations, `KEYS`-based O(N) search.
- **LiteDB-style document store** (KamiYomu): rejected — no migration tooling, opaque queries.
