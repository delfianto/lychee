# 16 — Read-status tracker sync

**Status:** ✅ Accepted

## Context

With the client being webapp-only ([15](15-api-surface.md)), device/OPDS sync is out — but users want their reading status pushed to external **trackers**: **AniList, MyAnimeList, Kitsu, MangaUpdates (Baka-Updates), MangaDex**. This is **outbound list tracking** (like AniList/MAL integration in Mihon), distinct from metadata *fetching* ([13](13-metadata-providers.md), inbound) — but it reuses that ADR's **`external_link`** matching and OAuth patterns. Reading progress ([11](11-reading-progress.md)) is the source of truth to push; work runs on the task queue ([08](08-task-runner.md)); the tracked unit is the **Series** ([10](10-tagging-content-rating.md)).

## Decision

### A local "list status" per user per series (the thing we push)
Trackers model a **library entry** (a shelf state) that's richer than raw page progress: status + score + dates. lychee gains its own version — useful as UI shelves independent of any tracker:

```
series_list_status(
  user_id → user, series_id → series,
  status  TEXT,          -- reading | completed | paused | dropped | planning | rereading
  score   REAL NULL,     -- normalized 0..10 internally
  progress_chapters INT, -- derived from completed books' number_sort (06/11)
  started_at, finished_at, updated_at,
  PRIMARY KEY (user_id, series_id))
```

- **Auto-advanced by reading progress** ([11](11-reading-progress.md)): first book read → `reading` + `started_at`; series fully read → `completed` + `finished_at`; `progress_chapters` tracks the max completed chapter number.
- **User-overridable** for the states progress can't infer (`paused` / `dropped` / `planning`) and `score`.

### Tracker abstraction (parallel to the metadata provider)
```
class Tracker(Protocol):
    id: str                                  # "anilist"
    oauth: OAuth2Config
    def search(q) -> list[Match]             # find the tracker's entry for a series
    def get_entry(external_id) -> Entry      # current remote status/progress/score
    def push(external_id, status: ListStatus) -> None   # update remote
```
A registry, like [13](13-metadata-providers.md)'s providers. Several services are **both** metadata provider *and* tracker (MangaDex, AniList, MangaUpdates) — they share the same `external_link` join and OAuth account.

### Linking & accounts
- A series links to a tracker entry via **`external_link`** ([13](13-metadata-providers.md), `provider = "anilist" | "myanimelist" | …`) — the same confidence-matched, **manual-confirm** flow; a series may link to **multiple trackers** at once.
- Per-user OAuth tokens:
  ```
  tracker_account(user_id, tracker, access_token, refresh_token, expires_at,
                  tracker_username, PRIMARY KEY(user_id, tracker))
  ```
  Tokens **encrypted at rest**. Per [12](12-auth-users.md) these attach to the single default user for now; the schema is already user-scoped.

### Sync trigger & policy (push-first)
- **Debounced push** via a `tracker_sync` task ([08](08-task-runner.md)) on: book **completion**, **mark series read/unread**, a **status/score change**, or explicit **"sync now"**. Never push per page-turn (binge a volume → one push).
- **Direction:** v1 is **outbound push** (lychee → tracker). **Inbound pull** (import an existing tracker list to seed `series_list_status`, and reconcile) is an opt-in follow-up; conflicts resolve **last-write-wins by `updated_at`** (or push-wins, configurable).
- **Status mapping** lychee → tracker enum is per-tracker (they differ slightly); score is normalized 0..10 internally and scaled per tracker (10 / 100 / stars).

### Tracker capability matrix (verify per-tracker at implementation)
| Tracker | API | Auth | Progress unit | Notes |
|---|---|---|---|---|
| **AniList** | GraphQL | OAuth2 | chapters + volumes + score + status | `SaveMediaListEntry`; the primary manga tracker |
| **MyAnimeList** | REST v2 | OAuth2 (PKCE) | chapters + volumes + score + status | `PATCH /manga/{id}/my_list_status` |
| **Kitsu** | JSON:API | OAuth2 | progress + status + rating | library entries |
| **MangaUpdates** | REST v1 | session token | reading list + chapter | Baka-Updates; more list-oriented, coarser progress |
| **MangaDex** | REST | OAuth2 (personal client) | status + chapter read-markers | also a metadata provider ([13](13-metadata-providers.md)) |

Recommended rollout: **AniList + MyAnimeList + MangaDex** first (most-used; AniList primary), then Kitsu + MangaUpdates.

## Consequences

- Reading in lychee auto-syncs to the user's trackers, across multiple trackers per series.
- Reuses [13](13-metadata-providers.md)'s `external_link` + OAuth infra; `series_list_status` doubles as native "reading / completed / plan-to-read" shelves — good UX on its own.
- Push-first keeps v1 simple; pull/2-way is additive later.

## Follow-ups

- **Per-tracker research notes** (like [../mangadex-api/README.md]) when implementing each — exact endpoints, OAuth flow, status enums, score scales.
- **Inbound pull / 2-way** sync + conflict policy.
- **Score-scale** normalization table; **status-enum** mapping per tracker.
- Encrypted token storage ties into the eventual secrets/auth work ([12](12-auth-users.md)).

## Alternatives considered

- **Device / OPDS sync** — out of scope ([15](15-api-surface.md)).
- **Two-way sync by default** — rejected for v1 (push-first is simpler; pull is opt-in).
- **Tracking at book/chapter level** — rejected: trackers track a **title**; we push series-level chapter counts derived from book progress.
