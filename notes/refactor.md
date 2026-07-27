# lychee — Refactor & Code Quality Backlog

> Tracker for issues found in a deep code-quality pass (backend + frontend), so they
> don't get lost. Not a build plan — see `plan.md` for feature status. Living doc;
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

### Dependencies / deprecations

- [ ] **`starlette.testclient` warns its `httpx` integration is deprecated.** Surfaces on every
      `pytest` run (`just be-check` / `just check`):
      `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install
      httpx2 instead` — from `.venv/lib/python3.14/site-packages/fastapi/testclient.py:1`
      (FastAPI/Starlette's own import), not code in this repo. First noticed 2026-07-27 running the
      full CI gate. No action yet: nothing here currently depends on `httpx2`, and it isn't a drop-in
      swap until Starlette actually cuts `TestClient` over — just tracked so the warning isn't
      mistaken for something the mcp/ or backend httpx usage introduced. Revisit when Starlette/FastAPI
      ship the real migration path.

---

## Frontend

### Bugs / correctness

- [x] **`FilterPanel.vue` has no `defineEmits` and mutates props directly.**
      `frontend/src/components/FilterPanel.vue` — `cycleTag()` wrote into `props.filters.tags`, `toggle()`
      called `.add()`/`.delete()` on the prop's `Set`s directly; there was no emit at all. Only worked
      because `LibraryView.vue` happened to pass the same live `reactive()` object down. **Fixed** — the
      component now only reads `props.filters` and emits `set-tag-mode` / `toggle-tag` / `toggle-rating` /
      `toggle-demographic` / `toggle-status` / `toggle-read-state`; `LibraryView.vue` handles each event and
      owns the mutation (`cycleTag`/`toggleInSet` helpers, same behavior as before). No other consumer of
      `FilterPanel` existed. Added `components/FilterPanel.test.ts` (3 tests) asserting the emit contract
      and that the prop object is never mutated by the component itself.

- [x] **Race condition on rapid navigation (no staleness guard), 4 call sites.**
      `SeriesDetail.vue`, `GalleryDetail.vue`, `ReaderView.vue`, and `api/queries.ts`'s
      `useSeriesList.fetchPage` all fired an async load from a route/filter watcher with no request
      generation guard — navigate quickly and a slower earlier response could resolve after the newer one,
      overwriting the view with stale data. **Fixed** — added `lib/staleGuard.ts` (a tiny shared
      generation-counter helper: `next()`/`isCurrent(token)`) and applied it at all 4 sites; `SeriesDetail`
      shares one guard between its full `load()` and its lighter `reloadChapters()` since both write
      `volumes.value` and can race each other too. Regression tests: `lib/staleGuard.test.ts` (the helper
      itself) and `api/queries.test.ts`'s new "stale-response guard" test (two overlapping `reload()` calls
      resolving out of order — the newer one's data wins); verified the `queries.ts` test fails with the
      guard check removed.

- [x] **Optimistic UI update not guarded by the actual result.** `frontend/src/views/settings/ContentPanel.vue:91-94`
      (`removeTax`) removed the tag from the local list unconditionally, even when `api.DELETE` returned an
      error (e.g. "tag in use") — the row disappeared from the UI until the next full reload despite the
      delete having failed. **Fixed** — checks `error` first, toasts the backend's message (or a fallback)
      and returns without touching the list on failure. (Left as an inline fix, not routed through
      `queries.ts` — see the separate settings-panels layering item below, which covers this file too.)

### Layering / architecture violations

- [x] **~11 Settings panels bypass `api/queries.ts` entirely**, calling `api.GET/POST/PATCH/DELETE` directly
      and hand-rolling response mapping + error handling instead of going through the layer `frontend/AGENTS.md`
      defines for exactly this: `AccountsPanel.vue`, `PathBrowserModal.vue`, `ImportPanel.vue`,
      `LibrariesPanel.vue`, `MangaDexConnectModal.vue`, `ContentPanel.vue`, `DownloadsPanel.vue`,
      `AddLibraryModal.vue`, `TrackerConnectModal.vue`, `ProviderPanel.vue`, `AboutPanel.vue`.
      Concretely caused discarded backend error messages — several showed one generic hardcoded toast
      string instead of reading `error.error.message`. **Fixed** — new `api/settingsQueries.ts` (a
      settings-specific sibling to `queries.ts`, per the fix direction originally noted here), covering
      providers, trackers, libraries, the server path browser, taxonomy, downloads/sync, and local import
      (~30 functions). Added `apiErrorMessage()` to `queries.ts` (the one place the
      `{"error":{"code","message"}}`/`{"detail"}` parsing happens now — also backfilled into
      `queueDownload`/`deleteChapterLocal`, which had their own inline copies) and reused it throughout.
      Callers now surface the backend's actual error message via `catch (e) { toast(e instanceof Error ?
      e.message : ...) }` instead of a fixed string. Also fixed a real latent bug found while migrating
      `PathBrowserModal`'s `makeDirectory`: the 409-conflict check read `.status` off the *error body*
      (`{"error":{"code","message"}}` has no such field), not off the HTTP response, so "a folder with that
      name already exists" could never actually show — now checks `response.status === 409` and the fix was
      verified live (create a folder, create it again → the specific message appears).
      All 11 files' `api.*` call counts confirmed at 0; full `just fe-check` green; verified live via a
      14-check Playwright sweep across every Settings panel (General/Libraries/Content/Downloads/About) plus
      a dedicated create → duplicate-create round trip for the mkdir 409 fix — no console errors anywhere,
      real dev data loaded/toggled/browsed correctly end to end.

- [x] **`toSeries` bridges the generated schema with a full unchecked cast.** `frontend/src/api/queries.ts:18-19`
      — `return s as unknown as Series;`. **Fixed** — replaced with an explicit per-field mapper matching
      `toChapter`'s style (each narrow-union field cast individually, nullable fields `?? undefined`),
      including `tags[]` (previously not mapped at all, so `Tag.group`'s narrow union went unchecked too).
      `bun run typecheck` clean after the change confirms every field the codebase actually reads was
      covered.

### State management inconsistency

- [x] **Duplicated, disconnected localStorage-backed state.** "Library density" was independently
      reimplemented (same key, no shared reactivity) in `LibraryView.vue`, `AddedView.vue`, and
      `AppearancePanel.vue` — changing it in Settings had no effect on an already-mounted view. Same
      pattern for `lychee.listsDefaultTab` between `ListsView.vue` and `AppearancePanel.vue`. **Fixed** —
      new `lib/density.ts` (mirrors `lib/fontSize.ts`'s shared-singleton shape) with `useDensity()` (fully
      shared, two-way — all three consumers bind directly) and `useListsDefaultTab()` (the persisted
      *default*; `ListsView.vue`'s own current-tab selection seeds from it and stays live-synced via a
      `watch`, but the page's own tab clicks don't write back, preserving the original
      default-vs-current-session distinction).
      Confirmed this was a real, reproducible bug and is now fixed via a live browser check: `AppShell.vue`
      wraps `LibraryView` in `<KeepAlive>`, so visiting `/manga`, changing the default density in Settings,
      then navigating back (no reload, same kept-alive instance) used to leave the old density in place —
      verified failing before the fix and passing after (density toggle reflects the new value immediately
      on nav-back).

### Styling convention drift

- [x] `frontend/src/components/ChapterFeed.vue:29` (`w-[2.333rem]`) and `RecentUpdates.vue:18`
      (`w-[3.333rem]`) hand-computed a 2:3 cover box instead of relying on the existing `.cover` utility
      (`style.css:453-457`, `aspect-ratio: 2/3`), whose comment explicitly says it exists to prevent this
      exact pattern. **Fixed** — dropped the arbitrary width class on both; `.cover` + a fixed height alone
      already renders the identical box (confirmed against `SeriesListCard.vue`'s equivalent
      width-omitted usage), matching the pattern every other `.cover` consumer in the codebase uses.
- [—] Minor/secondary, lower priority: `text-[10px]`/`text-[11px]` in `DownloadsPanel.vue:259` and
      `PathBrowserModal.vue:316`; `!z-[1100]` in `PathBrowserModal.vue:189` (already comment-justified).

### Component complexity / duplication

- [x] **`UnreadView.vue` and `UpdatesView.vue` are near-duplicates** — identical except the boolean passed
      to `fetchUpdates()`, the heading, and empty-state copy. **Fixed** — collapsed into
      `views/ChapterFeedView.vue`, parameterized by an `unreadOnly` route prop (`router/index.ts`'s
      `/updates` and `/unread` routes now both point at it, same pattern already used for `LibraryView`'s
      `libraryKey` prop); both old files deleted.
- [x] **`SeriesDetail.vue` (482 lines, 16 top-level refs) carries a full inline match-search modal**
      (`matchOpen`/`matchQuery`/`matchLoading`/`matchResults`/`runMatchSearch`/`openMatch`/`pickMatch`,
      ~40 lines state/logic + ~35 lines template). **Fixed** — extracted into `components/MatchSeriesModal.vue`
      (`seriesId`/`initialQuery` props, `close`/`matched` emits), matching the precedent of
      `EditSeriesModal.vue`'s no-`open`-prop/parent-mounts-it-only-while-shown pattern (including its own
      `useFocusTrap`). `SeriesDetail.vue` now only owns `matchOpen` + a two-line `onMatched` handler.
      Verified live: the menu item opens the modal pre-filled with the series title, auto-searches and
      shows the real match candidate, focus moves into the modal, and Close works — behavior identical to
      before the extraction, confirmed by screenshot.
- [x] **Dead/unwired controls, misleading as live UI:**
      - `ChapterList.vue:179-182`/`:192` (language `<select>`, "Newest" sort button) — **fixed**: both are
        now real, wired to backend functionality that already existed but was never exposed
        (`GET .../chapters?language=&order=`, `catalog/service.py:list_chapters`). Added `language`/`order`
        props + `update:language`/`update:order` emits to `ChapterList.vue`; `SeriesDetail.vue` owns the
        state and refetches just the chapters (not the whole series) on change.
      - `AboutPanel.vue` ("Check for updates" button + hardcoded "Up to date" badge + three `href="#"`
        GitHub/Docs/Report-an-issue links) — **removed**, per explicit user decision: no backend
        update-check exists and no real URLs were available to wire the links to, so the fake
        "Up to date" status and dead links were actively misleading rather than merely unimplemented.
      - `DownloadsPanel.vue:161-164` (dead `if` block, body only a leftover comment) — **removed**.

### Accessibility (extends the sweep `plan.md` already flags as partial)

- [x] **Tab strips with no keyboard path.** `ChapterList.vue`, `ListsView.vue`, `LibraryView.vue` rendered
      `role="tab"` on an `<a>` with only `@click` — no `href`, `tabindex`, or Enter/Space handling; not
      reachable or operable via keyboard/AT. **Fixed** — converted all three to `<button type="button"
      role="tab">`, which is natively focusable and handles Enter/Space without extra JS. Verified live
      (Playwright): Tab-focusing a tab button and pressing Enter activates it.
- [x] **No focus trap in any modal** — `ConfirmDialog.vue`, `PromptDialog.vue`, `EditSeriesModal.vue`,
      `AddLibraryModal.vue`, `MangaDexConnectModal.vue`, `TrackerConnectModal.vue`, `PathBrowserModal.vue`,
      and `SeriesDetail.vue`'s inline match modal all closed on Escape but never trapped Tab focus. **Fixed**
      — new `lib/focusTrap.ts` (`useFocusTrap(container, active)`), wired into all 8. Two distinct
      lifecycle shapes needed handling: components with a real `open` prop that stay mounted
      (ConfirmDialog/PromptDialog/the match modal) toggle `active`; components with no `open` prop that the
      parent mounts/unmounts instead (the other 5) pass a static `ref(true)` — for those, relying only on
      `watch(active, ...)` never fires the "closed" branch since the value never changes, so focus-restore
      and listener cleanup silently never ran. Caught this by actually testing in a browser (a DOM-substring
      check gave a false pass — `document.activeElement` had fallen back to `<body>`, whose `textContent`
      trivially contains everything); fixed by also cleaning up unconditionally in `onUnmounted`. Regression
      tests: `lib/focusTrap.test.ts` (3 tests, including the exact unmount-restores-focus case that caught
      the bug — verified it fails without the `onUnmounted` fix) plus a live Playwright check of both
      lifecycle shapes (Tab-trapping, focus auto-entry, and focus-restore-on-close, confirmed via exact DOM
      node identity, not text matching).
- [x] **Informative images with empty `alt`:** `Lightbox.vue`'s main viewer image, `SeriesDetail.vue`'s
      match-candidate cover, `ChapterList.vue`'s art covers. **Fixed** — match-candidate cover now uses the
      candidate's title; the other two lack any per-item label in their data, so given an indexed
      description (`"Item N of M"` / `"Related art N"`) rather than leaving them empty. Left
      `SeriesDetail.vue`'s blurred backdrop image alone — it already correctly has `alt=""
      aria-hidden="true"` since it's genuinely decorative.

### Test coverage — priority order (cheap → expensive)

Starting state: 3 test files (`api/queries.test.ts`, `components/ErrorState.test.ts`,
`lib/description.test.ts`) against ~7,900 lines of source; no coverage tool configured at all.

1. [x] `frontend/src/api/format.ts` — `relativeTime`: pure, deterministic with `vi.useFakeTimers()`, zero
       current coverage, used on every dashboard/updates/chapter row. **Done** — `api/format.test.ts`
       (5 tests: past at every unit, future/clock-skew, and the `numeric:"auto"` → "now" edge case).
2. [x] `frontend/src/lib/sort.ts` — `sortSeries`: pure, trivial, same shape as the existing
       `buildLibraryQuery` test to copy from. **Done** — `lib/sort.test.ts` (5 tests, including that it
       doesn't mutate its input).
3. [x] Extend `frontend/src/api/queries.test.ts` — cover `toChapter`'s nullish-coalescing defaults and the
       error-body→`Error` path in `queueDownload`/`deleteChapterLocal` (success + `{error:{message}}`
       failure) — the layer the whole app's error UX depends on, almost entirely untested. **Done** — 6 new
       tests; extended the file's `vi.mock("./client")` to cover `POST`/`DELETE` alongside the existing
       `GET`.
4. [x] `frontend/src/stores/collections.ts` — `toggleSeries`/`hasSeries`/`removeSeries` optimistic-update
       logic (needs `setActivePinia(createPinia())` in the test setup). Only Pinia store in the app.
       **Done** — `stores/collections.test.ts` (4 tests). Note: the store auto-fetches on creation (`void
       refresh()` inside the setup function) — tests await `flushPromises()` after construction rather than
       calling `refresh()` again, which would otherwise re-fetch with the default (empty) mock and
       overwrite the seeded fixture.
5. [x] `frontend/src/lib/readerSettings.ts` — `load()`'s malformed-JSON fallback + defaults-merge behavior.
       **Done** — `lib/readerSettings.test.ts` (4 tests, using `vi.resetModules()` + dynamic `import()` per
       test since `settings` is a module-level singleton seeded once on import).
6. [x] `frontend/src/components/ChapterList.vue` — mount-test gating predicates (`canDownload`/`canDelete`/
       `isInFlight`) and emitted-event contracts (`download`/`deleteChapter` fire with the right id).
       **Done** — `components/ChapterList.test.ts` (8 tests; stubs `RouterLink` via `RouterLinkStub` since
       downloaded rows render one).
7. [x] `frontend/src/api/events.ts` — dedup/cap-at-50 and `.done`/`.failed` → `onTaskDone` dispatch (needs a
       fake `EventSource`/`MessageEvent` harness). **Done** — `api/events.test.ts` (7 tests): a minimal
       `FakeEventSource` class stubbed via `vi.stubGlobal`, `vi.resetModules()` per test since `source`/
       `tasks` are module-level singletons seeded by `connectTaskStream()`.
8. [ ] Full view mounts last (highest value, highest setup cost — router + multi-endpoint + SSE mocking):
       `SeriesDetail.vue`, `ReaderView.vue`, `LibraryView.vue`.

---

## Notes on things intentionally *not* tracked here

Good/positive patterns from the review (path-traversal defenses, atomic cache writes, the FTS5 parameterized
query, `CamelModel`/`UtcDatetime`, `api/events.ts`'s `EventSource` singleton, modal lifecycle cleanup, etc.)
aren't listed — this file tracks fixes, not praise. Don't regress them while working through the above.
