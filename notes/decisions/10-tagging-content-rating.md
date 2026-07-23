# 10 — Tagging, content rating & taxonomy (MangaDex-modeled)

**Status:** ✅ Accepted

## Context

We want to **replicate MangaDex's content-rating + tag taxonomy**: a curated, grouped tag vocabulary and a per-work content rating — both shipped as **default fixtures** and **manageable from a settings page**. This refines the loose namespaced-tag sketch in [05](05-domain-model.md): the curated taxonomy is a **managed, id-based** system, not free-form strings. Tags/rating apply at the **Series** level (MangaDex tags a *title*, not a chapter); books are filtered through their series. The hard requirement is **good filter/browse performance at thousands–tens-of-thousands of series/books** in SQLite.

MangaDex's model we mirror:
- **Content rating** (one per work): `safe · suggestive · erotica · pornographic`.
- **Tag groups**: `content · format · genre · theme`; each tag belongs to one group.
- **Publication demographic** (separate field, not a tag): `shounen · shoujo · seinen · josei · none`.

## Decision

### Managed, id-based taxonomy (not string tags)

```
tag_group(id, key UNIQUE, name, sort_order)
     -- seed: content, format, genre, theme  (editable/extensible)

tag(id, group_id → tag_group, key UNIQUE, name, description,
    is_default,        -- true = shipped fixture
    enabled,           -- soft-disable instead of delete
    sort_order,
    series_count)      -- denormalized global usage count (see perf)

series_tag(series_id → series, tag_id → tag,
           PRIMARY KEY (series_id, tag_id))

content_rating(id, key UNIQUE, name, level INT, is_default, enabled)
     -- seed: safe=0, suggestive=1, erotica=2, pornographic=3  (level = explicitness)

demographic(id, key UNIQUE, name, is_default)
     -- seed: shounen, shoujo, seinen, josei, none

-- on series:
series.content_rating_id  → content_rating   (nullable)
series.content_rating_level INT               -- DENORMALIZED copy of the rating's level (hot filter)
series.demographic_id     → demographic       (nullable)
```

**Why id-based, not LANraragi-style `namespace:value` strings:** renaming a tag is a single `UPDATE tag.name` (assignments reference the id, untouched) instead of rewriting every work's tag string; filtering is integer-index joins instead of `LIKE`/`KEYS` scans; and a curated vocabulary is what "manage from a settings page" *means*. This supersedes the free-form tag idea in 05 for curated metadata. (Imported/scanlation tags from `ComicInfo <Tags>` map into a `custom` tag group — see follow-ups.)

### Fixtures & settings management
- Ship the **full MangaDex vocabulary** as fixtures (4 groups, ~70 tags, 4 ratings, demographics), seeded **idempotently by stable `key`** in a data step: insert-if-missing, **never overwrite** user-edited rows (`is_default` marks shipped rows; new releases can add missing defaults without clobbering edits). **Seed source = MangaDex `GET /manga/tag`** (use its stable tag ids as our `tag.key` for 1:1 provider mapping) — see [../mangadex-api/README.md](../mangadex-api/README.md).
- **Settings page** = CRUD over `tag` / `tag_group` / `content_rating`: create custom tags, rename (free), reorder, **enable/disable**. Default fixtures can be disabled but not hard-deleted (they may be referenced / re-seeded); user-created tags can be deleted (cascade `series_tag`). Content ratings are editable including their `level` ordering.

### Content rating
One rating per series via `content_rating_id`, plus a **denormalized `content_rating_level`** on `series` (kept in sync on assignment) so "how explicit" filtering is a single indexed integer comparison — no join on the hot path. Per-user filtering (a user's allowed ratings / max level, MangaDex's content filter) lives in user settings → the auth ADR; this schema makes it a `content_rating_level <= :cap` predicate.

## Performance design (thousands of books)

Scale is small for SQLite — 10k series × ~8 tags ≈ 80k junction rows; even 100k × 15 ≈ 1.5M — trivial **with the right indexes and set-based filters**.

**Indexes (the whole game):**
- `series_tag` **PK `(series_id, tag_id)`** — "tags of a series" + uniqueness.
- **extra index `(tag_id, series_id)`** — "series having tag X", the filter direction; enables **index-only** scans.
- `series(content_rating_level)`, `series(demographic_id)`, `series(library_id)`, and sort keys (`sort_name`, `created_at`).

**Filtering patterns (all index-driven):**
- **ALL-of tags** (Action AND Romance AND School Life):
  ```sql
  SELECT series_id FROM series_tag WHERE tag_id IN (:t1,:t2,:t3)
  GROUP BY series_id HAVING COUNT(*) = 3
  ```
  (single index scan) — or `INTERSECT` of one index-only scan per tag.
- **ANY-of tags**: `tag_id IN (...)` + `DISTINCT`.
- **EXCLUDE**: `series_id NOT IN (SELECT series_id FROM series_tag WHERE tag_id IN (:x…))`.
- **Rating / demographic**: direct indexed predicates (`content_rating_level <= :cap`, `demographic_id = :d`).
- **Text search**: FTS5 ([04](04-database-sqlite.md)) yields a series-id set; **intersect** with the tag-filtered set (apply the most selective side first).
- Compose these in a **typed filter builder** (Komga's `SearchCondition` idea) → one query; SQLite's planner uses the two junction indexes + series column indexes.

**Counts & facets:**
- **Global per-tag counts** (`Action (1,203)` in the tag list / settings page): maintained incrementally as **`tag.series_count`**, updated by triggers on `series_tag` insert/delete (or recomputed after a scan batch). Cheap, always accurate. (This is LANraragi's `LRR_STATS` idea, done relationally.)
- **Contextual facet counts** (counts *within* the current filter) are the expensive part — **deferred**: show global counts in v1; compute contextual counts lazily/capped or cache later if needed.

**Pagination:** keyset/seek on the sort key for deep pages (OFFSET is fine at thousands). Run `ANALYZE` / `PRAGMA optimize` so the planner reliably picks the junction indexes.

## Consequences

- Curated, grouped, MangaDex-faithful taxonomy that admins can manage; **renames and reorders are free** (id-based).
- Faceted filtering (tags × rating × demographic × text × read-state) stays millisecond-fast at tens of thousands of series via two junction indexes + set-based queries.
- Denormalized `content_rating_level` and `tag.series_count` keep the two hottest reads index-only / O(1).
- Content filtering is ready to become per-user (`level <= cap`) in the auth ADR.

## Follow-ups

- **Custom / imported tags:** map `ComicInfo <Tags>` and scanlation tags into a `custom` tag group (auto-create disabled-by-default or pending-review), so free-form input coexists with the curated vocabulary.
- **Per-user content filter** (allowed ratings / max level) → deferred with auth ([12](12-auth-users.md)); resolves to the single default user in v1, the `content_rating_level <= :cap` predicate is already in place.
- **Contextual facet counts** — add if the filter UI needs them.
- **Localized tag names** — MangaDex tags are localized; a `tag_name(tag_id, lang, name)` table can be added later; single `name` for v1.

## Alternatives considered

- **Free-form `namespace:value` strings** (LANraragi, 05 sketch) — rejected for curated metadata: rename rewrites every row, and filtering needs `LIKE`/scan. Kept only as the `custom`-group ingestion path.
- **Hardcoded enums** for rating/demographic/tags — rejected: the "manage from a settings page" requirement needs editable lookup tables.
- **Tags at book level** — rejected as the default: MangaDex tags a title; series-level matches the source model and keeps the junction small. Books filter via their series.
