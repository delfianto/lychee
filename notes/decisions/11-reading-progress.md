# 11 — Reading progress & sync

**Status:** ✅ Accepted

## Context

How lychee tracks "where am I in this book", per user, and how it syncs with the reader ecosystem. Grounded in the four references ([../04-reading-tracker.md]) and prior decisions: [04](04-database-sqlite.md) (`book.page_count`, no page rows), [05](05-domain-model.md) (the `reading_progress` sketch), [10](10-tagging-content-rating.md) (the read-status facet needs per-user state).

What the field teaches us:
- **Komga** — the model to copy: `READ_PROGRESS(book_id, user_id, page, completed, read_date, device, locator)`, per-user; a **denormalized series rollup**; and real external sync (KOReader, Kobo).
- **KamiYomu** — per-page scroll-triggered updates; explicit `IsCompleted`; but single-user.
- **Mango** — good **home-page UX** (continue / recently-added / start-reading) and the "cap progress at page_count" trick — but stores progress in **`info.json` sidecars** (not queryable, write-contention): a clear anti-pattern.
- **LANraragi** — a **single shared** progress int (no per-user): the other anti-pattern; but its **"hide completed at 85%"** heuristic and **page annotations (stamps)** are worth keeping. Its lesson on sync: Tachiyomi/Mihon needs **no special protocol — just a clean REST API**.

## Decision

### Storage — per-user, relational, keyed `(user, book)`

```
reading_progress(
  user_id → user, book_id → book,
  current_page  INT,          -- 1-based; NULL/0 = unstarted
  completed     BOOL DEFAULT 0,
  locator       JSON NULL,    -- Readium R2Locator (reflowable EPUB only)
  device_id     TEXT, device_name TEXT,   -- informational: who last updated
  started_at, last_read_at, completed_at,
  PRIMARY KEY (user_id, book_id))
-- indexes: (user_id, last_read_at DESC)  -- "continue reading"
--          (book_id)                     -- "who has read this"
```

- **Canonical page_count** = `book.page_count` ([04](04-database-sqlite.md)); progress stores only `current_page`, **capped to page_count on read** (Mango's trick) so re-archiving that changes page count never breaks resume.
- **Resume** = open the book at `current_page` — exactly the minimal model from [04](04-database-sqlite.md) ("book has X pages, resume at Y").
- **EPUB**: reflowable ebooks store a Readium **`locator`** (href + progression); page int suffices for CBZ/CBR/PDF (DIVINA). Nullable from day one to avoid a later migration (Komga's lesson).
- Reject sidecar files (Mango) and single-shared progress (LANraragi).

### Completion semantics
`completed` is **explicit** (set when the reader hits the last page, or via mark-as-read) — *separate* from `current_page == page_count`, because pages shift on re-archive. Additionally expose an **"effectively read" filter** using an 85%-of-page_count threshold (LANraragi) for "hide completed" / next-up logic, without mutating the stored flag.

### Series rollup (denormalized, per user)
```
series_read_progress(
  user_id → user, series_id → series,
  read_count INT, in_progress_count INT, book_count INT, last_read_at,
  PRIMARY KEY (user_id, series_id))
```
Updated in the same transaction as a progress change (or recomputed after a bulk op). Powers fast unread badges, series read-state classification (`unread` = 0/0, `read` = read_count == book_count, else `in_progress`) — this is what makes [10](10-tagging-content-rating.md)'s **read-status facet** index-fast, and it's Komga's exact pattern.

### Update API & bulk ops
- `PUT /api/books/{id}/progress` `{page?, locator?, completed?}` — the reader sends on page-turn (client-debounced; KamiYomu's scroll-trigger is fine). Updates `last_read_at`, derives/keeps `completed`, and updates the series rollup.
- Bulk **mark read / unread** at book and series level (Komga `readAll`/`unreadAll`, Mango). Unread resets `current_page=0, completed=0`.
- **Multi-device:** one row per `(user, book)`; `device_*` is informational; conflicts resolve **last-write-wins by `last_read_at`** (simple, adequate for self-hosted).

### Home sections (Mango UX)
Cheap, relational, high-value endpoints: **Continue reading** (in-progress by `last_read_at` desc), **Recently added** (`book.created_at`), **On deck** (next unread book in a series that has progress).

### External sync — scope narrowed (see 15 / 16)
The client is the **webapp only** ([15](15-api-surface.md)), so device/reader-ecosystem sync — Tachiyomi/Mihon, KOReader, Kobo, OPDS Position Sync, Komga-API compatibility — is **out of scope** (documented as options in [../04-reading-tracker.md], not chosen). The one retained external integration is **outbound read-status tracker sync** (AniList / MyAnimeList / Kitsu / MangaUpdates / MangaDex) → [16](16-tracker-sync.md), fed by the per-user progress defined here. Outbound webhooks (Gotify/Apprise) remain a trivial optional add.

## Consequences

- Per-user, queryable progress → multi-user shelves, read-state filters, and sync all fall out naturally.
- The rollup keeps unread badges and the read-status facet O(1)-ish at scale.
- Read-status feeds **tracker sync** ([16](16-tracker-sync.md)); there is no device/OPDS client ecosystem to serve ([15](15-api-surface.md)).
- `locator` reserved now avoids the EPUB migration Komga had to do.

## Follow-ups

- **Bookmarks / annotations** (LANraragi "stamps"): `bookmark(user_id, book_id, page, note, created_at)` — deferred, optional differentiator.
- **Komga-API compatibility** decision → API/OPDS ADR (strategic; affects the whole REST surface).
- **Tracker sync** (AniList/MAL/…) → [16](16-tracker-sync.md); device/reader sync (KOReader/Kobo/OPDS) is out of scope ([15](15-api-surface.md)).
- Per-user content-rating filter interplay ([10](10-tagging-content-rating.md)) → deferred with auth ([12](12-auth-users.md)); per-user rows resolve to a single default user in v1.

## Alternatives considered

- **Sidecar `info.json` progress** (Mango) — rejected: not queryable, write-contention, lost on rescan.
- **Single shared progress** (LANraragi) / **single-user** (KamiYomu) — rejected: per-user from day one; retrofitting is painful.
- **Per-device progress rows** — rejected: one row per `(user, book)` + LWW is enough for self-hosted; device is metadata.
- **Snapshotting `page_count` onto the progress row** (KamiYomu `TotalPages`) — rejected: use canonical `book.page_count` + cap, one source of truth.
