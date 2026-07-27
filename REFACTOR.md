# lychee — Refactor & Code Quality Backlog

> Tracker for issues found in a deep code-quality pass (backend + frontend), so they
> don't get lost. Not a build plan — see `PLAN.md` for feature status. Living doc;
> check items off (and add new ones) as they're addressed.
>
> Legend: `[x]` fixed · `[ ]` open · `[~]` partially addressed · `[—]` won't fix (note why)
>
> Source: deep code review, 2026-07-25.

---

## Backend

### Bugs / correctness

- [x] **Swallowed exception can corrupt session state.** `backend/src/downloads/downloader.py:264-269`
      (`plan_downloads`) did `except Exception: pass` around `upsert_provider_chapters`, with no
      `session.rollback()`. If the wrapped call fails after a partial flush, the session was left needing
      rollback and the *next* query in the same function raised an unrelated `PendingRollbackError` —
      the opposite of the comment's intent ("planning must not fail on index write"). **Fixed** to mirror
      the sibling call site (`catalog/remote_chapters.py:137-142`): `except Exception as exc:
      session.rollback(); logger.warning(...)`. Regression test:
      `tests/test_downloads_api.py::test_plan_downloads_survives_remote_index_write_failure` — forces a
      real flush failure (bad FK) and asserts the session is still usable afterward; verified it
      reproduces the original `PendingRollbackError` when run against the old code.

- [x] **Gallery item thumbnails all land in one shard.** `backend/src/catalog/media.py:392-394`
      (`_gallery_item_thumb_id`) built ids as `f"gi-{series_id}-{index}"`; the thumbnail store shards
      by the id's first two chars (`backend/src/media/thumbnails.py:39-40`), which was always `"gi"`.
      **Fixed** — id is now `f"{series_id}-gi-{index}"` so sharding is driven by the series id like every
      other thumbnail kind. Regression test: `tests/test_media_api.py::
      test_gallery_item_thumb_shards_by_series_not_fixed_prefix`; verified it fails against the old prefix.

- [x] **Orphaned download rows become permanently invisible.** `backend/src/downloads/service.py:27-46`
      (`_tasks_out`) silently drops any `DownloadTask` whose `series_id` no longer resolves.
      `DownloadTask.series_id` was `ON DELETE SET NULL` — the only series-referencing FK in the schema not
      using `CASCADE` (every sibling table — progress, collections, taxonomy, catalog children — cascades).
      **Fixed**: `series_id` is now non-nullable with `ON DELETE CASCADE` (migration `44d2dfce9ddb`,
      data-cleans any pre-existing orphaned rows before enforcing NOT NULL). Regression test:
      `tests/test_downloads_api.py::test_deleting_series_cascades_its_download_tasks`; verified it fails
      against the old `SET NULL` behavior.
      **Side finding fixed in the same pass:** `tests/conftest.py`'s `db_engine` fixture never set `PRAGMA
      foreign_keys=ON` (production's engine does), so no `ON DELETE CASCADE`/`SET NULL` behavior anywhere
      in the schema was actually exercised by the test suite — added the pragma; full suite re-verified
      green with real FK enforcement on.

- [x] **Unlocked module-level token cache.** `backend/src/providers/mangadex_account.py:49`
      (`_TOKEN_CACHE`) was a plain dict read/written with no lock; correctness depended entirely on the
      task queue being hardcoded to `max_workers=1`, an invariant nothing in this file enforced. MangaDex
      rotates refresh tokens on every use — a lost update on a race would permanently break the stored
      connection. Latent (every current call site happens to run on the queue), but not guaranteed by
      anything the module itself controls. **Fixed** — added `_TOKEN_LOCK` (`threading.Lock`) around the
      whole check-cache/refresh/persist/cache-write section, not just the dict access (a lock on the dict
      alone wouldn't stop two threads from both redeeming the same stale refresh token before either
      commits). Regression test:
      `tests/test_account_api.py::test_access_token_refresh_is_serialized_under_concurrency` — 4 threads
      call `_access_token` concurrently against a slowed-down fake `refresh_grant`; verified it fails
      (`call_count == 4`) with the lock removed and passes (`call_count == 1`) with it.

- [x] **Login-CSRF gap in tracker OAuth connect flow.** `backend/src/integrations/trackers.py:74-80`
      (`begin_connect`) sent a hardcoded `state=tracker_id` to AniList/MyAnimeList's authorize URL, and
      `TrackerCallback` had no `state` field — `complete_connect` never verified one came back. The code
      visibly intended state-based CSRF protection but never implemented the verification half. Narrow
      blast radius (single-user, no auth layer — ADR 12; each installation also registers its own OAuth
      client rather than sharing one, which further narrows the classic exploit), but still a real
      confused-deputy gap: with a fixed, universally-known state, a code obtained outside the flow this
      instance actually started could be redeemed. **Fixed** — cross-cutting change (schema + migration +
      frontend, regenerated via `just api-gen`):
      - `Tracker.state` column (migration `e54a78664e3e`), a random `secrets.token_urlsafe(32)` nonce
        generated per `begin_connect` call and embedded in the authorize URL.
      - `TrackerCallback.state` is now a required field; `complete_connect` verifies it with
        `secrets.compare_digest` before exchanging the code, and clears it after use (one-time, like
        `pkce_verifier`) so a callback can't be replayed.
      - `frontend/src/views/settings/TrackerConnectModal.vue` — no UX change (still "paste the code");
        the state nonce is parsed out of the `authorizeUrl` the backend already returned and round-tripped
        invisibly in the callback POST.
      Regression tests in `tests/test_tracker_api.py`: `test_callback_rejects_missing_or_mismatched_state`,
      `test_callback_state_cannot_be_replayed` (plus the existing `test_callback_completes_...` updated to
      supply the real state); both new tests verified to fail with the check removed.

### Consistency / antipatterns

- [x] **N+1 inconsistency in collections.** `backend/src/collections/service.py:21-28`
      (`_collection_kind`) accesses `entry.series.kind` per member in a loop. `list_collections` eager-loads
      `.entries.series` via `selectinload`, but `create_collection` / `update_collection` / `add_series` /
      `remove_series` called `session.refresh()` without the same eager load (refresh only reloads scalar
      columns, not relationships), triggering one lazy-load query per existing member on every write.
      **Fixed** — added `_reloaded()`, a re-fetch with the same `selectinload` chain as `list_collections`,
      used by all four write paths instead of `session.refresh()`. No behavior change (same output), pure
      query-count fix, so no dedicated regression test was added — covered by the existing
      `test_collections_api.py` suite (still green).

- [—] `backend/src/downloads/router.py:23-46` uses `response_model=None` + manual `model_dump` instead of
      returning a schema — the one departure from the otherwise-universal convention, but justified (two
      response shapes/status codes from one route). Not tracked as a fix; noted so it isn't copied
      elsewhere as a template.

### Test coverage gaps

- [x] Add a test driving a failure inside `upsert_provider_chapters` during `plan_downloads` — added (see
      above), and confirmed it reproduces the original bug when run against the pre-fix code.
- [x] Cover the `gi-{series_id}-{index}` gallery-item sharding path — added in `test_media_api.py` (see
      above) rather than `test_thumbnails.py`, since it's exercised through the gallery-item thumb
      endpoint, not the low-level `ThumbnailStore` unit tests.
- [x] `tests/conftest.py` test DB engine now enables `PRAGMA foreign_keys=ON`, matching production — was
      silently off, so cascade/set-null FK behavior was untested project-wide (see above).
- [x] Once the tracker CSRF fix lands, add a test asserting the callback rejects a missing/mismatched
      `state` — done as part of the fix above (`test_callback_rejects_missing_or_mismatched_state`,
      `test_callback_state_cannot_be_replayed`).

---

## Frontend

### Bugs / correctness

- [ ] **`FilterPanel.vue` has no `defineEmits` and mutates props directly.**
      `frontend/src/components/FilterPanel.vue` — `cycleTag()` writes into `props.filters.tags`, `toggle()`
      calls `.add()`/`.delete()` on the prop's `Set`s directly; there is no emit at all. Only works because
      `LibraryView.vue` happens to pass the same live `reactive()` object down. Breaks one-way data flow,
      makes the component unreusable with a copied/immutable filters object, and untestable via the
      emitted-event pattern the rest of the codebase uses (see `ErrorState.test.ts`).
      **Fix:** emit `update:filters` (or per-facet events) and let the parent own the mutation.

- [ ] **Race condition on rapid navigation (no staleness guard), 4 call sites.**
      `frontend/src/views/SeriesDetail.vue:76-81`, `GalleryDetail.vue:33-34`, `ReaderView.vue:33-53`, and
      `frontend/src/api/queries.ts:182-199` (`useSeriesList.fetchPage`) all fire an async load from a route/
      filter watcher with no request generation/abort guard. Navigate quickly (series A → series B) and a
      slower earlier response can resolve after the newer one, overwriting the view with stale data.
      **Fix:** track a per-call generation id and ignore responses that aren't for the latest one (or use
      `AbortController` if `openapi-fetch` supports it here).

- [ ] **Optimistic UI update not guarded by the actual result.** `frontend/src/views/settings/ContentPanel.vue:91-94`
      (`removeTax`) removes the tag from the local list unconditionally, even when `api.DELETE` returns an
      error (e.g. "tag in use") — the row disappears from the UI until the next full reload despite the
      delete having failed.

### Layering / architecture violations

- [ ] **~11 Settings panels bypass `api/queries.ts` entirely**, calling `api.GET/POST/PATCH/DELETE` directly
      and hand-rolling response mapping + error handling instead of going through the layer `frontend/AGENTS.md`
      defines for exactly this: `AccountsPanel.vue`, `PathBrowserModal.vue`, `ImportPanel.vue`,
      `LibrariesPanel.vue`, `MangaDexConnectModal.vue`, `ContentPanel.vue`, `DownloadsPanel.vue`,
      `AddLibraryModal.vue`, `TrackerConnectModal.vue`, `ProviderPanel.vue`, `AboutPanel.vue`.
      Concretely causes discarded backend error messages — `AddLibraryModal.vue:30-33`,
      `MangaDexConnectModal.vue:94-97`, `TrackerConnectModal.vue:26-29,39-42,52-55` all show one generic
      hardcoded toast string instead of reading `error.error.message`.
      **Fix:** move these calls into `queries.ts` (or a settings-specific sibling module) so error-body
      parsing and response mapping are written once.

- [ ] **`toSeries` bridges the generated schema with a full unchecked cast.** `frontend/src/api/queries.ts:18-19`
      — `return s as unknown as Series;`. Partly deliberate (a file-top comment explains the wider-backend-
      union-to-narrow-UI-union bridge), but unlike `toChapter` a few lines below (real field-by-field
      mapping), a backend value outside the narrow UI union (bad data, a new enum) is caught nowhere and
      silently misrenders (e.g. `statusColor[series.status]` → `undefined`).
      **Fix:** give `toSeries` the same explicit per-field mapping `toChapter` already uses.

### State management inconsistency

- [ ] **Duplicated, disconnected localStorage-backed state.** "Library density" is independently
      reimplemented (same key, no shared reactivity) in `frontend/src/views/LibraryView.vue:21-29`,
      `AddedView.vue:10-13`, and `views/settings/AppearancePanel.vue:100-105` — changing it in Settings has
      no effect on an already-mounted view. Same pattern for `lychee.listsDefaultTab` between
      `ListsView.vue:18-24` and `AppearancePanel.vue:107-112`. Contrast with `theme`/`fontSize`/
      `readerSettings`, each a proper shared reactive singleton in `lib/`.
      **Fix:** extract `lib/density.ts` (and fold the lists-default-tab key in) mirroring `lib/fontSize.ts`'s shape.

### Styling convention drift

- [ ] `frontend/src/components/ChapterFeed.vue:29` (`w-[2.333rem]`) and `RecentUpdates.vue:18`
      (`w-[3.333rem]`) hand-compute a 2:3 cover box instead of using the existing `.cover` utility
      (`style.css:453-457`), whose comment explicitly says it exists to prevent this exact pattern.
      **Fix:** `class="cover h-14 shrink-0 rounded"` reproduces the same box without the magic number.
- [—] Minor/secondary, lower priority: `text-[10px]`/`text-[11px]` in `DownloadsPanel.vue:259` and
      `PathBrowserModal.vue:316`; `!z-[1100]` in `PathBrowserModal.vue:189` (already comment-justified).

### Component complexity / duplication

- [ ] **`UnreadView.vue` and `UpdatesView.vue` are near-duplicates** — identical except the boolean passed
      to `fetchUpdates()`, the heading, and empty-state copy. **Fix:** collapse into one
      `ChapterFeedView.vue` parameterized by a prop/route meta.
- [ ] **`SeriesDetail.vue` (482 lines, 16 top-level refs) carries a full inline match-search modal**
      (`matchOpen`/`matchQuery`/`matchLoading`/`matchResults`/`runMatchSearch`/`openMatch`/`pickMatch`,
      ~40 lines state/logic + ~35 lines template, `SeriesDetail.vue:439-476`). Self-contained enough to
      extract into `MatchSeriesModal.vue`, matching the precedent of `EditSeriesModal.vue`.
- [ ] **Dead/unwired controls, misleading as live UI:** `ChapterList.vue:179-182` (language `<select>`,
      no `v-model`), `ChapterList.vue:192` ("Newest" sort button, no `@click` handler),
      `AboutPanel.vue:65,72-74` ("Check for updates" button + three `href="#"` links), and
      `DownloadsPanel.vue:161-164` (an `if` block whose body is only a leftover comment).
      **Fix:** wire them up, remove them, or visibly disable/mark as "coming soon."

### Accessibility (extends the sweep `PLAN.md` already flags as partial)

- [ ] **Tab strips with no keyboard path.** `ChapterList.vue:164-174`, `ListsView.vue:71-81`,
      `LibraryView.vue:236-246` render `role="tab"` on an `<a>` with only `@click` — no `href`, `tabindex`,
      or Enter/Space handling; not reachable or operable via keyboard/AT.
      **Fix:** add `tabindex="0"` + keydown handler, or use `<button>`.
- [ ] **No focus trap in any modal** — `ConfirmDialog.vue`, `PromptDialog.vue`, `EditSeriesModal.vue`,
      `AddLibraryModal.vue`, `MangaDexConnectModal.vue`, `TrackerConnectModal.vue`, `PathBrowserModal.vue`,
      and `SeriesDetail.vue`'s inline match modal all close on Escape but never trap Tab focus.
- [ ] **Informative images with empty `alt`:** `Lightbox.vue:132-137` (main viewer image),
      `SeriesDetail.vue:461` (match-candidate cover), `ChapterList.vue:300` (art covers). Contrast with the
      correct `alt="" aria-hidden="true"` on `SeriesDetail.vue:247-252`'s genuinely decorative backdrop.

### Test coverage — priority order (cheap → expensive)

Current state: 3 test files (`api/queries.test.ts`, `components/ErrorState.test.ts`,
`lib/description.test.ts`) against ~7,900 lines of source; no coverage tool configured at all.

1. [ ] `frontend/src/api/format.ts` — `relativeTime`: pure, deterministic with `vi.useFakeTimers()`, zero
       current coverage, used on every dashboard/updates/chapter row.
2. [ ] `frontend/src/lib/sort.ts` — `sortSeries`: pure, trivial, same shape as the existing
       `buildLibraryQuery` test to copy from.
3. [ ] Extend `frontend/src/api/queries.test.ts` — cover `toChapter`'s nullish-coalescing defaults and the
       error-body→`Error` path in `queueDownload`/`deleteChapterLocal` (success + `{error:{message}}`
       failure) — the layer the whole app's error UX depends on, almost entirely untested.
4. [ ] `frontend/src/stores/collections.ts` — `toggleSeries`/`hasSeries`/`removeSeries` optimistic-update
       logic (needs `setActivePinia(createPinia())` in the test setup). Only Pinia store in the app.
5. [ ] `frontend/src/lib/readerSettings.ts` — `load()`'s malformed-JSON fallback + defaults-merge behavior.
6. [ ] `frontend/src/components/ChapterList.vue` — mount-test gating predicates (`canDownload`/`canDelete`/
       `isInFlight`) and emitted-event contracts (`download`/`deleteChapter` fire with the right id).
7. [ ] `frontend/src/api/events.ts` — dedup/cap-at-50 and `.done`/`.failed` → `onTaskDone` dispatch (needs a
       fake `EventSource`/`MessageEvent` harness).
8. [ ] Full view mounts last (highest value, highest setup cost — router + multi-endpoint + SSE mocking):
       `SeriesDetail.vue`, `ReaderView.vue`, `LibraryView.vue`.

---

## Notes on things intentionally *not* tracked here

Good/positive patterns from the review (path-traversal defenses, atomic cache writes, the FTS5 parameterized
query, `CamelModel`/`UtcDatetime`, `api/events.ts`'s `EventSource` singleton, modal lifecycle cleanup, etc.)
aren't listed — this file tracks fixes, not praise. Don't regress them while working through the above.
