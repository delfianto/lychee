# lychee — Build Plan & TODO Tracker

> **Build plan & status tracker** (tracked in git). Living doc; update as we go.
> Legend: `[x]` done · `[~]` partial / needs wiring · `[ ]` not started

## Status snapshot (2026-07-25)
- **Frontend:** **fully API-driven** — `src/mocks/library.ts` is deleted; every view (Home,
  library grids, series/gallery detail, reader with progress writes, search, feeds, Lists, and all
  Settings tabs) reads/writes the backend via the generated `openapi-fetch` client. Typechecks clean.
- **Backend:** **feature-complete for the plan's core** — B0 conventions, B2 domain model + Alembic
  migration + seed, B3 AVIF pipeline, the full read API, ingest scan (parser + walk/diff/reconcile),
  synchronous download→AVIF pipeline + MangaDex page provider, reading-progress writes, and the
  Settings/collections/taxonomy/integrations APIs. **79 pytest, ruff + basedpyright clean.**
- **How to run:** `cd backend && uv run uvicorn src.main:app --reload` (auto-migrates + seeds) then
  `uv run python -m src.dev_seed` for a demo library; `cd frontend && bun run dev`.
- **Branch:** `docs/research-and-decisions` (local only, not pushed). Architecture: `notes/decisions/`
  (ADR 01–19).

## Remaining work (accurate — the genuine gaps)
1. **Functional (user-facing, small backend):**
   - [x] `PATCH /api/series/{id}` — favorite / library-status / personal rating now persist (migration
         b6a9fd5d added `user_rating`; SeriesDetail + GalleryDetail wired). ✅ done.
   - [ ] Download `pause`/`resume` endpoints (FE toggles status locally); `PUT /api/collections/{id}/series` reorder.
2. **Larger features (genuinely new work):**
   - [ ] MangaDex **metadata match/import** + `POST /api/series/{id}/refresh` + cover fetch (only chapter
         download of an already-linked series works today).
   - [ ] **Tracker OAuth + outbound sync** (connect is a stub; nothing pushes read status).
   - [ ] **Real sync** — `/api/sync` is a stub; check MangaDex for new chapters.
   - [x] **SSE** `/api/events` + `/api/tasks` + task tracker — scans emit live progress events. ✅ done.
   - [ ] **Background execution queue** — scans/downloads still run synchronously in the request; the
         tracker/SSE layer is done, only the fire-and-forget worker (APScheduler/ProcessPoolExecutor)
         remains. FE SSE consumption (live progress bars) also pending.
3. **Coverage:**
   - [ ] Containers RAR/7z/PDF/EPUB + `python-magic` content sniffing (ZIP/CBZ/image-dir/AVIF-dir only).
   - [~] Search is `LIKE`; **FTS5** (B6) for ranking/typo tolerance.
   - [ ] On-demand resize/transcode + disk render cache + page-list LRU (B3 caches).
4. **Fidelity / correctness:**
   - [~] Error shape is FastAPI `{"detail"}`, not the planned `{error:{code,message}}`.
   - [ ] Move-restore loses progress (chapters dropped on soft-delete; ADR 07 `tryRestore` migration
         not implemented). `partial_hash` is sha1-of-sample, not xxh3.
   - [~] Taxonomy seed is hand-curated MangaDex-aligned, not fetched from `/manga/tag`.
5. **FE polish + backlog:** see PART A remaining and PART E.

---

# PART A — Frontend: DONE (mockup **now wired to the API**)

- [x] **Shell/nav** — top-nav `AppShell` (Home · Reading · Favorites · Manga · Comics · Gallery ·
      Lists), icon-only below `xl`, mobile drawer, static brand, search → `/search`, random dice
      (`/api/series`), light/dark toggle, settings↔back, 404 route.
- [x] **Home dashboard** — stats + per-library storage · continue-reading · recent updates · recently
      added — all from `/api/dashboard` + `/api/libraries/summary`.
- [x] **Library** (`LibraryView`) — 3 density modes, shelf tabs, search + `FilterPanel` (tags from
      `/api/taxonomy`), saved presets (localStorage), active-filter chips, **server** filter/sort/
      cursor-pagination via `/api/series`.
- [x] **Gallery** — `GalleryView` + `GalleryDetail` + `Lightbox`, from `/api/series?kind=gallery` and
      `/api/series/{id}/images`.
- [x] **Reading / Unread** — reading shelf reuses `LibraryView`; unread feed via `/api/updates/unread`.
- [x] **Series detail** — hero + info panel + `ChapterList` (Related/Art tabs) from `/api/series/{id}`,
      `/chapters`, `/related`, `/art`. ⚠ action row (favorite/shelf/rating) not yet persisted — see gap #1.
- [x] **Reader** — modes/direction/fit/background; serves `/api/chapters/{id}/pages/{n}`; chapter
      selector + next; **writes progress** as pages turn.
- [x] **Lists** — `/lists` + `/lists/:id`, API-backed collections store.
- [x] **Settings** — General (libraries CRUD/scan, provider, trackers), Content (taxonomy table),
      Downloads (queue + sync), About — all on the API.
- [x] **Theming**, [x] **Transitions**.
- **Remaining FE polish:**
  - [~] Loading states (spinners on detail/gallery/home; grids show loading) — **error states largely
        missing** (API failures fail silently / empty).
  - [ ] Accessibility pass (focus rings, aria, keyboard nav).
  - [ ] Reader page preload / long-strip lazy-load.
  - [ ] Breakpoint/mobile QA sweep.
  - [ ] "Add to list" from series **cards** (only from detail/gallery-detail today).

---

# PART B — Backend

## B0. Cross-cutting conventions
- [x] camelCase JSON (`CamelModel`).
- [x] `nanoid` string ids.
- [x] Cursor pagination `{items, nextCursor}` for grids/feeds.
- [x] Page pagination `{items, total, page, pageSize}` (taxonomy → `OffsetPage`).
- [x] Image URLs are API paths (`/api/series/{id}/cover`, `/api/chapters/{id}/pages/{n}`).
- [x] **SSE** at `GET /api/events` (+ `/api/tasks`); task tracker emits scan progress.
- [x] No auth in v1 (single-user).
- [~] Errors: uses FastAPI `{"detail"}` via a `LycheeError` handler, **not** `{error:{code,message}}`.
      404 for missing / 400 for corrupt containers works.

## B1. Dependencies
- [~] **Images:** Pillow 12 (native AVIF) ✅ · pyvips ❌ (Pillow-only) · python-magic ❌.
- [ ] **Archives/formats:** only stdlib `zipfile` (CBZ/ZIP) + image dirs. rarfile/py7zr/pymupdf/ebooklib ❌.
- [~] **Ingest utils:** `hashlib` sha1 sample (not xxhash) · regex natural-sort (not natsort).
- [ ] **Tasks:** APScheduler / ProcessPoolExecutor ❌ (synchronous).
- [~] **Providers/trackers:** `httpx` ✅ (main dep) · tenacity ❌ (no retry/backoff).
- [~] **Search:** SQLite `LIKE` (FTS5 ❌).
- [x] Present: fastapi, uvicorn, sqlalchemy 2, alembic, pydantic 2 + settings, structlog, nanoid, httpx, pillow.

## B2. Domain model → first migration
- [x] Entities: Library, Series, Book, Chapter, Tag + series_tag, SeriesCredit, TitleVariant,
      ReadingProgress, Collection + CollectionSeries, Provider, Tracker, DownloadTask, SyncState.
- [x] Gallery = Series `kind=gallery` (image_count/source/characters; one image book; no chapters).
- [x] Derived (chapterCount/unreadCount/lastReadChapter/sizeGb/uses) computed in queries.
- [~] Taxonomy seed (MangaDex-aligned, **hand-curated** — not fetched from `/manga/tag`).
- [x] Repositories + services per slice; initial Alembic migration (`alembic check` clean).

## B3. Image pipeline + AVIF (ADR 19)
- [x] Downloaded images → content-aware AVIF, original discarded.
- [x] Content-aware presets (LINE_ART 4:0:0 / COLOR_ART 4:4:4 / PHOTO 4:2:0).
- [x] AVIF thumbnails, content-addressed sharded store, 320/640, idempotent + atomic.
- [~] Scanned archives not rewritten + AVIF thumbnails ✅; **on-demand resize/transcode → AVIF +
      diskcache ❌** (scanned pages served as original bytes).
- [x] Serving `pages/{n}` + `cover` with ETag + Cache-Control + 304.
- [x] Browser support (AVIF, webapp-only, no fallback).
- [~] Caches: thumbnail FS store ✅; page-list LRU + render/resize diskcache ❌.
- [ ] Encode on a ProcessPoolExecutor (currently inline; `encode` is pool-ready).

## B4. Ingest
- [x] Filename / volume-chapter parser (ADR 06) — decimals, ranges, specials, series-name subtraction.
- [~] `BookContainer` — image_dir + CBZ/ZIP + avif_dir ✅; RAR/7z/PDF/EPUB ❌; **extension-based**
      (no content sniffing).
- [x] Scan pipeline (walk → diff → reconcile, soft-delete + (size, partial_hash) restore) + library
      CRUD/scan API. ⚠ restore doesn't migrate reading progress (chapters dropped on soft-delete).
- [~] Task tracker + SSE progress events ✅; **background queue** (APScheduler, per-series
      serialization, ProcessPoolExecutor) ❌ — scans run synchronously in the request.

## B5. Providers + downloader
- [~] MangaDex provider: chapter listing + page download ✅; **metadata match/import + field mapping +
      cover fetch ❌**.
- [~] Chapter downloader → AVIF + DownloadTask rows ✅; **SSE progress ❌** (synchronous; statuses are
      done/failed, not live downloading/queued/paused).
- [ ] **Sync** — `/api/sync` is a stub (stamps timestamp); no real new-chapter check.

## B6. Search
- [~] `GET /api/search` works via `LIKE` over titles; **FTS5 trigram over title/alt-titles/authors ❌**.

## B7. Reading progress + trackers
- [x] Progress writes (`PUT /api/chapters/{id}/progress`) → unread / lastRead / continue-reading.
- [ ] Outbound tracker sync + OAuth — **connect/disconnect are stubs**; nothing pushes read status.

---

# PART C — API contract

### Series & library grids
- [x] `GET /api/series` (all filters, 5 sorts, cursor).
- [x] `GET /api/series/{id}`.
- [x] `PATCH /api/series/{id}` `{favorite?, libraryStatus?, rating?}` — favorite/shelf/user-rating persist.
- [ ] `POST /api/series/{id}/refresh` — not built (needs provider match).
- [x] `GET /api/series/{id}/chapters` → VolumeGroup[].
- [x] `GET /api/series/{id}/related`.
- [x] `GET /api/series/{id}/art` (returns `{images: []}` placeholder — no art store yet).
- [x] `GET /api/series/{id}/images` (cursor).
- [x] `GET /api/series/{id}/cover?size=`.

### Chapters / reader
- [x] `GET /api/chapters/{id}`.
- [x] `GET /api/chapters/{id}/pages/{n}` (ETag/304).
- [x] `PUT /api/chapters/{id}/progress`.

### Feeds & dashboard
- [x] `GET /api/updates`, [x] `GET /api/updates/unread`, [x] `GET /api/dashboard`.

### Search
- [~] `GET /api/search` (LIKE, not FTS5).

### Collections (Lists)
- [x] GET/POST `/api/collections`, [x] GET/PATCH/DELETE `/api/collections/{id}`,
      [x] POST/DELETE `/api/collections/{id}/series[/{sid}]`.
- [ ] `PUT /api/collections/{id}/series` reorder.

### Settings
- [x] **Libraries** GET/POST/PATCH/DELETE + `/summary` + scan/scan-all.
- [x] **Taxonomy** GET(paged)/POST/PATCH/DELETE (system rows protected; uses counts).
- [x] **Providers** GET/PATCH.
- [~] **Trackers** GET/PATCH/connect/disconnect ✅ — **connect is a stub (no real OAuth)**.
- [~] **Downloads** GET/POST/DELETE/clear-completed/retry ✅ — **pause/resume endpoints ❌**.
- [~] **Sync** GET/POST ✅ — **stub (no real check)**.
- [x] **About** GET.
- [x] Appearance/Reader/Theme/Density/Language client-side (localStorage).

### Live
- [x] `GET /api/events` (SSE) — task tracker emits `<kind>.started/progress/done/failed`.
- [x] `GET /api/tasks` — recent/running task snapshot.

---

# PART D — Integration
- [x] `openapi.json` (`scripts/dump_openapi.py`) → `openapi-typescript` → `src/api/schema.d.ts` +
      `openapi-fetch` client; Vite proxies `/api`.
- [~] State: API-backed collections **store** + `src/api/queries.ts` composables for series/feeds/
      downloads/settings (functionally equivalent to per-domain stores); theme/reader/toast singletons.
- [x] Swapped every view off `src/mocks/library.ts`; **mocks deleted**.
- [~] Filters/search/sort/cursor/presets/real-covers/AVIF-pages/reading-progress ✅; **SSE progress ❌,
      tracker sync ❌, series PATCH ❌**.

# PART E — Backlog / later
- [ ] Auth & multi-user (ADR 12).
- [~] Tests: backend 79 pytest ✅; **FE component tests ❌**.
- [ ] Docker packaging.
- [—] OPDS / device-sync (explicitly out per ADR 15).
- [ ] JPEG page fallback endpoint (only if a non-webapp client appears).
- [ ] Drag-reorder in lists · per-page reader thumbnails.
- [x] Formalize AVIF policy as **ADR 19**.
- [ ] Scrub any leftover "ebook/Books" wording.

---

## Build order — status
1. [x] **B0 conventions + B1 deps** (Pillow; other media deps deferred per-feature).
2. [x] **B2 domain model + migration + seed.**
3. [x] **B3 AVIF pipeline** (encode/presets/thumbnails/containers/serving). ADR 19.
4. [x] **Read-only API slice + client + FE swap of every read view.**
5. [x] **B4 ingest** — parser + scan + library API. (Task runner, RAR/PDF/EPUB, content-sniff, FTS
       deferred; scans synchronous.)
6. [x] **B5 providers + downloader** — download→AVIF pipeline + Downloads API + MangaDex page provider.
       (Metadata match/import, real sync, background queue + live progress deferred.)
7. [~] **B7 + settings** — progress writes, series PATCH (favorite/shelf/rating), providers/trackers/
       sync/about/taxonomy/collections APIs, SSE + task tracker, FE Lists + Settings swapped.
       **Remaining: tracker OAuth + outbound sync, real sync + MangaDex import, background task queue
       + FE SSE consumption, FTS5, extra containers.**

## Handy commands
- Backend: `cd backend && uv run uvicorn src.main:app --reload` (auto-migrates+seeds).
  Demo data: `uv run python -m src.dev_seed`. Checks: `uv run ruff check . && uv run basedpyright && uv run pytest`.
- Regen API client: `cd backend && uv run python scripts/dump_openapi.py` then `cd frontend && bun run api:gen`.
- Frontend: `cd frontend && bun run dev` (proxies /api → :8000). `bun run typecheck`.
