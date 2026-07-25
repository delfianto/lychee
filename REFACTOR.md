# Refactor analysis — code & design quality

Critical review of the backend (`backend/src`) and frontend (`frontend/src`) after
the MangaDex + trackers work. Focus: god objects, misplaced responsibilities, and
comments that couple the code to planning docs (PLAN.md phases, ADR numbers).

Legend: **[H]** high priority · **[M]** medium · **[L]** low / nice-to-have.

---

## 1. God objects

### 1.1 [H] `frontend/src/views/SettingsView.vue` — was 1093 lines
One component owned **eight** unrelated concerns, each with its own state, API
calls, and template block. Decomposing along the tab seam into
`views/settings/*Panel.vue`, each owning its state, `load*()`, and SSE subscription.

**Status — partially done (1093 → 674 lines):**
- [x] `ContentPanel.vue` (taxonomy table)
- [x] `AboutPanel.vue` (server info + library summary)
- [x] `DownloadsPanel.vue` (downloads queue + sync card + its own SSE wiring)
- [ ] The **"general" tab** (~674 lines left in SettingsView) still bundles Libraries,
      Provider + MangaDex account, Trackers (+ connect modal), and Appearance/Reader.
      Split next into `LibrariesPanel` / `ProviderPanel` / `TrackersPanel`
      (+`TrackerConnectModal`) / `AppearancePanel`, leaving SettingsView a shell
      (section rail + theme + `<component v-else-if>`). Scan + import SSE handlers
      move to Libraries/Provider respectively.

### 1.2 [H] `backend/src/integrations/service.py` — 382 lines, 5 concerns
Mixes provider-config CRUD, **MangaDex account + follows import**, tracker
connect/OAuth, sync, and About. The MangaDex account/import block (≈120 lines)
is the worst part — see §2.1.

**Fix:** split by concern:
- `integrations/providers.py` — provider *config* CRUD (`list/update`, `_provider_out`, `_get_provider`).
- `integrations/trackers.py` — tracker CRUD + connect/callback/login/disconnect.
- `integrations/sync.py` — sync state + the sync task.
- `integrations/about.py` — About.
- `providers/mangadex_account.py` — MangaDex connect/disconnect/import (moved out of integrations).
- delete `integrations/service.py`; the router imports the concrete functions.

### 1.3 [M] `backend/src/catalog/service.py` — 439 lines
The read-service (list/detail/chapters/updates/dashboard/search/related/art/
summaries + DTO mappers) is bloated by a **provider-matching** block
(`match_candidates`, `set_match`, `unlink_match`, `auto_match_*`, `refresh_*`) that
is a separate concern.

**Fix:** extract `catalog/matching.py` (search/match/auto-match/refresh);
`catalog/service.py` keeps reads + `update_series`. `catalog/router.py` and
`library/service.py` import matching from the new module.

### Borderline (leave as-is, noted)
- `catalog/repository.py` (451) — large but **cohesive**: it's the read-query layer
  (filters, keyset pagination, chapters, updates, dashboard). Not a god object.
- `ingest/scanner.py` (319), `dev_seed.py` (277) — single-purpose; acceptable.
- `frontend/src/api/queries.ts` (354) — a flat grab-bag of query functions; could be
  split by domain (series / feeds / gallery / match) later. **[L]**

---

## 2. Antipatterns & design smells

### 2.1 [H] Misplaced responsibility — MangaDex specifics inside generic `integrations`
`integrations/service.py` imports `MangaDexProvider`, `mangadex_auth`,
`mangadex_client`, and builds authed httpx clients + upserts `Series` into a
"MangaDex" library. A generic integrations layer should not know MangaDex's
OAuth/GraphQL/library details. → move to `providers/mangadex_account.py` (§1.2).
`_authed_provider` (inline httpx client construction) moves with it.

### 2.2 [M] Comments couple code to planning docs
~39 `ADR NN` references and ~35 `PART F` / `M0–M5` / `B2–B7` references live in
docstrings and inline comments across ~25 files. These describe *when/why in the
plan* a thing was built, not *what it does*, and rot the moment PLAN.md changes.
→ strip the tags; make each docstring state the file/class's responsibility. Also
drop "is a follow-up", "lands in B6", "deferred" phrasing that describes the plan
rather than the code.

### 2.3 [L] Repeated `queue.submit(...) → TaskOut.model_validate` boilerplate
Five call sites (`enqueue_scan_*`, `create_downloads`, `refresh_series`,
`import_follows`, `run_sync`) do `task = queue.submit(...); return
TaskOut.model_validate(task)`. → add `queue.submit_task(kind, label, work) ->
TaskOut` (or a `to_task_out` helper) and call it once.

### 2.4 [L] Cross-service reach: `library/service.py` → catalog auto-match
The scan worker calls into catalog matching. Acceptable (a scan legitimately
triggers matching), but after §1.3 it should import from `catalog.matching`, and
the direction (library → catalog) should be the only such edge.

### 2.5 [L] `catalog.service.cover_url(series_id, cover_source=None)` dual-use
Two calling conventions via a default arg. Minor; leave unless it grows.

---

## 3. Comment cleanup scope (what "proper" looks like)

Replace planning/decision references with a one-line statement of responsibility:

| Before | After |
|---|---|
| `"""Reading-progress service (ADR 11). Drives unread / lastRead…"""` | `"""Reading-progress service: drives unread / lastRead / continue-reading."""` |
| `"""MangaDex provider (ADR 13, PART F) — … land in PART F M1–M5 …"""` | `"""MangaDex provider: chapter listing + page download + metadata/search."""` |
| `# progress migration on restore is a follow-up (ADR 07 tryRestore).` | `# soft-delete drops derived chapters; restore doesn't migrate their progress.` |
| `total_chapters from lastChapter; /aggregate not needed (M1)` | `total_chapters comes from the manga's lastChapter attribute.` |

Files with references (from grep): `tasks/*`, `progress/*`, `providers/*`,
`ingest/*`, `catalog/{models,schema,media,service,metadata,repository}.py`,
`integrations/{models,service}.py`, `taxonomy/*`, `downloads/*`, `media/*`,
`trackers/*`, `core/{config,crypto}.py`, and `frontend/.../SeriesDetail.vue`.

---

## 4. Execution plan (each step: verify `ruff`+`basedpyright`+`pytest` [+ FE build], then commit)

1. [x] **This file.**
2. [x] **Backend god-object split** — MangaDex account/import → `providers/mangadex_account.py`;
   `integrations/service.py` → `providers.py` / `trackers.py` / `sync.py` / `about.py`. (§1.2, §2.1.)
3. [x] **Extract `catalog/matching.py`** from `catalog/service.py`. (§1.3.)
4. [x] **`queue.submit_task`** collapses the enqueue boilerplate. (§2.3.)
5. [x] **Backend comment cleanup** — ADR/PLAN refs stripped across ~35 files. (§2.2, incl. FE.)
6. [~] **Frontend SettingsView split** — Content/About/Downloads panels done (1093→674); the
   general-tab panels remain (§1.1).
7. [x] **Frontend comment cleanup** (done with step 5).

Out of scope: `queries.ts` domain split (§1.3 borderline), FTS/search, and anything
behavioural — this stayed a **pure refactor**; the test suite (**129 green**) and the
API/DTO shapes are unchanged throughout.
