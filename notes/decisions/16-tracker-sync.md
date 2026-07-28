# 16 — Read-status tracker sync

**Status:** Implemented — AniList, MyAnimeList, MangaUpdates via a shared
`Tracker` protocol, outbound-push-only. MangaDex is two-way but wired
separately, outside that protocol. Kitsu was never built.

## List status: plain columns, not a separate table

No `series_list_status` table. The "shelf state" lives directly on
`Series`: `library_status` (`none | reading | on_hold | dropped |
plan_to_read | completed | re_reading`) and `user_rating` (float, 1-10).
There's no `score`/`started_at`/`finished_at`/`progress_chapters` column
anywhere — chapter counts pushed to a tracker are computed at push time from
`ReadingProgress` + `Series.total_chapters`, not stored.

## Tracker abstraction

`backend/src/trackers/base.py`'s `Tracker` Protocol: `id`,
`external_id_key`, `auth_kind` (`"oauth"|"credentials"`), `uses_pkce`,
`authorize_url`/`exchange_code`/`login`/`account_name`/`push`. A registry
(`register_tracker`/`get_tracker`). Three real implementations:

| Tracker | API | Auth | Notes |
|---|---|---|---|
| **AniList** | GraphQL | OAuth2 | `SaveMediaListEntry` mutation |
| **MyAnimeList** | REST v2 | OAuth2 + PKCE | `PATCH /manga/{id}/my_list_status` |
| **MangaUpdates** | REST v1 | session-token login | list-update via `list_id` 0-4 |

**Kitsu was never implemented** — not in the seeded tracker roster, no code
anywhere references it. **NovelUpdates exists as a seeded-but-unsupported
row** (`auth_kind: "unsupported"` — no public API, connecting is rejected)
— present in the roster but not functional, a case the original design
didn't anticipate either way.

**MangaDex is not a `Tracker` at all.** It's a separate module,
`backend/src/providers/mangadex_account.py`, with its own **two-way** sync
(`sync_account` pulls follows/status/custom-lists/ratings/read-markers with
MangaDex as source of truth; `push_series` pushes status/read-markers/
rating outbound) — it lives in the `provider` table, not the `tracker`
table, and shares no code path with the three `Tracker`-protocol trackers.

## Linking & accounts

Linking uses `Series.external_ids_json` (a JSON dict keyed `al`/`mal`/`mu`/
`kt`/`nu`/…, populated from MangaDex's own `links` object on match — note
`kt`/`nu` keys get harvested even though no Kitsu tracker consumes them and
NovelUpdates can't connect). No generic `external_link` table.

Per-tracker credentials: `Tracker` (`backend/src/integrations/models.py`) —
`id` (slug PK), `connected`, `sync_on_read`, `account_name`, OAuth
client/token fields (`client_id`, `client_secret_enc`, `access_token_enc`,
`refresh_token_enc`, `pkce_verifier`, `state`, `token_expires_at`). **No
`user_id` column** — a flat single-row-per-tracker table, consistent with
true single-user, not a forward-compatible per-user schema.

## Sync trigger & direction

Debounced push via a `tracker` task on chapter completion or a status/score
change — never per page-turn (`trackers/sync.py:enqueue_push`, called from
`progress/service.py:update_progress` on completion). For the three
`Tracker`-protocol trackers, direction is **outbound push only** — no
inbound pull, no conflict resolution needed since lychee is always the
source of truth pushing out. MangaDex is the one exception, with real
inbound pull already shipped (`notes/plan.md` PART I).

## Not built

- Kitsu (never started).
- Inbound pull / two-way sync for AniList/MyAnimeList/MangaUpdates.
- Score-scale normalization beyond what each tracker's own push call does
  inline.
