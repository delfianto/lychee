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
  Settings/collections/taxonomy/integrations APIs. **86 pytest, ruff + basedpyright clean.**
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
   - [ ] **MangaDex full integration** — metadata match/import + `/refresh` + covers, download
         enhancements, OAuth2 account + follows/status import, and real sync (flag new chapters).
         **Planned in detail in PART F below.**
   - [ ] **Tracker OAuth + outbound sync** for AniList/MangaUpdates/MAL (connect is a stub; nothing
         pushes read status) — distinct from MangaDex; MangaDex `links` (PART F/M1) feed the match.
   - [x] **SSE** `/api/events` + `/api/tasks` + task tracker — scans emit live progress events. ✅ done.
   - [x] **Background execution queue** — `src/tasks/queue.py` runs scans + downloads on a worker
         thread (own session, serial for SQLite); POSTs return `202 + TaskOut` and stream progress
         via SSE. FE consumes `/api/events` (shared `EventSource`, activity indicator, refetch on
         `*.done`). ✅ done. (Only a persistent/multiprocess queue + pause/resume remain — see below.)
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
- [x] Task tracker + SSE progress events ✅; **background queue** ✅ — scans run on a worker thread
      (`src/tasks/queue.py`), POST returns `202 + TaskOut`. (In-process/serial; a persistent or
      ProcessPoolExecutor queue is a later scaling concern.)

## B5. Providers + downloader
- [~] MangaDex provider: chapter listing + page download ✅; **metadata match/import + field mapping +
      cover fetch ❌**.
- [x] Chapter downloader → AVIF + DownloadTask rows ✅; runs on the background queue with per-page SSE
      progress (`download.progress`). Rows commit as each chapter downloads, so the Downloads table
      climbs mid-chapter (FE reloads on throttled progress events). ⚠ pause/resume not implemented.
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
- [~] Filters/search/sort/cursor/presets/real-covers/AVIF-pages/reading-progress ✅; SSE progress ✅
      (`src/api/events.ts` + activity indicator), series PATCH ✅; **tracker sync ❌**.

# PART E — Backlog / later
- [ ] Auth & multi-user (ADR 12).
- [~] Tests: backend 85 pytest ✅; **FE component tests ❌**.
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
5. [x] **B4 ingest** — parser + scan + library API; scans run on the background queue (`202`, SSE
       progress). (RAR/PDF/EPUB, content-sniff, FTS deferred.)
6. [~] **B5 providers + downloader** — download→AVIF pipeline + Downloads API + MangaDex page provider
       ✅; downloads run on the background queue with SSE progress. **Full MangaDex metadata / match /
       auth / sync planned in PART F below.** (pause/resume deferred.)
7. [~] **B7 + settings** — progress writes, series PATCH (favorite/shelf/rating), providers/trackers/
       sync/about/taxonomy/collections APIs, SSE + task tracker + **background queue + FE SSE
       consumption**, FE Lists + Settings swapped.
       **Remaining: MangaDex full integration (PART F), tracker (AniList/MU/MAL) OAuth, FTS5, extra
       containers.**

---

# PART F — MangaDex API (full integration)

Use the MangaDex API for **metadata fetch + matching**, **chapter download** (already partial), and
**sync** (new-chapter checks + account import). Grounded in the official docs:
- Reference expansion — https://api.mangadex.org/docs/01-concepts/reference-expansion/
- Manga (search / get / aggregate / covers) — https://api.mangadex.org/docs/03-manga/
- Retrieving a chapter's images (at-home) — https://api.mangadex.org/docs/04-chapter/retrieving-chapter/
- Limitations & rate limits — https://api.mangadex.org/docs/2-limitations/
- Swagger — https://api.mangadex.org/docs/swagger.html

**Decisions (2026-07-25):** sync = read-only new-chapter checks **plus** OAuth2 account login to
import follows + reading status; new chapters are **flagged as available** (not auto-downloaded);
series **auto-match after scan** (honors `provider.auto_match` + `locked_fields_json`) with manual
override.

### Key API facts to honor
- **Auth:** metadata / feed / at-home / cover / tag are **public** (no token). Account ops (follows,
  reading status) use an **OAuth2 personal client** (Keycloak): one-time `client_id` / `client_secret`
  + username/password via the `password` grant at
  `https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token`, then `refresh_token`
  grant (access token ~15 min). Store the refresh token + client secret **encrypted at rest**.
- **Rate limits:** global ~5 req/s/IP → HTTP 429 (respect `X-RateLimit-Limit/Remaining/Retry-After`;
  Retry-After is a UNIX ts); persistent abuse → 403 IP ban. Endpoint caps: at-home **40/min**, chapter
  reads 300/10min, manga writes 10/60min. Pagination: `limit` ≤ 100 (feed ≤ 500), `offset+limit ≤ 10000`.
  A non-spoofed `User-Agent` is **required**; the `Via` header is forbidden.
- **At-home download:** `GET /at-home/server/{chapterId}` → `{baseUrl, chapter:{hash, data[],
  dataSaver[]}}`; page URL `{baseUrl}/{data|data-saver}/{hash}/{filename}`. `baseUrl` valid ~15 min; on
  403 re-fetch. **Never** send auth headers to at-home nodes. **Mandatory** best-effort report per image
  to `https://api.mangadex.network/report` `{url, success, bytes, duration, cached}`.
- **Reference expansion:** `includes[]=cover_art&includes[]=author&includes[]=artist` (and
  `scanlation_group` on feed) inlines related attributes into `relationships[]`.
- **Covers:** `cover_art` relationship → `attributes.fileName`; URL
  `https://uploads.mangadex.org/covers/{mangaId}/{fileName}` (`.512.jpg` / `.256.jpg` thumbs).

### Field / enum mapping (MangaDex → lychee)
| MangaDex | lychee |
|---|---|
| `title` (prefer provider language → `en` → original) | `Series.title` + primary `TitleVariant` |
| `altTitles[]` | `TitleVariant` (language-tagged) |
| `description{lang}` | `Series.description` |
| `status` ongoing/completed/hiatus/cancelled | `Series.status` |
| `year` | `Series.year` |
| `contentRating` safe/suggestive/erotica/pornographic | `Series.content_rating` |
| `publicationDemographic` shounen/shoujo/josei/seinen | `Series.demographic` |
| `originalLanguage` (ja→jp, ko→kr, zh→cn) | `Series.origin_country` |
| `tags[]` (group genre/theme/format/content) | `Tag` (reconcile with taxonomy) |
| `author` / `artist` relationships | `SeriesCredit` (name, role) |
| `cover_art.fileName` | `Series.cover_source` / downloaded cover |
| `lastChapter` / aggregate count | `Series.total_chapters` |
| `GET /statistics/manga/{id}` `rating.average` | `Series.rating` (community) |
| `links` (al, mal, mu, ap, kt, …) | `Series.external_ids_json` (**new column**) → tracker match |
| reading status reading/on_hold/plan_to_read/dropped/re_reading/completed | `Series.library_status` |
| feed `scanlation_group.name`, `publishAt` | `Chapter.group_name`, `Chapter.source_uploaded_at` |

### Phases

**M0 — Client foundation** (shared infra) — ✅ done
- [x] Rate-limited client: `src/providers/ratelimit.py` (`TokenBucket`, thread-safe, injectable
      clock) + `src/providers/mangadex_client.py` (`MangaDexClient`): global 5 req/s + at-home 40/min
      buckets, 429 / `X-RateLimit-Retry-After` + bounded 5xx retries, required `User-Agent`.
      `MangaDexProvider` refactored onto it.
- [x] MangaDex@Home report — best-effort `MangaDexClient.report(...)`, wired into `fetch_pages`
      (per-page success/failure report; never fails a download).
- [x] Provider abstraction extended: `MetadataProvider` protocol + `MangaMatch` / `SeriesMetadata`
      DTOs in `downloads/provider.py` (the contract M1/M2/M5 implement).
- [ ] `data_saver` (quality) option → **moved to M3** (only meaningful once `fetch_pages` consumes it).

**M1 — Metadata fetch + mapping** — ✅ done
- [x] `MangaDexProvider.get_metadata(id)`: `GET /manga/{id}?includes[]=cover_art,author,artist` +
      best-effort `/statistics` (community rating) → normalised `SeriesMetadata`. (total_chapters from
      `lastChapter`; `/aggregate` not needed here.)
- [x] Mapper `src/catalog/metadata.py` → `Series` / `TitleVariant` / `SeriesCredit` / `Tag`, honouring
      `locked_fields_json` + language preference. Migration `d59ac262` adds `Series.external_ids_json`.
      Scanner now keys series identity on `path_rel`, so an adopted title can't duplicate on rescan.
- [x] Tag reconciliation against the seeded taxonomy by slug/name (group→`Tag.group`); missing tags
      created. (The manga's own tag list carries the group, so a `/manga/tag` cache isn't needed.)
- [~] Cover: `fetch_covers` stores the remote `.512.jpg` URL in `cover_source`; `coverUrl` hotlinks it.
      **Downloading + local thumbnailing deferred** (`get_cover` still generates from local pages).
- [x] `POST /api/series/{id}/refresh` → enqueues a `metadata` task (queue + SSE); returns 202 + TaskOut.

**M2 — Matching (auto + manual)** — ✅ done
- [x] `MangaDexProvider.search(title)`: `GET /manga?title=&includes[]=cover_art&contentRating[]=all&
      order[relevance]=desc` → `MangaMatch` candidates.
- [x] Auto-match runs inline at the end of a scan (gated by `provider.auto_match`): adopts a provider
      entry only on an **exact normalised-title** match (conservative — otherwise left for manual),
      then applies metadata. `SeriesOut.provider` exposes the matched state to the UI.
- [x] Manual: `GET /api/series/{id}/match-candidates?q=`, `POST /api/series/{id}/match` (202 → metadata
      task), `DELETE …/match` (unlink); FE match-picker modal (covers) + Refresh/Unlink menu on
      SeriesDetail, reloading on the `metadata` task's `done` event.

**M3 — Download enhancements** (pipeline on the queue; M0 added rate limiting + per-page reporting)
- [ ] Feed: `contentRating[]` (all, filtered to the library's policy), `includes[]=scanlation_group`,
      capture `publishAt`→`source_uploaded_at`, title, volume; feed `limit=500`; respect the offset cap.
- [ ] Provider `data_saver` (quality) config (migration or `options_json`) + `fetch_pages` picks
      `data` vs `data-saver`; on 403 re-fetch `/at-home/server` and retry. (Per-page report + the
      40/min at-home bucket are already done in M0.)

**M4 — Account auth (OAuth2) + follows / status import**
- [ ] OAuth2 personal-client flow (password → refresh grant); auto-refresh inside the client.
- [ ] **Secret storage (decided 2026-07-25): encrypt at rest with an app key.** Add a
      `LYCHEE_SECRET_KEY` setting; encrypt the client secret + refresh token with Fernet (adds a
      `cryptography` dep) before writing to SQLite (Provider columns or a `mangadex_account` row).
      Losing the key just means re-connecting.
- [ ] `POST /api/providers/mangadex/connect {clientId, clientSecret, username, password}` / `DELETE`.
- [ ] Import follows: `GET /user/follows/manga` (paged) → create/link `Series` + fetch metadata;
      `GET /manga/status` → map reading status → `library_status`.

**M5 — Sync (new-chapter checks; "flag as available")**
- [ ] Real `POST /api/sync` → enqueue a **`sync`** task (queue + SSE). For matched series, compare
      remote (`latestUploadedChapter` / `aggregate` / `feed`, or authed `GET /user/follows/manga/feed`
      for a bulk check) vs local → count new; persist availability (a lightweight `remote_chapter`
      table or the updates feed) → `SyncState.new_chapters` + a per-series badge + an updates-feed
      "download" affordance (reuses the existing download flow, which skips already-present chapters).
- [ ] Scheduler honouring `SyncState.auto_every_minutes` (periodic asyncio task / APScheduler).
- [ ] FE: wire the Settings → Sync card to real results; SeriesDetail "new chapters" badge; updates markers.

**Testing:** all via `httpx.MockTransport` with canned fixtures per endpoint (search / get / feed /
at-home / statistics / tag / auth / follows). Unit-test the rate limiter (429 / Retry-After), the mapper
(locked fields, language fallback, tag reconcile), and best-effort reporting. No network in tests.

## Handy commands
- Backend: `cd backend && uv run uvicorn src.main:app --reload` (auto-migrates+seeds).
  Demo data: `uv run python -m src.dev_seed`. Checks: `uv run ruff check . && uv run basedpyright && uv run pytest`.
- Regen API client: `cd backend && uv run python scripts/dump_openapi.py` then `cd frontend && bun run api:gen`.
- Frontend: `cd frontend && bun run dev` (proxies /api → :8000). `bun run typecheck`.
