# 10 — Tagging, content rating & taxonomy

**Status:** Implemented.

## What this is

A curated, id-based tag vocabulary plus a per-series content rating and
publication demographic — modeled on MangaDex's own taxonomy, shipped as
default fixtures, and manageable from Settings → Content.

## Schema (as built)

One unified table, not the separate `tag`/`tag_group`/`content_rating` tables
originally sketched — `backend/src/taxonomy/models.py`:

```python
class Tag(Base, TimestampMixin):
    id: str        # stable slug, primary key — no auto-gen
    name: str       # display label — independently renamable, see ADR 21
    group: str      # genre | theme | format | content | content_rating | demographic
    enabled: bool
    system: bool    # True for content_rating/demographic rows: id/group locked, undeletable
```

`series_tag(series_id, tag_id)` is the m2m join for the four free groups
(`genre`, `theme`, `format`, `content`). `content_rating` and `demographic`
are **fixed enum groups**: `system=True` rows whose `id` is stored directly on
`Series.content_rating` / `Series.demographic` (plain indexed `String`
columns, not a foreign key — referential integrity is enforced in application
code, not the schema).

**Why one table, id-based:** renaming a tag is a single `UPDATE tag.name`
(assignments reference the id, untouched) instead of rewriting every work's
tag string, and filtering is an indexed join instead of `LIKE`/substring
scans. `Tag.id` is the stable sync key (what MangaDex tag matching,
`series_tag`, and `Series.content_rating` reference); `Tag.name` is the
display label — the two are independent, so renaming a tag from Settings
never touches anything that references it by id.

## Content rating

`content_rating` is a fixed group with **five** system rows
(`backend/src/taxonomy/seed.py`): `safe`, `suggestive`, `erotica` are shared
across every kind and match MangaDex's own values verbatim (`safe · suggestive
· erotica · pornographic`, confirmed against MangaDex's OpenAPI spec). The top
tier forks by kind, since only manga/comic actually sync with MangaDex:

- **manga/comic** (MangaDex-synced): `pornographic` — MangaDex's own raw
  `contentRating` value, passed straight through unrenamed.
- **gallery** (never MangaDex-synced — there's no MangaDex title to borrow a
  word from): `explicit`, a lychee-only top tier.

Nothing enforces kind-appropriateness at the schema/validation layer — same
posture as `demographic` below, which is inapplicable-but-not-rejected on the
wrong kind. The seeded default and every first-party caller (the manual-edit
form, dev/mock fixtures) pick the kind-appropriate value.

## Demographic

`demographic` is a fixed group with four system rows: `shonen`, `shojo`,
`seinen`, `josei` (`Series.demographic` defaults to the non-tag sentinel
`"none"` rather than a fifth row). Manga/comic only — `catalog.service`
warns and skips it on a gallery series rather than rejecting the write.

## Filtering performance

Built for thousands–tens of thousands of series in SQLite:
- `series_tag` primary key `(series_id, tag_id)` plus an extra index
  `(tag_id, series_id)` for the "series having tag X" direction —
  index-only scans both ways.
- `series(content_rating)`, `series(demographic)`, and the sort keys are
  indexed directly (no join needed to filter or sort by rating/demographic).
- ALL-of-tags filtering: `tag_id IN (...) GROUP BY series_id HAVING
  COUNT(*) = n`. ANY-of: `tag_id IN (...)` + `DISTINCT`. EXCLUDE: `NOT IN
  (subquery)`. Text search (FTS5 trigram, [17](17-search-fts.md)) yields a
  series-id set that's intersected with the tag-filtered set.
- Per-tag usage counts (`Action (1,203)` in Settings → Content) are computed
  live via `GROUP BY` over `series_tag` / the `Series` rating+demographic
  columns (`taxonomy/service.py`) — not a denormalized counter column.

## Settings management

Settings → Content is CRUD over the `Tag` table (`taxonomy/service.py`,
`/api/taxonomy`): create/rename/reorder/enable-disable for the four free
groups; `content_rating`/`demographic` rows are `system=True` — undeletable,
`id`/`group` locked, but `name` renames exactly like any other tag (see
[21](21-tag-aliases.md)). Default fixtures can be disabled but not
hard-deleted; user-created tags can be deleted (cascades `series_tag`).
`POST /api/taxonomy/refresh` re-pulls MangaDex's tag vocabulary
(`GET /manga/tag`) and adds anything missing — idempotent, never overwrites
user edits.

## Not built

- Contextual facet counts (counts *within* the current filter, as opposed to
  global per-tag counts) — global counts only today.
- Localized tag names (MangaDex tags are localized; lychee stores one `name`
  per tag regardless of language).
- Enforcing kind-appropriate content rating at the schema/validation layer
  (see above) — not guarded today, same as `demographic`.
