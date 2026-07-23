# Overview 4 — Reading Tracker

Read-progress model, multi-user, and syncing progress with external clients/providers.
Per-project detail: [komga](komga/README.md) · [kamiyomu](kamiyomu/README.md) · [mango](mango/README.md) · [lanraragi](lanraragi/README.md).

## Comparison

| Aspect | Komga | KamiYomu | Mango | LANraragi |
|---|---|---|---|---|
| Where stored | `READ_PROGRESS` table | `chapter_progress` (LiteDB) | **`info.json` files** on disk | archive Redis hash fields |
| Granularity | per **book**, per **user**; page int + Readium `R2Locator` for EPUB | per **chapter**, per page; single user | per **entry**, per user; page int | per **archive**; single shared page int |
| Key | `(BOOK_ID, USER_ID)` | `(LibraryId, ChapterDownloadId)` | `progress[username][entry_name]` | archive `progress` field |
| Completion | explicit `COMPLETED` bool + `READ_DATE` | `IsCompleted` (last page reached) | `progress == pages` | `progress/pagecount > 0.85` heuristic |
| Extra fields | device id/name; series-level aggregate counts (`READ_PROGRESS_SERIES`) | `LastPageRead, TotalPages, LastReadAt` | `last_read` timestamp per user | `lastreadtime`, `isnew` flag; "stamps" annotations |
| Multi-user | **yes** (per-user rows + content restrictions) | **no** (global) | **yes** (username-keyed in JSON) | **no** (one shared value) |
| Update trigger | reader/client PUT | HTMX scroll event → POST | page turn → JSON write (mutex/dir) | `PUT /api/archives/{id}/progress/{page}` |
| External sync | **KOReader** (`/koreader/`), **Kobo** (`/kobo/{token}/`, KEPUB, SyncPoints) | Kavita push, Gotify (outbound only) | **none** (OPDS catalog only) | **Tachiyomi/Mihon** via the plain REST API |
| Reading position fidelity | page (DIVINA/PDF) + fragment→R2Locator (EPUB) | page index | page index | page index |

## Patterns & divergences

- **The right store is a per-user relational table.** Komga's `READ_PROGRESS(BOOK_ID, USER_ID, PAGE, COMPLETED, READ_DATE, device_id, device_name, locator)` is the model to copy. Mango's `info.json` approach is explicitly flagged (by its own analysis and ours) as an anti-pattern: not queryable, write-contention under concurrent readers (mutex per directory), and **lost when files are re-scanned into new entries**. LANraragi's single shared integer and KamiYomu's user-less record are both painful to make multi-user later.
- **Separate `completed` from `page == last`.** Komga and KamiYomu both keep an explicit completion flag. Pages can change after re-archiving (Mango even caps stored progress at `pages` to cope), so `current_page == total_pages` is not a reliable "finished" signal. LANraragi's **85%-of-pagecount** "hide completed" heuristic is a nice complement for filtering.
- **EPUB needs more than a page number.** Komga stores a Readium **`R2Locator`** JSON blob (`href` + `locations.position/progression/totalProgression`) for reflowable EPUB, while page ints suffice for CBZ/PDF (DIVINA). Adding a nullable `locator` JSON column from day one avoids a later migration.
- **Series-level rollups pay off.** Komga denormalizes `READ_PROGRESS_SERIES(read_count, in_progress_count)` so "continue reading" / unread badges don't scan every book. Mango computes similar "continue reading / recently added / start reading" home sections (good UX to copy) but does it live over `info.json`.
- **External sync is where the ecosystem value is:**
  - **KOReader sync** (Komga): books are identified by a **KOReader partial MD5** (1 KB read at exponential offsets — must match KOReader's Lua exactly), not the server id; progress strings (`DocFragment[N]`) map to/from the locator.
  - **Kobo sync** (Komga): full device protocol with **SyncPoint** snapshot tables and **KEPUB** conversion — lets a physical Kobo use the server as its store.
  - **Tachiyomi/Mihon** (LANraragi): *no special protocol* — the community extension just calls the normal `/api/archives` + `/progress/{page}` REST endpoints. So a clean REST progress API is most of the work.
  - **Outbound only** (KamiYomu): triggers a Kavita rescan and Gotify push — integration by webhook, not progress sync.

## Recommendation for lychee

- **Schema (per-user, day one):**
  `reading_progress(user_id, book_id, page int, total_pages int, completed bool, read_date, device_id, device_name, locator json null, updated_at)`, PK `(user_id, book_id)`.
  Plus a denormalized `series_read_progress(user_id, series_id, read_count, in_progress_count)` for fast shelves/badges (Komga).
- **Completion:** explicit `completed` flag set by the reader; also expose an 85%-style "effectively finished" filter (LANraragi) for "hide completed".
- **EPUB:** include the nullable `locator` JSON (Readium shape) now; page int for CBZ/PDF.
- **Update API:** a small `PUT /api/books/{id}/progress` (page and/or locator). A scroll-triggered client POST (KamiYomu's HTMX pattern) is a fine low-overhead UI approach.
- **Home sections:** "continue reading / recently added / start reading" (Mango) computed from the relational tables, not JSON.
- **External sync roadmap:**
  1. Make the **REST progress API Tachiyomi/Mihon-friendly** (cheapest big win — LANraragi shows it's just good REST).
  2. Add **KOReader sync** (implement the partial-MD5 identity + progress-string mapping — Komga documents the exact algorithm).
  3. Consider **Kobo sync** later (SyncPoints + KEPUB) — high effort, niche but beloved.
  4. **Outbound webhooks** (Kavita rescan / Gotify / Apprise) are trivial and worth offering (KamiYomu).
- **Avoid:** progress in sidecar files (Mango) and any single-user/global progress design (LANraragi, KamiYomu).
