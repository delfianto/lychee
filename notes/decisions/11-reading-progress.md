# 11 — Reading progress & sync

**Status:** Implemented — single-user, chapter-keyed. Outbound tracker sync
shipped; device/reader-ecosystem sync stays out of scope.

## Storage

```python
# progress/models.py
reading_progress(
  id,
  chapter_id → chapter UNIQUE,   # one row per Chapter, not per (user, book)
  series_id → series,             # denormalized, for rollup queries
  current_page: int,
  completed: bool,
)
```

**No `user_id` column exists anywhere in the schema** — there's no `User`
table at all ([12](12-auth-users.md)); every field that would have been
per-user instead lives as a plain column with an implicit single reader.
`updated_at` (from the base model) doubles as the last-read timestamp; there
are no separate `started_at`/`completed_at` fields, no `device_id`/
`device_name`, no `locator` for reflowable EPUB (there's no EPUB support at
all — `content_kind` is `cbz|zip|image_dir|avif_dir` only).

Progress is per **Chapter** (the logical reading unit), not per Book (the
physical container) — matching the split in [05](05-domain-model.md).

## No rollup table

There's no `series_read_progress` table. `unreadCount`, `lastReadChapter`,
and "continue reading" are computed live via correlated SQL subqueries
(`backend/src/catalog/repository.py` — `_aggregates`, `dashboard_counts`,
`continue_reading`, `recently_added`), not a denormalized row kept in sync
on write.

## Update API

`PUT /api/chapters/{chapter_id}/progress` (`backend/src/progress/router.py`
→ `progress/service.py:update_progress`), body `{page, completed?}`.
Completion is **inferred** (`page >= chapter.page_count`) when `completed`
is omitted from the request, or set explicitly when the caller passes it.
On completion, `enqueue_push(session, chapter.series_id)`
(`trackers/sync.py`) fires outbound tracker sync.

## Move/restore preserves progress

Not part of this table directly, but the mechanism that protects it: on
soft-delete during a scan, a Book's Chapters' progress is snapshotted
(`Book.restore_progress_json`, [07](07-scan-pipeline.md)) and re-applied on
restore, matched back by chapter `number`.

## Home sections

`GET /api/dashboard` returns `continue_reading`, `recently_added`, and
stats; `GET /api/updates`/`/api/updates/unread` cover the recent-updates
feed. There's no separately-named "on deck" concept — it's folded into the
unread-updates feed rather than being its own endpoint.

## External sync: tracker push shipped, device/reader sync stays out of scope

The client is the webapp (and `mcp/`) only ([15](15-api-surface.md)) — no
Tachiyomi/Mihon, KOReader, Kobo, or OPDS Position Sync, and none of those
are planned. What **is** shipped: **outbound read-status tracker sync** to
AniList, MyAnimeList, and MangaUpdates (`backend/src/trackers/`, a
`Tracker` protocol + registry — see [16](16-tracker-sync.md) for the
per-tracker detail), fired on chapter completion, gated by `sync_on_read`.
MangaDex gets its own **two-way** account sync
(`providers/mangadex_account.py`) — inbound pull (follows, status, custom
lists, ratings, read markers, MangaDex as source of truth) as well as
outbound push — built separately from the generic `Tracker` protocol.

## Why chapter-keyed, single-user, no rollup table

Single-user was the explicit v1 scope ([12](12-auth-users.md)); the
consequence worth knowing is that this was **not** built as "one seeded
default user with `user_id` wired through," so multi-user later needs a
real schema migration (adding `user_id` to `reading_progress` and moving
per-user `Series` fields like `favorite`/`library_status` off `Series`) —
not a config flip. A live-computed rollup avoids a denormalized counter that
could drift from the source rows; at this scale the correlated subqueries
are fast enough that the extra table wasn't worth the write-path complexity.
