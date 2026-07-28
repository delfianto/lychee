# 21 — Tag aliases: synonym resolution + a renamable display label

**Status:** ✅ Accepted — implemented.

## Context

Full design + rationale lives in [`../09-tag-aliases.md`](../09-tag-aliases.md)
(promoted here per its own "Promotion path" section); read it for the complete
walkthrough. This ADR records the decision as built.

Builds on [10](10-tagging-content-rating.md) (the unified `Tag` table: one
table, a `group` column spanning `genre|theme|content|format|content_rating|
demographic`), the `reconcile_tags` matching path it introduced
(`backend/src/catalog/metadata.py`), and [20](20-lychee-info-metadata.md)
(`lychee.info`, whose `tags:` block reconciles free text through that same
function).

Two distinct gaps prompted this:

1. **Free-vocabulary tag groups silently duplicate under a synonym** —
   `reconcile_tags()` matched by slug or exact name only, so an agent-authored
   `lychee.info` (or a differently-worded provider tag) writing `"Yaoi"` or
   `"Yuri"` minted a duplicate tag next to the already-seeded `"Boys' Love"` /
   `"Girls' Love"`.
2. **MangaDex's `content_rating` passthrough was unrenamed** — MangaDex's API
   exposes `safe · suggestive · erotica · pornographic` (confirmed against
   MangaDex's own OpenAPI spec); lychee's taxonomy seeds `safe · suggestive ·
   erotica · mature`. `decisions/10` already documented the intended
   `pornographic`→`mature` rename, but no code performed it — a
   `"pornographic"`-rated MangaDex title wrote that literal string straight to
   `Series.content_rating`, a value absent from the seeded taxonomy and every
   frontend rating map.

A third, initially-conflated ask — "show more familiar manga-esque terms
(hentai, yuri) while still syncing cleanly with MangaDex" — turned out to be a
**separate, smaller** problem once `Tag.id` (the sync key) and `Tag.name` (the
display label) were recognized as already-independent fields. See "Decision"
below.

## Schema (v1, as built)

`backend/src/taxonomy/models.py`:

```python
class TagAlias(Base, TimestampMixin):
    """An alternate name (slang, abbreviation, a provider's own naming) that
    resolves to a canonical Tag. Mirrors Tag's own id=slug / name=display split.
    """
    __tablename__ = "tag_alias"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # slug of the alias itself
    name: Mapped[str] = mapped_column(String(128), nullable=False)  # display form, e.g. "Hentai"
    tag_id: Mapped[str] = mapped_column(
        ForeignKey("tag.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tag: Mapped["Tag"] = relationship(back_populates="aliases")
```

`Tag.aliases` is the reverse `relationship(..., cascade="all, delete-orphan")`.
Aliases are globally unique by slug (not scoped per group) and seeded
idempotently (`taxonomy/seed.py`, same insert-if-missing pattern as tags
themselves):

```python
_ALIASES = [
    ("Ecchi", "suggestive"),
    ("Hentai", "mature"),
    ("Pornographic", "mature"),   # MangaDex's own raw contentRating value
    ("NSFW", "mature"),
    ("Yaoi", "boys-love"),
    ("BL", "boys-love"),
    ("Yuri", "girls-love"),
    ("GL", "girls-love"),
]
```

## Decision

- **`TagAlias` is a pure ingestion/sync-key resolution mechanism, never a
  display mechanism.** `reconcile_tags()` (`catalog/metadata.py`) gained one
  more lookup tier — slug, then name, then alias — checked before the
  create-new-tag fallback. This reaches every current caller (MangaDex tag
  sync, the local importer, and `lychee.info`'s `tags:` block) with one
  change, no `lychee.info` schema edit needed since `tags:` was already
  free-text.
- **A new `resolve_tag_id(session, raw, group)` helper** covers the closed
  `content_rating`/`demographic` enums, which aren't m2m assignments. Unlike
  `reconcile_tags`, an unresolved value **must not** fall back to creating a
  new row — the closed enums have no "just make a new one" escape hatch.
  Wiring this into `catalog/metadata.py`'s content-rating/demographic
  assignment (replacing the old bare passthrough) closes the MangaDex
  `pornographic` gap: it resolves via the seeded alias to `mature`. An
  unresolvable value now logs a structured warning and leaves the field
  untouched, rather than writing garbage — the same warn-and-skip convention
  `lychee.info` uses for a bad field (ADR 20).
- **Resolution happens only at the write boundary, never at read/render
  time.** Three input boundaries in the code (MangaDex provider apply, local
  import, `lychee.info` apply) call the resolver before anything touches
  `Series`; `SeriesOut`, the OpenAPI contract, and every frontend display
  component need zero alias-handling logic as a result — they only ever see
  canonical values. An alias's own text is never persisted against a series
  and never shown series-facing; it's visible only as a secondary annotation
  in the Settings → Content taxonomy admin table.
- **The "familiar terms" ask is not an aliasing problem — it's a display-label
  editability problem.** `Tag.id` (sync key: what MangaDex matching,
  `series_tag`, and `Series.content_rating` reference) and `Tag.name`
  (display label) were already independent fields. For genre/theme/format/
  content tags this needed **zero code changes** — `update_taxonomy()`
  already let non-system tags rename freely, and `SeriesOut.tags` already
  renders live `{id, name}` pairs. For `content_rating`/`demographic` (both
  `system=True`), two small fixes were needed instead:
  1. `update_taxonomy()`'s system-row lock now covers only `id`/`group`/
     deletability — `name` can be renamed on a system row exactly like any
     other tag (`delete_taxonomy` still refuses to delete it).
  2. The frontend no longer hardcodes content-rating/demographic labels.
     `frontend/src/lib/ratingLabels.ts` fetches live names from
     `/api/taxonomy` once per app session (`AppShell.vue`'s `onMounted`,
     alongside `connectTaskStream`), falling back to static defaults until
     loaded; every badge/dropdown/filter chip that used to read
     `contentRatingLabel[x]` (a static map in `lib/display.ts`) now calls
     `ratingLabel(x)`/`demographicLabel(x)`. The color-class mapping
     (`contentRatingClass`) stays keyed by the stable id — only the text
     needed to become dynamic.
  3. `taxonomy/seed.py`'s demographic names were updated to their macron forms
     (`"Shōnen"`, `"Shōjo"`) to match what the frontend's now-removed
     hardcoded map used to show by default — a pure data change, not a schema
     change, so the default first-boot experience doesn't regress once the
     label became DB-driven.
- **Settings surface:** `TaxonomyItemOut.aliases: list[AliasOut]` (each
  `{id, name, tagId}`, not just names — the frontend needs the id to delete
  one) plus `POST/DELETE /api/taxonomy/{tag_id}/aliases[/{alias_id}]`. An
  alias whose slug collides with an existing `Tag.id` is rejected (409); one
  pointing at a *different* tag is rejected (409); re-adding the same
  alias→tag pair is a no-op, not an error. The Settings → Content panel
  (`ContentPanel.vue`) also gained inline rename (click a name to edit — the
  UI affordance that made renaming reachable at all, since none existed
  before this change even for non-system tags) and alias chips with add/
  remove.
- **Unified the two duplicate slugifiers.** `catalog/metadata.py`'s `_slug()`
  and `taxonomy/service.py`'s `_slugify()` were byte-identical reimplementations;
  both now import `slugify()` from a new `taxonomy/slug.py`.
- **Migration:** squashed into the repo's single initial-schema migration
  (still local/pre-production — same practice as the prior squash), rather
  than added as an incremental revision. `alembic check` reports no drift.

## Consequences

- Splitting "sync key" from "display label" shrank this from one feature into
  two much smaller ones — most of the "familiar terms" ask needed no backend
  change at all.
- `reconcile_tags` stops creating duplicate tags for known synonyms across
  every current caller with one shared lookup.
- Closes the `decisions/10`-documented-but-never-implemented `pornographic`→
  `mature` rename using the general alias mechanism, not a special-cased dict.
- The taxonomy gains one more relation (`Tag` ← `TagAlias`), but its core
  "one table, `group` column" shape (ADR 10) is untouched.
- The frontend's content-rating/demographic display text now depends on a
  network fetch (with a synchronous static fallback for first paint) instead
  of being purely static — a small new moving part, scoped to exactly the two
  system-enum groups that needed it.

## Deferred / explicitly not built

Same list as `09-tag-aliases.md`'s: localized tag names (stays ADR 10's own
tracked follow-up), fuzzy/typo-tolerant alias matching, alias-aware full-text
search (the FTS5 index doesn't cover tags at all today, aliased or not), and
an alias-aware typeahead in the browse-view tag filter (which today has no
search box for any tag, aliased or not).

## Alternatives considered

See `09-tag-aliases.md` for the full list (a separate `lychee_tag` field, a
hardcoded MangaDex-only translation dict, per-group alias scoping, storing
aliases as a JSON column on `Tag`) and why each was rejected.
