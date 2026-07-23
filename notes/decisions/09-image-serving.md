# 09 — Image, thumbnail & page-serving pipeline

**Status:** ✅ Accepted

## Context

The last piece of the ingest→serve path: how lychee reads pages out of containers, generates thumbnails, and serves page images to the reader. Builds on [02](02-backend-stack.md) (media libs), [04](04-database-sqlite.md) (thumbnails on the **filesystem**, never DB BLOBs; no page rows), [05](05-domain-model.md) (loose-image books; series-cover selection; cover overrides), [07](07-scan-pipeline.md) (scan enqueues thumbnails), [08](08-task-runner.md) (CPU work → `ProcessPoolExecutor`). Research: [../07-image-decoding.md]. Anti-patterns to avoid, all surfaced there: DB-BLOB thumbnails (Komga/Mango/KamiYomu), whole-archive buffering (KamiYomu), uncached PDF renders (Komga).

## Decision

### 1. Container abstraction (Strategy)
One `BookContainer` protocol over every type, chosen by **content-detected** kind (`python-magic`), not extension:
```
list_pages() -> [PageEntry(name, media_type)]     # ordered
read_page(index) -> (stream, media_type)          # ONE entry, streamed
page_count() -> int
```
Impls: `zipfile` (CBZ/ZIP), `rarfile`|`libarchive-c` (CBR/RAR), `libarchive-c`|`py7zr` (7z), `pymupdf` (PDF — renders pages), `ebooklib`/zip (EPUB), filesystem dir (loose-image `DirEntry`, [05](05-domain-model.md)). Extraction is **always a single streamed entry — never buffer the whole archive** (KamiYomu's `MemoryStream` mistake).

### 2. Page ordering
Natural sort of image entries, then LANraragi's reordering: **cover to front** (`cover` regex, excluding back/rear/recover), **credits / `999*` to back**; strip macOS junk (`__MACOSX/`, `._*`). Computed once per book and cached (§6). No page rows ([04](04-database-sqlite.md)) — this ordered list is derived, cached, and rebuildable.

### 3. Decode / encode
**pyvips (libvips)** primary — fast, low-memory, streaming resize (LANraragi's choice); **Pillow (+pillow-heif)** fallback for format coverage (HEIF/AVIF/…). Thumbnails written as **WebP** (JPEG fallback). Full pages are served as their **original bytes by default** (lossless, fast); transcode/resize only on demand (§5). Decode guards (max-pixel limit) protect against decompression bombs.

### 4. Thumbnails
- **What:** a cover thumbnail per book; a **series cover** derived from its selected book's cover (05 selection strategy). **Two sizes** — `cover` (~320 px longest edge, for grids) and `detail` (~640 px). Configurable, deliberately few: the reader loads full pages directly, so we don't need Komga's four sizes.
- **Storage — filesystem, content-addressed, sharded** (LANraragi layout):
  ```
  <thumb_dir>/<id[:2]>/<id>.cover.webp
  <thumb_dir>/<id[:2]>/<id>.detail.webp
  ```
  The path is **derived from the id** — not a DB BLOB, not even a stored path row — so nginx/CDN can serve it and the DB stays small.
- **Generation:** low-priority, **idempotent** tasks enqueued by the scan ([07](07-scan-pipeline.md)/[08](08-task-runner.md)); CPU work runs in the `ProcessPoolExecutor`. A "regenerate thumbnails" admin task exists.
- **Fallback (Mango):** if the thumbnail file is missing, serve `thumbnail || first_page` (extract page 1 live) so a cover always renders, even before generation.
- **Overrides (Komga):** a user-uploaded or sidecar cover sets `cover_source` (`generated | sidecar | user`) on the book/series so regeneration never clobbers a manual/sidecar cover.

### 5. Page serving (the reader hot path)
- `GET /api/books/{id}/pages/{n}` → `read_page(n)` streamed with the correct content-type (`StreamingResponse`).
- **Caching:** `ETag` (page content hash, or `book.partial_hash` + index + transform params) + `Cache-Control: public, max-age`; return **304** on `If-None-Match` (Mango). Loose-image dirs are mutable → weaker validator (include mtime), shorter cache.
- **On-the-fly resize/transcode — off by default:** serve originals. If a `?w=` / reader-quality setting is present (LANraragi's `enable_resize` / `readerquality`), resize/recompress via pyvips and **cache the result** on disk.
- **PDF:** render page *n* via `pymupdf` at a target DPI and **cache the render** — explicitly fixing Komga's uncached-render cost.
- **Prefetch (optional):** the reader prefetches the next N pages; the server may warm the page cache after a request (LANraragi's `cbw_prefetch`).

### 6. Caches — three, distinct
1. **Ordered page-list** — in-memory LRU per book (avoids re-listing archives on every page turn).
2. **Thumbnail store** — filesystem, permanent, sharded (§4).
3. **Rendered/resized page cache** — filesystem, size-capped/evictable (`diskcache`), **only** for PDF renders and on-demand resizes; originals live on disk and are served directly.

All three are rebuildable — safe to clear at any time.

### 7. Errors (Komga taxonomy)
A corrupt / encrypted / unsupported container gives the book an **error state** during the scan ([07](07-scan-pipeline.md)); page requests then return a clear error/placeholder, not a 500. Missing index → 404; a single-page decode failure → placeholder + log, not a whole-book failure.

## Consequences

- Thumbnails off the DB → small DB, CDN/nginx-cacheable images.
- Single-entry streamed extraction → **constant memory regardless of archive size**.
- PDF renders and resizes are cached → the two expensive paths are paid once.
- pyvips keeps decode/resize fast and memory-light; Pillow covers the format long tail.
- Page-list / thumbnail / render layers are all rebuildable caches.

## Follow-ups

- **Per-page thumbnails** (reader page-grid/strip) — deferred; same sharded layout (`<id>/<page>.webp`), generated on demand.
- **Spread / webtoon layout hints** need page dimensions — compute on demand or client-side ([04](04-database-sqlite.md) discussion); revisit only if the reader needs them server-side.
- Exact thumbnail sizes and default reader quality — tune against real content.

## Alternatives considered

- **DB-BLOB thumbnails** (Komga/Mango/KamiYomu) — rejected: DB bloat, no CDN offload.
- **Whole-archive buffering** (KamiYomu) — rejected: memory blowup on large books.
- **Per-format hand-rolled decoders / ImageIO SPI** (Komga) — unnecessary in Python; the container libs + pyvips + Pillow cover it.
- **No render cache** (Komga's PDF path) — rejected: we cache renders and resizes.
