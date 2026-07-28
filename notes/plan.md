# lychee — Build Plan & TODO Tracker

> **Build plan & status tracker** (tracked in git). Living doc; update as we go.
> Legend: `[x]` done · `[~]` partial / needs wiring · `[ ]` not started · `[—]` not planned · `[⏸]` on hold

## Status snapshot (2026-07-25)
- **Frontend:** **fully API-driven** — `src/mocks/library.ts` is deleted; every view (Home,
  library grids, series/gallery detail, reader with progress writes, search, feeds, Lists, and all
  Settings tabs) reads/writes the backend via the generated `openapi-fetch` client. Typechecks clean.
- **Backend:** **feature-complete for the plan's core** — B0 conventions, B2 domain model + Alembic
  migration + seed, B3 AVIF pipeline, the full read API, ingest scan (parser + walk/diff/reconcile),
  synchronous download→AVIF pipeline + MangaDex page provider, reading-progress writes, and the
  Settings/collections/taxonomy/integrations APIs, and the full MangaDex integration (PART F) + reading trackers. **273
  pytest, ruff + basedpyright clean.**
- **How to run:** `cd backend && uv run uvicorn src.main:app --reload` (auto-migrates + seeds) then
  `uv run python -m src.dev_seed` for a demo library; `cd frontend && bun run dev`.
- **Branch:** `docs/research-and-decisions` (local only, not pushed). Architecture: `notes/decisions/`
  (ADR 01–21).
- **PART H — ✅ done:** on-disk `Cover.avif` storage (canonical source + derived grid) + gallery
  artist/model two-level scan (artist folder → `SeriesCredit` + auto `Collection`). See PART H below.
- **PART I — ✅ done:** **two-way** MangaDex account sync — local shelf/read edits push to MangaDex
  per-action (threaded into the tracker sync-on-read machinery); a re-runnable Sync pulls
  status/read-markers/custom-lists→Collections/metadata with MangaDex as source of truth. No page
  downloads. Plus **no-volume** chapter grouping. A sync, not a client. See PART I below.
- **PART K — ✅ done:** `lychee.info` — a native YAML metadata sidecar, read on scan and applied
  through the existing manual-edit lock mechanism (zero new precedence tier). See PART K below and
  [ADR 20](decisions/20-lychee-info-metadata.md). The **writer** side is a Claude Skill
  (`cosplay-metadata`) in the separate [`delfianto/lychee-agents`](https://github.com/delfianto/lychee-agents)
  repo — writes the sidecar directly to disk (read-merge-write, its own schema-strict script),
  independent of `mcp/`. Already functional.
- **PART L — ✅ done:** tag aliases — synonym resolution for `reconcile_tags` (fixes MangaDex's
  unrenamed `pornographic` content rating + Yaoi/Yuri-style duplicate tags) plus a renamable
  display label for the two system taxonomy groups. See PART L below and
  [ADR 21](decisions/21-tag-aliases.md).

## Remaining work (accurate — the genuine gaps)
1. **Functional (user-facing, small backend):**
   - [x] `PATCH /api/series/{id}` — favorite / library-status / personal rating now persist (migration
         b6a9fd5d added `user_rating`; SeriesDetail + GalleryDetail wired). ✅ done.
   - [x] Download `pause`/`resume` — downloads plan one queued row per chapter (carrying
         provider + remote_json); a serial runner drains them, pause/resume flip a row
         queued↔paused. Endpoints `POST /api/downloads/{id}/pause` and `/resume`; the
         Downloads panel calls them. ✅ done.
2. **Larger features (genuinely new work):**
   - [x] **MangaDex full integration** — metadata match/import + `/refresh` + covers, download
         enhancements, OAuth2 account + follows/status import, and real sync (flag new chapters).
         **PART F M0–M5 done** (the automatic sync scheduler is not planned — manual sync covers it).
   - [x] **Tracker outbound sync.** `src/trackers/` — Tracker protocol + registry supporting two auth
         kinds (`oauth` with optional PKCE, `credentials`); tokens/secrets encrypted (Tracker cols,
         migrations `a453837`/`999d293`). Endpoints: `/connect`→authorize URL, `/callback`, `/login`;
         FE connect modal branches on `authKind`. **AniList** (OAuth2), **MyAnimeList** (OAuth2 + PKCE),
         and **MangaUpdates** (password login → session token) all do connect **+ outbound push** on
         chapter completion (`SaveMediaListEntry` / `my_list_status` / `lists/series/update`), gated by
         `sync_on_read`, media id from `Series.external_ids` (M1); push runs on the queue, best-effort.
         **NovelUpdates has no public API → unsupported** (`authKind: "unsupported"`, connect rejected).
         ⚠ MangaUpdates' list-update follows the Mihon/Tachiyomi shape — worth a live sanity check.
   - [x] **SSE** `/api/events` + `/api/tasks` + task tracker — scans emit live progress events. ✅ done.
   - [x] **Background execution queue** — `src/tasks/queue.py` runs scans + downloads on a worker
         thread (own session, serial for SQLite); POSTs return `202 + TaskOut` and stream progress
         via SSE. FE consumes `/api/events` (shared `EventSource`, activity indicator, refetch on
         `*.done`). ✅ done. (Only a persistent/multiprocess queue remains — see below.)
   - [x] **Local import + eager thumbnails + filename metadata** (PART G) — cover thumbnails warmed on
         download/scan (not lazy-on-request); a Settings "Local import" page that transcodes containers to
         AVIF (server path + browser upload; UI quality + enable toggle); and a configurable token-template
         filename→metadata pattern that auto-fills series/volume/chapter/title. **G0–G5 done.** ✅
   - [ ] **MCP server for agent-assisted batch operations** (PART J) — 🟡 proposed, not started. Let a
         local (later, optionally cloud-based) LLM agent drive bulk tagging/downloads/matching instead of
         clicking through the webapp one series at a time. See PART J for the architecture recommendation
         (separate `mcp/` directory, stdio-first, when to add API-key auth).
3. **Coverage:**
   - [—] Extra containers RAR/7z/PDF/EPUB + `python-magic` content sniffing — **not planned**. CBZ/ZIP +
         image directories (plus AVIF-dir for downloads) cover the common cases; the rest isn't worth the
         native-dep + licensing baggage (unrar/7z binaries, pymupdf AGPL).
   - [x] Search: **FTS5 trigram** over title / alt-titles / authors, bm25-ranked, trigger-maintained;
         LIKE fallback for <3-char queries (B6). ✅ done.
   - [x] On-demand resize + disk render cache — `GET /api/chapters/{id}/pages/{n}?w=<width>` serves a
         width-capped AVIF re-encode, cached on disk (`RenderCache`); image-directory listings are
         LRU-cached. Encode fans across a spawn ProcessPool when `LYCHEE_ENCODE_WORKERS` > 1. ✅
4. **Fidelity / correctness:**
   - [x] Error shape: every error response is `{"error":{"code","message"}}` — domain (`LycheeError.code`),
         Pydantic validation (422), and framework HTTP errors (unknown route / method) all normalized. ✅
   - [x] Move-restore preserves reading progress — a soft-delete snapshots its chapters' progress onto
         `Book.restore_progress_json`; a restore (matched by size + hash) re-applies it by chapter number.
         `partial_hash` is now **xxh3-128** (xxhash dep). ✅
   - [x] Taxonomy refresh from `/manga/tag` — `POST /api/taxonomy/refresh` (queue) fetches the provider's
         canonical tag list and adds any missing tags (idempotent; user edits kept). FE: a Refresh button
         on Settings → Content. The hand-curated seed remains the offline default. ✅
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
      `/chapters`, `/related`, `/art`. Action row (favorite / shelf / rating) persists via `PATCH`.
- [x] **Reader** — modes/direction/fit/background; serves `/api/chapters/{id}/pages/{n}`; chapter
      selector + next; **writes progress** as pages turn.
- [x] **Lists** — `/lists` + `/lists/:id`, API-backed collections store.
- [x] **Settings** — General (libraries CRUD/scan, provider, trackers), Content (taxonomy table),
      Downloads (queue + sync), About — all on the API.
- [x] **Theming**, [x] **Transitions**.
- **FE polish:**
  - [x] Loading + **error states** — shared `ErrorState` (message + Retry) wired into dashboard,
        series/gallery detail, and the library grid (`useSeriesList` tracks `failed`). No more
        silent failures / infinite spinners. ✅
  - [~] Accessibility — global `:focus-visible` ring + aria-labels on all search inputs done; a fuller
        keyboard-nav / screen-reader sweep remains.
  - [x] "Add to list" from series **cards** — reusable `AddToListMenu` (deduped from the two detail views),
        on the default-density list card. ✅ (Gallery cover-card variant still to add.)
  - [ ] Reader page preload / long-strip lazy-load.
  - [ ] Breakpoint / mobile QA sweep.

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
- [~] **Images:** Pillow 12 (native AVIF) ✅ · pyvips ❌ (Pillow-only). `python-magic` not planned (see B4).
- [x] **Archives/formats:** stdlib `zipfile` (CBZ/ZIP) + image dirs + AVIF-dir. rarfile/py7zr/pymupdf/ebooklib
      **not planned** (CBZ + directories cover the common cases).
- [~] **Ingest utils:** `hashlib` sha1 sample (not xxhash) · regex natural-sort (not natsort).
- [x] **Tasks:** background `ThreadPoolExecutor` queue ✅ (`src/tasks/queue.py`) + opt-in ProcessPoolExecutor
      for AVIF encode (`media/encode_pool.py`) ✅. APScheduler (auto-sync) not planned.
- [x] **Providers/trackers:** `httpx` ✅ · `cryptography` ✅ (Fernet token encryption) · custom 429/5xx retry + rate-limit buckets (no tenacity).
- [x] **Search:** SQLite **FTS5 trigram** (title / alt-titles / authors, bm25-ranked). ✅
- [x] Present: fastapi, uvicorn, sqlalchemy 2, alembic, pydantic 2 + settings, structlog, nanoid, httpx, pillow, cryptography.

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
- [x] Scanned archives not rewritten (pages served as original bytes) ✅; on-demand resize/transcode →
      AVIF + disk render cache ✅ (`?w=<width>` on `pages/{n}`; `RenderCache`).
- [x] Serving `pages/{n}` + `cover` with ETag + Cache-Control + 304.
- [x] Browser support (AVIF, webapp-only, no fallback).
- [x] Caches: thumbnail FS store ✅; image-dir page-list LRU ✅; render/resize disk cache ✅.
- [x] Encode on a ProcessPoolExecutor — `media/encode_pool.py` fans a chapter's page encodes across a
      spawn pool (`encode` is a pure function). Opt-in via `LYCHEE_ENCODE_WORKERS` (default 1 = serial);
      wired into the downloader + importer. ✅

## B4. Ingest
- [x] Filename / volume-chapter parser (ADR 06) — decimals, ranges, specials, series-name subtraction.
- [x] `BookContainer` — image_dir + CBZ/ZIP + avif_dir ✅, extension-based. RAR/7z/PDF/EPUB + content
      sniffing **not planned** (CBZ + directories cover the common cases).
- [x] Scan pipeline (walk → diff → reconcile, soft-delete + (size, partial_hash) restore) + library
      CRUD/scan API. Restore migrates reading progress (snapshotted on soft-delete; xxh3 hash).
- [x] Task tracker + SSE progress events ✅; **background queue** ✅ — scans run on a worker thread
      (`src/tasks/queue.py`), POST returns `202 + TaskOut`. (In-process/serial; a persistent or
      ProcessPoolExecutor queue is a later scaling concern.)

## B5. Providers + downloader
- [x] MangaDex provider: chapter listing + page download ✅; metadata fetch + search + auto/manual match
      + field mapping (`catalog.metadata`) + covers ✅ (M1/M2). Covers downloaded + cached locally as AVIF thumbnails.
- [x] Chapter downloader → AVIF + DownloadTask rows ✅; runs on the background queue with per-page SSE
      progress (`download.progress`). Rows commit as each chapter downloads, so the Downloads table
      climbs mid-chapter (FE reloads on throttled progress events). Planned as one queued row per
      chapter (carrying provider + remote_json) so a serial runner can drain them and pause/resume ✅.
- [x] **Sync** ✅ — `/api/sync` diffs each matched series' feed vs local chapters → `Series.available_chapters`
      + a global count (M5). Auto-scheduler not planned.

## B6. Search
- [x] `GET /api/search` — **FTS5 trigram** over title / alt-titles / authors, bm25-ranked (title weighted
      highest), kept in sync by triggers on series/title_variant/series_credit; LIKE fallback for short
      queries. Shared DDL in `catalog/search_index.py` (migration + test harness). ✅ done.

## B7. Reading progress + trackers
- [x] Progress writes (`PUT /api/chapters/{id}/progress`) → unread / lastRead / continue-reading.
- [x] Outbound tracker sync + OAuth ✅ — AniList / MyAnimeList (OAuth2 ± PKCE) + MangaUpdates (login)
      connect + push read status on chapter completion (`src/trackers/`, gated by `sync_on_read`;
      NovelUpdates unsupported).

---

# PART C — API contract

### Series & library grids
- [x] `GET /api/series` (all filters, 5 sorts, cursor).
- [x] `GET /api/series/{id}`.
- [x] `PATCH /api/series/{id}` `{favorite?, libraryStatus?, rating?}` — favorite/shelf/user-rating persist.
- [x] `POST /api/series/{id}/refresh` ✅ (M1) + `GET .../match-candidates`, `POST .../match`, `DELETE .../match` (M2).
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
- [x] `GET /api/search` (FTS5 trigram, bm25-ranked).

### Collections (Lists)
- [x] GET/POST `/api/collections`, [x] GET/PATCH/DELETE `/api/collections/{id}`,
      [x] POST/DELETE `/api/collections/{id}/series[/{sid}]`.
- [—] Series reorder within a list — intentionally not planned (lists are alphabetical + searchable).

### Settings
- [x] **Libraries** GET/POST/PATCH/DELETE + `/summary` + scan/scan-all.
- [x] **Taxonomy** GET(paged)/POST/PATCH/DELETE (system rows protected; uses counts).
- [x] **Providers** GET/PATCH + connect/disconnect/import (MangaDex OAuth account + follows import).
- [x] **Trackers** GET/PATCH + connect(→authorize URL)/callback/login/disconnect ✅ — real OAuth2 ± PKCE + credentials login.
- [x] **Downloads** GET/POST/DELETE/clear-completed/retry/pause/resume ✅.
- [x] **Sync** GET/POST ✅ — real new-chapter check on the queue (M5).
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
- [x] **CI + task runner** — GitHub Actions (`ci.yml` backend: uv → ruff / basedpyright / alembic check /
      pytest; `frontend-ci.yml`: bun → typecheck / vitest / build) + a `just` task runner (`just check`
      runs the whole gate locally).
- **Infra — on hold** (deferred to last, by request):
  - [⏸] Auth & multi-user.
  - [⏸] Docker packaging.
- [~] Tests: backend 175 pytest ✅; FE vitest set up (@vue/test-utils + happy-dom) with first
      component/unit tests — **coverage still thin**.
- [—] OPDS / device-sync (explicitly out per ADR 15).
- [ ] JPEG page fallback endpoint (only if a non-webapp client appears).
- [ ] Per-page reader thumbnails.
- [x] Formalize AVIF policy as **ADR 19**.
- [ ] Scrub any leftover "ebook/Books" wording.

---

## Build order — status
1. [x] **B0 conventions + B1 deps** (Pillow; other media deps deferred per-feature).
2. [x] **B2 domain model + migration + seed.**
3. [x] **B3 AVIF pipeline** (encode/presets/thumbnails/containers/serving). ADR 19.
4. [x] **Read-only API slice + client + FE swap of every read view.**
5. [x] **B4 ingest** — parser + scan + library API; scans run on the background queue (`202`, SSE
       progress). (RAR/PDF/EPUB + content-sniff not planned.)
6. [x] **B5 providers + downloader** — download→AVIF pipeline + Downloads API + MangaDex page provider
       ✅; downloads run on the background queue with SSE progress. Full MangaDex metadata / match /
       auth / sync done (PART F M0–M5); resumable download pause/resume ✅. (Local cover cache remains.)
7. [x] **B7 + settings** — progress writes, series PATCH (favorite/shelf/rating), providers/trackers/
       sync/about/taxonomy/collections APIs, SSE + task tracker + background queue + FE SSE consumption,
       MangaDex integration (PART F) + tracker OAuth/push (`src/trackers/`), FE Lists + Settings
       swapped. (Auto-sync scheduler not planned.)

---

# PART F — MangaDex API (full integration) — ✅ done (M0–M5; auto-sync scheduler not planned)

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
- [x] `data_saver` (quality) option — done in M3.

**M1 — Metadata fetch + mapping** — ✅ done
- [x] `MangaDexProvider.get_metadata(id)`: `GET /manga/{id}?includes[]=cover_art,author,artist` +
      best-effort `/statistics` (community rating) → normalised `SeriesMetadata`. (total_chapters from
      `lastChapter`; `/aggregate` not needed here.)
- [x] Mapper `src/catalog/metadata.py` → `Series` / `TitleVariant` / `SeriesCredit` / `Tag`, honouring
      `locked_fields_json` + language preference. Migration `d59ac262` adds `Series.external_ids_json`.
      Scanner now keys series identity on `path_rel`, so an adopted title can't duplicate on rescan.
- [x] Tag reconciliation against the seeded taxonomy by slug/name (group→`Tag.group`); missing tags
      created. (The manga's own tag list carries the group, so a `/manga/tag` cache isn't needed.)
- [x] Cover: the provider cover is **downloaded once and served locally** as a cached AVIF thumbnail
      (never hotlinked). `generate_series_cover` prefers `cover_source` over the first page; `coverUrl`
      always points at `/api/series/{id}/cover`. ✅
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

**M3 — Download enhancements** (pipeline on the queue; M0 added rate limiting + per-page reporting) — ✅ done
- [x] Feed: `contentRating[]` (all — else erotica/pornographic drop), `includes[]=scanlation_group`,
      `publishAt`→`Chapter.source_uploaded_at`, `scanlation_group.name`→`group_name`, title, volume;
      feed `limit=500`; offset capped at 10000. `RemoteChapter` carries group + published_at.
- [x] Provider `data_saver` config (migration `c32e0a9`, ProviderOut/Update + Settings toggle) →
      `fetch_pages` picks `data` vs `data-saver`; on 403 re-fetches `/at-home/server` + retries once.
      (Per-page report + the 40/min at-home bucket were already done in M0.)

**M4 — Account auth (OAuth2) + follows / status import** — ✅ done
- [x] OAuth2 personal-client flow (`src/providers/mangadex_auth.py`): `password` grant on connect,
      `refresh_token` grant at import time (tokens rotate → the new refresh token is re-persisted).
- [x] **Secret storage — encrypted at rest.** `LYCHEE_SECRET_KEY` setting + `src/core/crypto.py`
      (Fernet, `cryptography` dep); Provider gains `client_id`/`account_name` + encrypted
      `client_secret_enc`/`refresh_token_enc` (migration `37829ee`). Connect is refused without a key.
- [x] `POST /api/providers/{id}/connect` (stores encrypted) / `/disconnect`; `ProviderOut.connected`
      + `account_name`. FE: Settings connect form + Connected/Import/Disconnect card.
- [x] `POST /api/providers/{id}/import` → background `import` task: `list_follows` + `reading_status`
      (authed) upsert into a virtual "MangaDex" library, apply metadata, map status → `library_status`.

**M5 — Sync (new-chapter checks; "flag as available")** — ✅ core done
- [x] Real `POST /api/sync` → enqueues a **`sync`** task (queue + SSE). For each matched series it
      diffs the provider feed vs local chapters and stores the count on `Series.available_chapters`
      (migration `a368507`), summing into `SyncState.new_chapters`. Reusing the download flow (which
      skips already-present chapters) is the "download" affordance.
- [x] FE: Settings → Sync card runs the async sync + reloads on the task's `done`; SeriesDetail shows
      a "N new" badge from `availableChapters`.
- [—] **Scheduler** honouring `SyncState.auto_every_minutes` (periodic task) — **not planned**. Manual
      sync (Settings → Sync → "Sync now") covers the need; an always-on interval scheduler isn't worth it.

**Testing:** all via `httpx.MockTransport` with canned fixtures per endpoint (search / get / feed /
at-home / statistics / tag / auth / follows). Unit-test the rate limiter (429 / Retry-After), the mapper
(locked fields, language fallback, tag reconcile), and best-effort reporting. No network in tests.

# PART G — Local import + eager thumbnails + filename metadata — ✅ done (G0–G5)

Three related pieces of catalog-building polish:
1. **Eager thumbnails** — warm cover thumbnails when content lands (download / scan), instead of lazily on
   the first `/cover` request.
2. **Local import** — a Settings page to import container files/folders already on the server's disk,
   transcoding pages to AVIF (like downloads do), with UI-configurable quality + an enable toggle.
3. **Filename → metadata pattern** — a configurable, LANraragi-style pattern that fills
   series/volume/chapter/title (and credits) from filenames during import.

### Current state (what we build on)
- **Thumbnails** (`media/thumbnails.py`): `ThumbnailStore.generate(thumb_id, source, variant, *,
  content_class, overwrite)` + `generate_all(...)`; store keys by **`series_id`** (`thumb_id == series_id`),
  sharded `<root>/<id[:2]>/<id>.<cover|detail>.avif`. Generated **only lazily** in `get_cover`
  (`catalog/media.py:70-85`) on a miss; cover source = **first book, page 0** (`_first_book` +
  `_read_page(book, 0)`). Store built as `ThumbnailStore(Path(settings.storage_path)/"thumbnails")`.
- **AVIF** (`media/avif.py`): `encode(image, *, content_class)` / `encode_bytes(bytes, *, content_class)` —
  **quality is not overridable** (hardcoded per-class in `_PRESETS`: line_art q63 mono, color_art q80 4:4:4,
  photo q60 4:2:0; `ENCODE_SPEED=2`). Sole `encode_bytes` caller is `downloader.py:100`.
- **Download transcode** (`downloads/downloader.py`): `_download_chapter` fetches pages → `encode_bytes` →
  writes `NNN.avif` under `storage/downloads/<series>/<chapter>` → `Book(content_kind="avif_dir")` + `Chapter`
  (flush at `:132`). Runs on the queue; `storage_root` in scope.
- **Scan** (`ingest/scanner.py`): registers **in-place originals** (no transcode); `_ingest_series` creates
  Series/Book/Chapter; `_sync_chapter` (`:277`) calls `parse(...)`. Series title = folder name.
- **Filename parser** (`ingest/parser.py`): `parse(segments, series_name, kind) -> ParsedName{number,
  number_sort, volume, year, special, label}` — number/volume/year/special via a regex cascade; **does not
  extract series or title** (series is an input that's subtracted out).
- **Config storage**: **no general settings table.** Template = the `Provider` row / `SyncState` singleton
  (`id="default"`) + GET/PATCH + a reactive FE panel that `watch`es and PATCHes.
- **Task queue**: `queue.submit_task(kind, label, work) -> TaskOut` (202 + SSE); FE follows `/api/events`
  filtering by `task.kind`. ⚠ `"import"` kind is **already used** by MangaDex follows-import → the new job
  must use a different kind (`"localimport"`).
- **Managed library pattern**: `downloads_library(session, storage_root)` get-or-creates a "Downloads"
  library at `storage/downloads`. Imports mirror this with an "Imports" library at `storage/imports`.

### Decisions (confirmed 2026-07-25)
- Imported content is **transcoded to AVIF** (per the request) and lands in a managed **"Imports"** library
  at `storage/imports/...` (mirrors Downloads), never registered in-place.
- **Two import sources, phased:** **(Phase 1, G3) a server-side path** the admin points at (file or folder),
  consistent with how libraries already take a server path; **(Phase 2, G5) browser upload** (multipart →
  staged temp dir → the same transcode pipeline).
- Config is a **global singleton `ImportConfig`** (`id="default"`): `enabled`, `quality`, `filename_pattern`.
  (Per-library `Library.options_json` rejected — the import page is one global settings surface.)
- **Quality** override replaces the per-class preset `quality` for import transcodes; **subsampling stays
  per content-class** (keeps line-art crisp). UI exposes a few tiers → numbers (e.g. Higher 85 / Balanced
  75 / Smaller 60).
- **Filename pattern = friendly token template** (`{series} - c{chapter} (v{volume})`) compiled to a regex —
  not raw regex — and falls back to the built-in `parse` on no-match.
- Eager thumbnails **keep the lazy `get_cover` fallback** (warm, don't replace) — a missing thumb still
  self-heals on request.

### Phases

**G0 — AVIF quality override (foundation)** — ✅ done
- [x] Optional `quality: int | None` on `avif.encode` / `encode_bytes` (override `preset.quality`, clamped
      1–100; subsampling + speed unchanged), threaded through `ThumbnailStore.generate` / `generate_all`.
- [x] Tests: lower quality → smaller bytes; `None` reproduces the preset path exactly.

**G1 — Eager thumbnails on download + scan** — ✅ done
- [x] `catalog/media.py` `generate_series_cover(session, store, series_id, *, overwrite=False)` (kept next to
      `get_cover` to reuse `_first_book`/`_read_page`) + `warm_library_covers(...)` — first-book page 0 →
      `generate_all`. Idempotent (skips reading when all variants exist) + best-effort (swallows a bad page).
- [x] Downloader `run_download_queue` warms the cover after each finished chapter (store =
      `ThumbnailStore(storage_root/"thumbnails")`).
- [x] Scan work threads `storage_root` (via the shared `StorageRootDep` so the test override applies) and
      `warm_library_covers` after auto-match. conftest: thumbnails now live under `storage_root/"thumbnails"`.
- [x] `get_cover` lazy fallback kept. Tests: after download/scan, thumb files exist with no `/cover` request.

**G2 — Import config (storage + API + FE panel)** — ✅ done
- [x] `ImportConfig` singleton (`integrations/models.py`): `enabled=False`, `quality=75`,
      `filename_pattern=""`. Migration `2f54a96b80db` (new table) + idempotent seed (like `SyncState`).
- [x] `ImportConfigOut`/`ImportConfigUpdate` (camel, quality validated 1–100) + `GET/PATCH
      /api/import/config` in `integrations/import_config.py` (copies `providers.update_provider`).
- [x] FE `views/settings/ImportPanel.vue` + a "Local import" `sections` entry in `SettingsView.vue`;
      reactive `watch → PATCH`. Enable toggle, quality tiers (Higher/Balanced/Smaller), pattern input +
      token legend. Screenshot-verified, zero JS errors. (Import form itself lands in G3.)
- [x] Tests: defaults, PATCH persists, partial update, quality out-of-range → 422.

**G3 — Local import job (walk → AVIF → catalog)** — ✅ done
- [x] `ingest/importer.py` `import_path(session, source, *, kind, storage_root, quality, on_progress)` —
      resolves the source (file → one book; folder → `resolve_books`), transcodes each page
      `encode_bytes(raw, quality)` → `NNN.avif` under `storage/imports/<series>/<book>`, creates
      `Book(content_kind="avif_dir")` + `Chapter` in a get-or-create **Imports** library, warms cover (G1).
      Idempotent (skips already-imported books), per-book commit + progress. Promoted the reused scanner
      helpers to public (`Candidate`, `resolve_books`, `sync_chapter`, `order_chapters`).
- [x] `POST /api/import` `{path, kind}` (`integrations/local_import.py`) →
      `queue.submit_task("localimport", …)` → 202 + TaskOut. Rejects 400 when disabled / bad kind / bad path.
- [x] FE: "Import from a path" form in ImportPanel (path + kind + Import); follows SSE
      (`activeTasks` / `onTaskDone` filter `kind === "localimport"`), toasts the result.
- [x] Verified live (CBZ → served AVIF pages + warmed cover) + 5 tests: file, folder, idempotent,
      disabled → 400, bad path → 400.

**G4 — Filename → metadata pattern (LANraragi-style)** — ✅ done
- [x] Pattern engine in `parser.py`: `parse_pattern(filename, pattern) -> PatternResult | None` — compiles a
      token template (`{series}`, `{title}`, `{volume}`, `{chapter}`, `{author}`, `{artist}`, `{group}`,
      `{year}`, `*` ignore) to a regex and **fullmatches** the extension-stripped name (text tokens lazy so a
      literal delimits them; `*` = `.*?` for extra text). Unknown/duplicate/no-token → None.
- [x] Import integration: when `config.filename_pattern` is set, the first book names the series (+ year /
      author / artist credits, deduped); each book's chapter number/volume/title/group come from the pattern,
      else the built-in `parse`. Source name stays the stable series identity (no dup on re-import).
- [—] (Optional) extend the same pattern to the scanner — not done; scoped to import for now.
- [x] Verified live (`{author} - {series} - c{chapter}` → series/author/chapter) + 8 tests (pattern unit
      cases: series/chapter/volume, author, title/year, whole-name, trailing `*`, no-match, invalid; plus a
      pattern-driven import).

**G5 — Browser upload (import source, Phase 2)** — ✅ done
- [x] `POST /api/import/upload` (multipart) — validates (enabled / `.cbz`|`.zip` / 1 GiB cap), streams the
      upload in chunks to `storage/uploads/<token>/` (outside any library so scans ignore it), runs the same
      `import_path` pipeline, and removes the staging dir when done (success or failure). Added
      `python-multipart`.
- [x] FE: an "or upload a file" file-input in ImportPanel (raw multipart `fetch`) beside the path form;
      result via the same `"localimport"` SSE.
- [x] Verified live (CBZ upload → series + transcoded AVIF + warmed cover, staging cleaned) + 4 tests:
      upload transcodes, disabled → 400, bad-type → 400, oversize → 400.

**Testing:** unit-test the pattern compiler (tokens→regex, literal escaping, no-match) and the AVIF quality
override; integration-test import end-to-end (tmp CBZ/folder → served AVIF + generated thumbnail) and config
GET/PATCH — all offline, building real archives in `tmp_path` like `test_scan_api.py`. **New deps: none**
(Pillow AVIF + stdlib `zipfile` cover it).

# PART H — Cover.avif storage + gallery artist/model scan — ✅ done (H0–H1)

> Decided 2026-07-25: covers become an on-disk **`Cover.avif`** (the canonical source of
> truth) with the small grid thumbnail still derived from it; **gallery** libraries scan
> **two levels** (artist/model → gallery). Spec first — build after review. New deps: none.

## H0 — `Cover.avif` as the canonical cover source — ✅ done

**Today:** covers are *derived only* — AVIF thumbnails in a central sharded store keyed by
series id (`storage/thumbnails/<id[:2]>/<series_id>.{cover,detail}.avif`, 320/640). The source
is the matched provider cover (cached) or the series' first book's first page. No on-disk
cover-file convention is read anywhere.

**Target:** one canonical `Cover.avif` per series is the source of truth; the 320px grid
thumbnail is still derived from it and cached.
```
storage/imports/<series_id>/
  Cover.avif              ← canonical (~640px longest edge, normalized AVIF)
  <hash>.cbz  <hash>.cbz  ← the books
storage/thumbnails/<id[:2]>/<series_id>.cover.avif   ← derived 320px (grids only)
```
- [x] **Managed libraries (import/download):** `write_series_cover()` writes `<library>/<series_id>/Cover.avif`
      — a normalized ~640px AVIF of the raw source (provider cover if matched, else first book's first
      page). Atomic (temp + `os.replace`). Books stay CBZ; the cover sits beside them at the series dir.
- [x] **Scanned (in-place) libraries:** `_on_disk_cover()` reads `Cover.avif` / `cover.*` / `folder.*`
      (case-insensitive) from the series dir as the source, else the fallback (provider cover / first
      page). Never writes into the user's originals.
- [x] **Source resolution** (`media.py`): `_canonical_cover_bytes()` → (1) on-disk `Cover.*`/`folder.*`
      at the series dir (normalized if not already AVIF), else (2) provider cover / first page via
      `_raw_cover_source()`. `_series_dir()` resolves the dir (scanned `path_rel` folder, else managed
      `<lib>/<series_id>`; None for a loose one-shot). *(Skipped the optional `cover_source` caching —
      resolution is cheap.)*
- [x] **Derived grid; dropped `detail`:** the store holds only the 320px `cover` variant (from the
      canonical cover); `?size=detail` serves the canonical cover bytes, no 640 store variant.
      (`ThumbnailStore` still *supports* `detail`/`generate_all` — just unused by the cover flow.)
- [x] **Page-list exclusion:** `is_cover_file()` excludes `Cover.avif`/`cover.*`/`folder.*` from
      `resolve_books` detection + `_signature` **and** `ImageDirContainer`/`ZipContainer` page lists — a
      cover file is never a spurious book nor a page. (Fixes the "any image in a folder → book" gotcha.)
- [x] **Serving:** `GET /api/series/{id}/cover?size=cover|detail` — `cover` → derived 320 (generated on
      a miss); `detail` → canonical cover bytes; ETag/Cache-Control/304 unchanged.
- [x] **Back-compat:** old `cover`/`detail` thumbnails keep serving; `Cover.avif` is written on the next
      import/download. No DB migration. *(One-shot backfill for existing managed series not done — optional.)*
- [x] **Tests:** import writes `<series>/Cover.avif` (AVIF) + `?size=detail` serves it; a source cover is
      excluded from a chapter's page count; container cover-exclusion (dir + zip) + `is_cover_file` unit;
      download writes a managed `Cover.avif`; scan/download warming assert the 320 grid. **+6 → 183.**

**Open (follow-up, not this scope):** per-volume covers. With books as CBZ there's no `Vol.01/`
dir — a volume's cover is its cbz's first page (served on demand). Series-level `Cover.avif` is the
scope here; per-book `<series>/<book>.cover.avif` can come later if wanted.

## H1 — Gallery libraries: artist/model → gallery two-level scan — ✅ done

**Today:** every kind uses one scan rule — first-level dir under the root = Series. For gallery
libraries that makes `Root/GalleryName/imgs` → `GalleryName` the gallery; artists are metadata only
(`SeriesCredit` role=artist). `Collection` (named, ordered group of series) already exists in
`src/collections/`.

**Target:** for `kind=gallery` libraries only, scan **two levels** — top folder = artist/model, each
subfolder/cbz below = its own gallery.
```
/galleries/                 Library (kind=gallery)
  Artist Name/              → artist credit (+ Collection "Artist Name")
    Set A/  001.jpg…        → Series (kind=gallery)   [image_dir]
    Set B.cbz               → Series (kind=gallery)   [cbz]
  Loose Gallery.cbz         → Series (kind=gallery), no artist (root one-shot)
```
- [x] **Kind-specific resolution** (`scanner.py`): gallery libraries iterate first-level dirs via
      `_ingest_artist` — each is an artist/model; every image-dir / archive below is a gallery Series
      (`_ingest_entry` → `resolve_books` one level down). An artist folder that *directly* holds images
      is itself a single gallery (flat libraries still work). Loose root archive/dir → one-shot gallery,
      no artist. Manga/comic rule unchanged (`_ingest_entry` with `artist=None`).
- [x] **Artist wiring:** `_credit_artist()` adds `SeriesCredit(role="artist")` per gallery (deduped).
      The existing `GalleryView` artist filter (`g.artists`) lights up for free.
- [x] **Collection wiring:** `_credit_artist()` get-or-creates a `Collection` named after the artist and
      appends each gallery (ordered) — browsable via `/api/collections` + the Lists UI. Idempotent.
- [x] **Series identity:** `path_rel` = the gallery's path relative to the root (`Artist Name/Set A`,
      archives suffix-stripped), so it's unique across artists + move-restore keeps working. `image_count`
      as today. (`_ingest_entry` unifies the identity for manga folders + loose archives too.)
- [x] **FE:** no change needed — `GalleryView` already filters/searches by `g.artists`, and the auto
      Collection appears in the Lists UI. Both consume the now-populated data directly.
- [x] **Tests:** `Artist/SetA` + `Artist/SetB.cbz` → two gallery Series, both credited "Artist", both in
      Collection "Artist"; loose root gallery → one Series, no artist; re-scan idempotent (no dup credits
      / collection membership). Manga scan tests unchanged (unaffected). **+2 → 185.**

**Testing (both):** offline, building real dirs/CBZs in `tmp_path` like `test_scan_api.py` /
`test_import_api.py`. New deps: none (Pillow AVIF + stdlib `zipfile`).

# PART I — Two-way MangaDex sync (status · read · lists) + no-volume grouping — ✅ done (I0–I2)

> Decided 2026-07-25: a **two-way** sync with the MangaDex account. Local edits to a dex-linked series
> **push to MangaDex the moment you make them** (per-action, like the AniList/MAL trackers); a re-runnable
> **pull** brings MangaDex state down with **MangaDex as the source of truth**. Custom lists →
> Collections (pull-only). Metadata + covers, **no page downloads** (download stays a triggered action).
> Plus a **no-volume** chapter-grouping fix. A sync, not a client. New deps: none.
>
> **The rule that makes it robust:** push on the *action*, not at sync time — so MangaDex already has your
> edit before any pull runs, and "MD-wins-on-pull" never eats a change you just made. (A failed push may
> be reverted by a later pull — best-effort, like the trackers; a retry queue is later hardening.)
> **Auth:** the account Bearer only ever hits `api.mangadex.org` (status/read/lists/follows/metadata) —
> never the at-home page path — so it can't leak; the download provider stays unauthenticated.
> **Push gate:** only series with a MangaDex id (`provider_series_id`) + a connected account push.

**Shipped — deviations from the spec:** `Chapter.provider_chapter_id` already existed + is populated by
the downloader, so no new column there — the only migration is `Collection.provider/provider_list_id`
(`bac440c50fd8`). The account access token is cached **in-memory** (~14 min), not in a DB column — the
single-worker queue makes that race-free. The endpoint was renamed `/import` → `/sync`, and the FE
already labelled `volume=null` (just capitalised to "No Volume").

**Conflict policy (per data type):**

| Data | Direction | Resolution |
|---|---|---|
| Reading status (shelf) | two-way | push on change; **MD-wins** on pull (replace) |
| Read markers (progress) | two-way | push on chapter-read; pull marks read from MD (additive v1; downloaded series only) |
| Metadata · tags · covers | pull only | **MD-wins** (mirror of a MD-sourced title) |
| Custom lists → Collections | pull only (managed) | **MD-wins**; local edits to a *synced* list revert (two-way membership is a later opt-in) |
| Favorite · personal rating | local only | not synced |
| Unfollow / removal on MD | — | **never delete** a series with downloaded chapters; just clear its shelf |

## I0 — Inbound sync (pull; MangaDex is source of truth) — ✅ done

**Today:** `POST /api/providers/mangadex/import` (`providers/mangadex_account.py::import_follows`) is a
one-shot — authed → `list_follows` + `reading_status` → upsert Series into the virtual "MangaDex"
library, `apply_metadata`, status → `library_status`. No custom lists, no read markers, no re-sync.

**Target:** an idempotent Sync over the union of follows ∪ status'd ∪ custom-list-member manga.
- [x] **Provider:** add `list_custom_lists()` → `GET /user/list` (paged, Bearer) → `[{id, name,
      manga_ids}]` (manga ids ride in each `CustomList.relationships` — verified live; no per-list call
      needed). Add `read_markers(manga_ids)` → batch `GET /manga/read?ids[]=` → `{manga_id:[chapter_id]}`.
      `list_follows` + `reading_status` already exist. (Bonus, later: `/list/{id}/feed` → "follow a list".)
- [x] **Series set = union:** follows ∪ status'd ∪ list members; `get_metadata` for any not covered.
      Upsert by `(provider, provider_series_id)` (existing) — so a scanned-and-matched series is the *same*
      row (no duplicate; sync updates it in place).
- [x] **Status → shelf (MD-wins):** `_READING_STATUSES` → `library_status`, overwriting local. Paired with
      the I1 push, local edits already reached MD, so a pull only lands genuine website-side changes.
- [x] **Read markers → progress (downloaded only):** needs `Chapter.provider_chapter_id` (nullable,
      indexed; migration), set by the downloader from `RemoteChapter.provider_chapter_id`. For each synced
      series **with local chapters**, mark `ReadingProgress` completed for chapters whose id ∈ the read set
      (additive v1 — don't unmark). Sync-only series → no-op; only request markers for series that have
      local chapters (bounds calls).
- [x] **Custom lists → Collections (managed):** add `provider` + `provider_list_id` (+ index) to
      `Collection` (migration). Get-or-create by `(provider, provider_list_id)`, name from the MD list;
      reconcile membership. Surfaces in the Lists UI unchanged.
- [x] **Metadata + covers (mirror):** `apply_metadata` as today — `cover_source` = MD cover URL, lazy.
      **No page downloads.** Never delete a series on unfollow (clear shelf only, keep any downloads).
- [x] **Re-runnable action:** **"Sync from MangaDex"** (202 + SSE queue task); reuse the account button.
      Optional `last_synced_at` on the Provider row.
- [x] **Tests:** stub provider → follows + statuses + two overlapping lists + read markers → one Series per
      unique manga, shelves set, two Collections w/ membership, read chapters completed on a downloaded
      series (no-op on a sync-only one); re-sync idempotent (no dup series/collections/members).

## I1 — Outbound sync (push; per-action, immediate) — ✅ done

**Today:** local shelf/progress edits stay local for MangaDex-linked series (the AniList/MAL/MU trackers
push local changes out; MangaDex — a *provider* — does not).

**Target:** on a dex-linked series, push local edits to MangaDex the moment they happen.
- [x] **Status push:** when `library_status` changes on a series with `provider="mangadex"` +
      `provider_series_id` + a connected account → `POST /manga/{id}/status` `{status|null}` (map
      `_READING_STATUSES`; `none` → clear). Fire where the trackers hook the shelf change.
- [x] **Read push:** when a chapter is completed on such a series → `POST /manga/{id}/read`
      `{chapterIdsRead:[<provider_chapter_id>]}` (uses the I0 `Chapter.provider_chapter_id`). Hook the
      progress-completed path (the trackers' sync-on-read point).
- [x] **Best-effort:** fire-and-forget through the client's retry/rate-limit; a failed push isn't fatal (a
      later pull may revert — acceptable v1; retry queue later). Never attach the Bearer to page fetches.
- [x] **Reuse:** thread MangaDex into the existing tracker sync-on-read trigger points rather than new call
      sites — one place decides "push to all connected sinks".
- [x] **Tests:** shelf change on a dex-linked + connected series → `status` POST with the mapped value; a
      non-dex or disconnected series → no push; chapter-completed → `read` POST carrying the MD chapter id.

## I2 — No-volume chapter grouping ("No Volume" on top) — ✅ done

**Today:** `catalog/service.py::list_chapters` groups by nullable `volume` (good) but emits groups in
**first-seen order** of a `number_sort`-ordered list — so a `null`-volume group interleaves among
numbered volumes, and the FE has no label for `volume: null`.

**Target:** deterministic grouping with loose chapters up top (MangaDex-style).
- [x] **BE group order:** emit the `null` ("No Volume") group **first**, then numbered volumes by number
      **descending** (latest first). Within a group keep the existing chapter order.
- [x] **FE label:** `ChapterList` renders `volume === null` as a **"No Volume"** heading (not "Volume ").
- [x] **Pure-loose (nice-to-have):** a series with only null volumes may render as a flat list; the "No
      Volume" heading is harmless either way — decide in impl.
- [x] **Tests:** volumes {null, 1, 2} → group order [null, 2, 1]; non-numeric MD volumes land in the null
      group (already true); the null group is labeled "No Volume" in the FE.

**Testing (all):** offline — stub the provider (no network), fixtures in `tmp_path`; migrations for
`Collection.provider/provider_list_id` + `Chapter.provider_chapter_id` (`alembic check` clean).

# PART J — MCP server for agent-assisted library operations — ✅ done

> Built as `mcp/` — see [`mcp/AGENTS.md`](../mcp/AGENTS.md) for what actually shipped
> (tool list, layout, conventions); this section is the original architecture
> recommendation that preceded it, kept for the rationale. Goal: let an
> LLM agent (local today; possibly cloud-based later) drive the batch/tedious library
> operations that are annoying to click through one series at a time — bulk tagging,
> bulk downloads, finding unmatched/untagged series, bulk shelf-status updates.

## Decision (recommended)

- **Separate top-level `mcp/` directory**, sibling to `backend/`/`frontend/` — **not**
  `backend/src/mcp/`. The MCP server is a **client of the existing REST API**, the same
  relationship the frontend already has to the backend, not a new direct consumer of
  the ORM/service layer. Reasons:
  - The described use cases (bulk tag, bulk download, bulk shelf update) are
    **orchestration over endpoints that already exist** — `PATCH /api/series/{id}`
    already accepts `tagIds`/`libraryStatus`/`favorite`; `POST /api/downloads` already
    accepts a `seriesId` or `providerChapterIds` list. **Zero backend changes are
    required to build v1** — the MCP layer just loops over the current contract, the
    same way a batch script hitting the API would. (A handful of true bulk endpoints —
    e.g. `PATCH` many series at once — would cut round-trips later, but aren't needed
    to start.)
  - Keeps `fastmcp` + the MCP SDK (and whatever HTTP client it needs) **out of the
    backend's `pyproject.toml`/lockfile** entirely. Nobody who just wants the media
    server pays for that dependency surface, and the backend's own quality gate
    (ruff/basedpyright/pytest) doesn't have to cover agent-tool code.
  - Matches [ADR 15](decisions/15-api-surface.md)'s own escape hatch: "the clean REST
    API + entity model don't preclude adding … a public API later if a non-webapp
    client ever appears." An MCP server is exactly that second client — but it's an
    **owner-operated automation surface**, not the OPDS/Komga-compat/third-party-reader
    ecosystem ADR 15 explicitly rejected, so it doesn't reopen that decision, just
    exercises the reversibility it already banked.
  - Structurally: `backend/` + `frontend/` stay "the one deployable" (per the root
    `CLAUDE.md`); `mcp/` is optional tooling you run only if you want agent access, same
    spirit as `notes/` or `scripts/` — not part of what a self-hoster has to run.
  - **Alternative considered:** mount FastMCP as an ASGI sub-app inside the existing
    FastAPI process (`app.mount("/mcp", mcp.http_app())`), reusing `Depends(get_db)`
    directly. Rejected for now — saves an HTTP hop that's irrelevant next to
    chapter-download/provider I/O, but permanently couples the backend's dependency
    footprint and release surface to the MCP surface for no real gain given v1 needs no
    new service-layer access.
- **Shape, once built:** own `pyproject.toml` (`uv`-managed like `backend/`), own
  `AGENTS.md`, a typed client generated from `backend/openapi.json` (mirrors the
  frontend's `openapi-typescript` step — e.g. `openapi-python-client` or a hand-rolled
  `httpx` wrapper over the same schema, decide at build time), and `just mcp-install` /
  `just mcp-dev` recipes alongside `be-*`/`fe-*` in the root `justfile`.
- **Tool surface is the batch primitives, not 1:1 endpoint passthrough** — e.g.
  `find_untagged_series` / `find_unmatched_series` (fetch + filter client-side; no new
  backend filter needed for v1), `bulk_tag_series(series_ids, tag_ids, mode)`,
  `bulk_queue_downloads(series_ids)`, `bulk_set_library_status(series_ids, status)`.
  Resolving tag names → ids goes through the existing `GET /api/taxonomy`.

## Transport + auth: when the API key actually earns its keep

- **Start on stdio transport.** FastMCP spawned via stdio (how Claude Desktop / Claude
  Code launch local MCP servers) has **no network listener at all** — the OS process
  boundary is the entire trust boundary. This is a full match for "local server only"
  as stated today, and needs **zero auth code**. Don't add an API-key check before
  there's actually a socket for it to guard — it would be pure theater.
- **The trigger point: the moment the transport becomes HTTP/SSE instead of stdio.**
  That's the same moment a network listener exists, and — not coincidentally — the
  same moment a **cloud-based model** could actually participate (it needs a reachable
  URL, almost certainly via a tunnel: Tailscale funnel, Cloudflare tunnel, etc.).
  Local-stdio-only and cloud-reachable-HTTP aren't two points on a spectrum here;
  they're two different transports, and the second one is exactly when auth stops
  being optional.
- **When that happens:** bolt on a minimal API key, read from an env var
  (`LYCHEE_MCP_API_KEY` or similar), checked via FastMCP's HTTP-transport auth hook
  (e.g. a bearer-token / `X-API-Key` check) on every tool call. This is scoped to the
  **MCP server's own listener** — it does not require adding auth to the backend's
  FastAPI app, which stays open/localhost-only per [ADR 12](decisions/12-auth-users.md)
  exactly as it does today; the MCP→backend hop is unaffected.
  - This is literally backlog item **#1** from ADR 12's own auth backlog — "single
    shared password + API key … cheapest, covers 'put it on the internet safely'" —
    just landing on the MCP surface first instead of the whole webapp API. If it ever
    proves out there, promoting the same mechanism to the main API later is a natural,
    already-anticipated next step rather than a new decision.
- **Not required now, so not built now:** rate limiting, per-tool scoping/roles,
  request logging/audit trail. Revisit only if the MCP surface actually goes
  network-reachable — same "don't build it until the transport requires it" logic as
  the API key itself.

## Open before starting (decide at build time, not speculatively now)
- Exact tool list + argument shapes (the four above are illustrative, not final).
- Typed-client generation approach for the Python side (`openapi-python-client` vs.
  hand-rolled `httpx` + the existing `schema` types).
- Whether any bulk backend endpoints (e.g. `PATCH` many series in one call) are worth
  adding once real usage shows the per-item round-trip cost actually matters.
- Whether this warrants its own ADR once scope firms up — plan.md tracks it as a
  proposal for now; an ADR would be the place to formally record the "second REST
  client" decision if/when this actually gets built.

# PART K — `lychee.info` metadata sidecar — ✅ done

> See [ADR 20](decisions/20-lychee-info-metadata.md) for the full schema and rationale.
> This is the **reader** half — parsing + applying a `lychee.info` file found on scan.
> The **writer** half lives externally: [`delfianto/lychee-agents`](https://github.com/delfianto/lychee-agents)'s
> `cosplay-metadata` Claude Skill infers franchise/character/content-rating for gallery
> sets (via folder-name reasoning + web search + viewing sample frames) and writes the
> sidecar directly to disk through its own schema-strict script — a filesystem writer,
> not an `mcp/` tool or a backend API client. Already functional; not part of this repo.

- [x] **Schema + parser** (`ingest/lychee_info.py`) — strict Pydantic (`CamelModel`,
      `extra="forbid"`) schema v1 exactly per the design doc; `parse_lychee_info(raw)`
      raises `LycheeInfoParseError` on bad YAML, a non-mapping, a hallucinated field,
      a bad enum, or an unsupported `schema` version.
- [x] **Apply via the exact same lock mechanism `PATCH /api/series/{id}` uses** —
      `catalog.service._apply_metadata_fields` was extracted from `update_series` as
      the shared core; `apply_lychee_info` builds the same `SeriesUpdate`-shaped
      fields dict from a parsed file and calls it — zero new locking logic.
      `SeriesUpdate` gained a `titles` field (→ `TitleVariant`, union-merged by
      `(language, title)`, never locked — ADR 18's stated merge policy) so the file
      has a path to set title variants at all.
- [x] **Tags:** union-merged (not replaced) via the existing
      `catalog.metadata.reconcile_tags` — unknown tag names auto-create, no new
      "create tag" path.
- [x] **`provider:`** seeds a match via the existing `catalog.matching.set_match`
      (same path the manual match-picker uses) — triggers the normal
      match/refresh flow. **`external:`** merges into `external_ids_json`, mapping
      friendly tracker names to their `Tracker.external_id_key` (`anilist`→`al`, …).
- [x] **`crossovers`:** only the first entry applies (→ `source`/`characters_json`);
      2+ entries warn (multi-franchise would need a new junction table — not built).
- [x] **Kind handling:** a `kind` mismatch is warn-only (`series.kind` is never set
      from the file); `status`/`demographic` on a `kind=gallery` file warn + skip.
- [x] **Re-apply gating:** `Series.metadata_file_hash` (xxh3-128, mirrors
      `Book.partial_hash`) — unchanged file costs nothing on rescan; a malformed
      file's hash is deliberately not stored, so it re-warns every scan until fixed.
      `Series.metadata_file_version` mirrors the file's `generated.version` (audit
      trail only). Now part of the single squashed initial-schema migration (see
      PART L — migrations were re-squashed when tag_alias was added).
- [x] **Scan wiring:** `ingest/scanner.py` reads `lychee.info` at a series' folder
      (or, for `kind=gallery`, each per-work folder — same level as `Cover.avif`);
      `ScanSummary` gained `lychee_info_applied`/`lychee_info_warnings`, surfaced as
      `lycheeInfoApplied`/`lycheeInfoWarnings` on the scan task's `TaskOut.result`
      (same slot `thumbsGenerated` already uses). No container/exclusion-logic
      changes needed — `.info` was already outside every media extension allowlist.
- [x] **Tests:** `test_lychee_info.py` (schema validation + `apply_lychee_info`
      mapping/locking/warnings, 19 cases) + `test_lychee_info_scan.py` (scan
      discovery, hash-gated re-apply, edited-file re-apply, malformed-file
      resilience, gallery per-work-folder application, 5 cases). **+24 → 261.**

---

# PART L — Tag aliases — ✅ done

> See [ADR 21](decisions/21-tag-aliases.md) for the full design and rationale.

- [x] **`TagAlias` model** (`taxonomy/models.py`) — id=slug, `name` display form,
      `tag_id` FK (`ondelete="CASCADE"`), globally unique across every group.
      `Tag.aliases` reverse relationship (`cascade="all, delete-orphan"`).
- [x] **`reconcile_tags()` alias tier** (`catalog/metadata.py`) — matches slug,
      then name, then alias, before falling back to creating a new tag. Fixes
      MangaDex sync, the local importer, and `lychee.info`'s `tags:` block at once
      (no schema change needed there — `tags:` was already free-text).
- [x] **`resolve_tag_id()` helper** — same idea for the closed `content_rating`/
      `demographic` enums, except an unresolved value must **not** fall back to
      creating a row: it warns (structured log) and leaves the field untouched.
      Wired into `apply_metadata`'s content-rating/demographic assignment,
      replacing the old bare passthrough — closes the `decisions/10`-documented,
      never-implemented MangaDex `pornographic`→`mature` rename.
- [x] **Display label editability, not a new "familiar terms" field** — `Tag.id`
      (sync key) and `Tag.name` (display label) were already independent.
      Genre/theme/format/content tags needed **zero backend changes** (already
      renamable, already rendered live). `content_rating`/`demographic`
      (`system=True`) needed two fixes: `update_taxonomy()`'s system-row lock now
      protects only `id`/`group`/deletability, not `name`; and the frontend
      dropped its hardcoded rating/demographic label maps in favor of
      `lib/ratingLabels.ts`, which fetches live names from `/api/taxonomy` once
      per session (`AppShell.vue`, alongside `connectTaskStream`) with a static
      fallback until loaded.
- [x] **Settings surface:** `TaxonomyItemOut.aliases: list[AliasOut]`
      (`{id, name, tagId}`) + `POST`/`DELETE /api/taxonomy/{tag_id}/aliases[/{alias_id}]`
      (409 on a slug collision with a real tag or a differently-targeted alias;
      re-adding the same alias→tag pair is a no-op). `ContentPanel.vue` gained
      inline rename (click a name — the affordance didn't exist before this,
      even for already-renamable non-system tags) and alias chips with add/remove.
      MSW mock harness updated in parallel (`mocks/data/taxonomy.ts`, `mocks/handlers.ts`).
- [x] **Seed data:** Ecchi→suggestive, Hentai/Pornographic/NSFW→mature,
      Yaoi/BL→boys-love, Yuri/GL→girls-love (`taxonomy/seed.py`). Demographic
      names updated to macron form (`Shōnen`/`Shōjo`) so the now-DB-driven
      default doesn't regress vs. the frontend's old hardcoded strings.
- [x] **Cleanup:** unified `catalog/metadata.py`'s `_slug()` and
      `taxonomy/service.py`'s `_slugify()` (byte-identical duplicates) into one
      `taxonomy/slug.py`.
- [x] **Migrations re-squashed:** still local/pre-production, so the two
      existing revisions were replaced with one fresh autogenerated initial-schema
      migration including `tag_alias` — same practice as the earlier squash.
      `alembic check`: no drift.
- [x] **Tests:** `test_tag_aliases.py` (alias resolution in `reconcile_tags`,
      `resolve_tag_id` slug/alias/group-mismatch cases, the MangaDex
      `pornographic`→`mature` fix, warn-and-skip on an unresolvable rating, alias
      CRUD + its collision rules, system-tag rename now allowed, 12 cases) +
      `test_taxonomy_api.py` updated for the loosened rename rule. **+12 → 273.**
      Frontend: `bun run typecheck && bun run test && bun run build` clean.

---

# PART M — Content rating: MangaDex-native naming + gallery's own `explicit` tier — ✅ done

> Folded into [ADR 10](decisions/10-tagging-content-rating.md) (content rating) and
> [ADR 21](decisions/21-tag-aliases.md) (the alias-table change) — no separate ADR.

- [x] **Retired the `mature` rename.** `taxonomy/seed.py`'s `_CONTENT_RATINGS`
      is now `safe/suggestive/erotica/pornographic/explicit` (5 system rows, was
      4). MangaDex-synced manga/comic use `pornographic` — MangaDex's own raw
      value — verbatim; gallery (never MangaDex-synced) gets its own top tier,
      `explicit`.
- [x] **Alias table simplified.** The `("Pornographic", "mature")` alias is
      gone — MangaDex's own value now slugifies straight to a matching `Tag.id`,
      no resolution needed. `Hentai`/`NSFW` repointed to `pornographic`.
- [x] **No migration needed** — `content_rating` rows are runtime seed data
      (`seed_taxonomy()`), not baked into the schema. Local dev DBs with old
      `mature` rows just need a reset (`rm backend/lychee.db`) to re-seed clean.
- [x] **Updated in lockstep:** `catalog/models.py`/`service.py` (validation
      set), `ingest/lychee_info.py` (`Literal`), `dev_seed.py` (6 `mature` →
      `pornographic`, all manga/comic), frontend `types/index.ts`
      (`ContentRating` union), `lib/display.ts` (badge class/label maps),
      `FilterPanel.vue` (all 5, mixed-kind browse), `EditSeriesModal.vue`
      (kind-conditional: `pornographic` for manga/comic, `explicit` for
      gallery), mock fixtures (`mocks/data/{taxonomy,series}.ts`).
- [x] **Tests:** `test_tag_aliases.py`, `test_lychee_info.py`,
      `test_taxonomy_api.py`, `test_series_api.py`, `test_seed.py` (content
      rating count 4→5, system row count 8→9) updated for the new values.
      Backend: `uv run pytest` (273 passed) + `ruff format/check` + `basedpyright`
      clean. Frontend: `bun run typecheck && bun run test` clean.

---

## Handy commands
- Backend: `cd backend && uv run uvicorn src.main:app --reload` (auto-migrates+seeds).
  Demo data: `uv run python -m src.dev_seed`. Checks: `uv run ruff check . && uv run basedpyright && uv run pytest`.
- Regen API client: `cd backend && uv run python scripts/dump_openapi.py` then `cd frontend && bun run api:gen`.
- Frontend: `cd frontend && bun run dev` (proxies /api → :8000). `bun run typecheck`.
