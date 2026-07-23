# Reference Research — Cross-Project Overview

> Deep-dive study of four self-hosted manga/comic/ebook servers, to inform the architecture of **lychee**
> (planned: Python 3.14 / FastAPI / SQLAlchemy + Alembic / SQLite).
> Analysis date: 2026-07-23. Sources cloned under `temp/` (gitignored).

## How to read these notes

- **Per-project deep dives** (one folder each, source-cited):
  - [`komga/`](komga/README.md) — the reference implementation (+ [`schema.md`](komga/schema.md))
  - [`kamiyomu/`](kamiyomu/README.md) — the contrast case (crawler/downloader, not a scanner)
  - [`mango/`](mango/README.md) — the minimalist filesystem-first server
  - [`lanraragi/`](lanraragi/README.md) — the archive-centric outlier (+ [`redis-schema.md`](lanraragi/redis-schema.md))
- **External-API research** (not a codebase — a data source to consume):
  - [`mangadex-api/`](mangadex-api/README.md) — MangaDex API: metadata backbone + optional chapter downloader; seeds the [10](decisions/10-tagging-content-rating.md) taxonomy.
- **Per-aspect overviews** (compare all four, then recommend for lychee):
  1. [Stack](01-stack.md)
  2. [Media management model](02-media-management.md)
  3. [File management & sync](03-file-management-sync.md)
  4. [Reading tracker](04-reading-tracker.md)
  5. [Metadata & tagging](05-metadata-tagging.md)
  6. [Media scan & filename structure](06-scan-and-filenames.md)
  7. [Image decoding & archives](07-image-decoding.md)

---

## The four projects at a glance

| | **Komga** | **KamiYomu** | **Mango** | **LANraragi** |
|---|---|---|---|---|
| Version studied | 1.25.0 | main (early) | 0.27.0 | 0.9.x |
| Language | Kotlin 2.2 | C# / .NET 8 | Crystal 1.0 | Perl 5.36 |
| Web framework | Spring Boot 3.5 | ASP.NET Core 8 | Kemal 1.0 | Mojolicious 9.39 |
| Frontend | Vue 2.6 + Vuetify (SPA) | Razor + HTMX + SignalR | ECR server-render | TT2 + jQuery→Preact |
| Datastore | **SQLite** (jOOQ) + Lucene | **LiteDB** (documents) | **SQLite** (raw SQL) | **Redis** (5 DBs) |
| Migrations | Flyway (SQL + Kotlin) | none | `mg` (numbered) | none |
| Orientation | **scan & index** | **crawler / download** | **scan & index** | **scan & index** (archives) |
| Media model | Library→Series→Book | Library(=1 manga)→Chapter | Library→Title→Entry | flat archive + tags |
| Grouping extras | Collections, ReadLists, one-shots | — | nested Titles | Categories, Tankoubon |
| Background jobs | SQLite task queue + thread pool | Hangfire (SQLite) | Crystal fibers | Minion (Redis) |
| File watching | none (polling) | none (owns files) | none (polling) | **Shinobu** (inotify) |
| File identity | XXH3-128 (full file) + size | none (creates files) | **inode** + dir signatures | **SHA-1 of first 512 KB** |
| Progress model | per-book **per-user** + R2Locator | per-chapter/page (single) | `info.json` per-title/user | per-archive (single shared) |
| Progress sync out | **KOReader, Kobo** | Kavita push, Gotify | none | Tachiyomi (plain REST) |
| Embedded metadata | ComicInfo.xml, EPUB OPF, Mylar, ISBN | writes ComicInfo only | none | ComicInfo + plugins |
| External scraping | none (embedded only) | none (crawler only) | via JS download plugins | **plugin scrapers** (EH/nhentai/…) |
| Filename parsing | none — natural sort + metadata | none (crawler) | **ChapterSorter** (smart) | **RegexParse** (doujinshi) |
| Archive formats | ZIP, RAR4/5, PDF, EPUB | CBZ only (+PDF/EPUB export) | ZIP, RAR | ZIP/RAR/7z/tar/…, PDF, EPUB |
| Image pipeline | ImageIO + TwelveMonkeys/nightmonkeys | SkiaSharp/native | image_size.cr | **libvips** / ImageMagick |
| Thumbnails | SQLite BLOB, 4 sizes | LiteDB blob, no resize | SQLite BLOB, 1 size | **filesystem** (sharded), 1 size |
| Search | **Lucene** (n-gram, CJK) | LiteDB `Contains` | tag filter only | Redis `KEYS` (O(N)) |
| Multi-user | **yes** (roles, restrictions) | no | yes | no (one shared account) |
| OPDS | v1.2 + v2.0 + WebPub | v1.2 | v1 catalog | Atom + Tachiyomi REST |
| License | AGPL-3.0 | AGPL-3.0 | MIT | (MIT-style) |

---

## Three archetypes

The four projects are not four variants of one thing — they represent **three different product shapes**, and lychee has to pick one deliberately.

1. **Scan-and-index server** (Komga, Mango, LANraragi). The filesystem is the source of truth; the app discovers files, extracts metadata, and serves them. **This is what lychee is.** Komga is the mature relational take; Mango the minimalist take; LANraragi the flat archive-hash take.
2. **Crawler/downloader** (KamiYomu). The app *creates* the files by downloading from source sites via plugins, so it never needs a scanner and every byte of metadata comes from the crawler. Useful as a contrast and as a source of good sub-patterns (decimal chapters, OPDS, outbound webhooks, path templating), but its overall shape is **not** lychee's.
3. **Archive-centric tag store** (LANraragi). A special case of #1 where there is *no* series/volume hierarchy at all — one archive = one entry, organized purely by namespaced tags, saved-search "categories", and manually-ordered "tankoubon". Excellent for doujinshi, weak for long-running series.

**Implication for lychee:** build a scan-and-index server with a proper relational hierarchy (like Komga), but keep a first-class "standalone/one-shot" entry type and a namespaced-tag system (like LANraragi) so both long series and loose doujinshi are first-class.

---

## Cross-cutting consensus → safe defaults for lychee

Where multiple independent projects converge, treat it as a validated default:

- **SQLite is the right embedded database.** Komga and Mango both use it; even KamiYomu's Hangfire and LANraragi's tooling lean on SQLite. LiteDB (KamiYomu) and Redis-as-DB (LANraragi) are the outliers and both regretted the lack of migrations / relational queries. → **SQLAlchemy + SQLite + Alembic.**
- **Decimal chapter numbers are mandatory.** Komga (`numberSort` float), KamiYomu (`decimal`), Mango (BigDecimal in ChapterSorter) all handle `10.5`. → store a numeric `number_sort` (float/decimal) distinct from the display label.
- **Separate display label from sort key.** Komga `NUMBER` (display str) vs `NUMBER_SORT` (float); Mango `title` vs `sort_title`. → every orderable entity gets `title` + `sort_name`/`number_sort`.
- **Natural sort everywhere.** All four natural-sort page filenames inside archives and entries within a series. → adopt Python `natsort` (or a ported comparator) as the single ordering primitive.
- **ComicInfo.xml is the interop standard.** Komga reads it, KamiYomu writes it, LANraragi has a plugin for it. → parse it on import and write it on export from day one.
- **Background work belongs off the request path.** Every project has an async mechanism (task queue / fibers / Minion / Hangfire) for scans, thumbnails, and imports. → pick a Python task runner early.
- **OPDS is table stakes.** All four expose OPDS. → implement OPDS 1.2 (JSON OPDS 2.0 optional).
- **Serve pages with ETag/`Cache-Control`.** Mango and Komga both do content-addressed caching of page images. → cheap win, do it.

---

## Cross-cutting divergences → decisions lychee must make

| Decision | Options seen | Leaning for lychee |
|---|---|---|
| **File identity across move/rename** | full-file hash+size (Komga) · inode + 3-step fallback (Mango) · 512 KB SHA-1 content ID (LANraragi) · none (KamiYomu) | Hybrid: DB surrogate id + stored `(size, partial_hash)` for restore-on-rename; **avoid** inode-only (unstable across remounts) and **avoid** 512 KB-only hash (false collisions). See [03](03-file-management-sync.md). |
| **Change detection / freshness** | periodic polling (Komga, Mango) · filesystem watcher (LANraragi/Shinobu) · daily re-crawl (KamiYomu) | **Both**: `watchfiles` watcher for latency + periodic full scan for correctness on NFS/SMB (Komga documents why watchers are unreliable on network mounts). |
| **Thumbnail storage** | SQLite BLOB (Komga, Mango, KamiYomu) · sharded filesystem dirs (LANraragi) | **Filesystem**, content-addressed, hash-prefixed dirs (LANraragi layout) — lets nginx/CDN serve them and keeps the DB small. |
| **Reading progress store** | relational per-user (Komga) · `info.json` files (Mango) · single shared int (LANraragi) · single-user doc (KamiYomu) | **Relational, per-user from day one** (`reading_progress(user_id, book_id, page, completed, locator, updated_at)`). |
| **Search** | Lucene (Komga) · SQL `Contains`/tag-only (Mango, KamiYomu) · Redis `KEYS` (LANraragi) | **SQLite FTS5** for phase 1; note Komga *dropped* FTS5 for Lucene specifically for **CJK n-gram** support — plan an escape hatch (Tantivy/Meilisearch) if CJK matters. |
| **Numbers from filename vs metadata** | metadata-authoritative, no filename regex (Komga) · smart filename parser (Mango ChapterSorter, LANraragi RegexParse) | **Both**: prefer embedded metadata; fall back to a filename parser (port ChapterSorter + a doujinshi/volume-chapter regex layer). |
| **Metadata acquisition** | embedded-only (Komga) · plugin scrapers (LANraragi) · crawler (KamiYomu) | Phase 1 embedded (ComicInfo/OPF) + manual edit with **field locks** (Komga's lock-flag pattern); plugin scrapers later. |

---

## Recommended starting architecture for lychee (synthesized)

A Komga-shaped core, with LANraragi's tag/collection ideas and Mango's/KamiYomu's best sub-patterns, on a Python stack:

- **Domain hierarchy:** `Library → Series → Book → Page`, plus `Collection` (ordered series groups) and `ReadList`/`Tankoubon` (ordered cross-series book lists), plus a first-class **one-shot** book type (Komga's virtual-series trick). Namespaced tags (`artist:`, `series:`, `language:` …) as a relational M2M, not a comma string.
- **Persistence:** SQLAlchemy 2.0 + SQLite, Alembic migrations, FTS5 virtual table for search. Thumbnails on the filesystem.
- **Identity & sync:** surrogate id + `(file_size, partial_hash)` for rename-restore; soft-delete + "trash" so progress/metadata survive reorganizations (Komga); `watchfiles` watcher + scheduled full scan.
- **Ingestion pipeline:** walk → detect container (Tika-equivalent/`python-magic`) → extract page list (natural sort) → read `ComicInfo.xml`/EPUB OPF → assign `number_sort` → generate cover thumbnail → index into FTS5. Heavy steps run in a task queue keyed per-series (Komga's group-id serialization).
- **Containers/images:** `zipfile` (CBZ) + `rarfile`/`libarchive-c` (CBR/7z) + `pypdf`/`pymupdf` (PDF) + `ebooklib` (EPUB); **pyvips** or Pillow(+pillow-heif) for decode/resize; stream pages, don't buffer whole archives.
- **Reading & sync:** per-user progress with a Readium-style `locator` JSON for EPUB; expose a Tachiyomi/Mihon-friendly REST surface (LANraragi shows it's "just the REST API"); plan KOReader + Kobo sync (Komga documents the exact hashes/protocols) as opt-in.
- **API & auth:** REST + OPDS 1.2; multi-user with roles/content-restrictions from the start (Komga) — retrofitting users (KamiYomu, LANraragi) is painful.

---

## Standout ideas worth stealing (with source)

- **One-shot = virtual series** wrapping the file itself — Komga (`FileSystemScanner`).
- **Soft-delete + hash-based restore** so moves/renames keep progress, metadata, collection membership — Komga (`tryRestoreBooks`).
- **`ChapterSorter`**: infer prefix+number keys across a title's filenames, rank by frequency/range, multi-key numeric sort — Mango (`src/util/chapter_sort.cr`).
- **3-step ID lookup** (path+sig → path → sig+path-similarity) — Mango (`src/storage.cr`).
- **Tankoubon as ordered collection with a single global progress cursor** mapping to `(archive, local_page)` — LANraragi.
- **Namespaced tags + tag-rewrite rules + saved-search "dynamic categories"** — LANraragi.
- **Per-field metadata lock flags** so auto-import never clobbers manual edits — Komga.
- **Group-id task serialization** (per-series tasks run sequentially, others parallel) — Komga (`TaskProcessor`).
- **Watcher + job-queue split** as two processes/services — LANraragi (Shinobu + Minion).
- **"Hide completed" at 85% of pagecount** — LANraragi.
- **Path/filename templating** for downloaded/exported files (`{manga_title}/… Ch.{chapter_padded_4}`) — KamiYomu.
- **Outbound webhooks** (trigger a Kavita rescan; Gotify push) — KamiYomu.

## Anti-patterns to avoid (with source)

- Progress/metadata in JSON sidecars → not queryable, write-contention, lost on rescan — Mango `info.json`.
- Thumbnails as SQLite BLOBs → DB bloat, no CDN/nginx caching — Komga, Mango, KamiYomu.
- Redis-as-only-database / no migrations → no referential integrity, `KEYS` O(N) search — LANraragi; LiteDB no-migrations — KamiYomu.
- Single shared reading progress / single-user baked in → painful to retrofit — LANraragi, KamiYomu.
- 512 KB-only content hash → false-collision risk — LANraragi.
- inode-only identity → breaks across remounts/filesystem moves — Mango (mitigated by fallback).
- Buffering whole pages/archives into memory to serve — KamiYomu (`MemoryStream`).
- `KEYS`/`Contains` search that can't scale or do CJK — LANraragi, Mango, KamiYomu.
