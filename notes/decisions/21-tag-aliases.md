# 21 — Tag aliases: synonym resolution + a renamable display label

**Status:** Implemented.

## What this is

A way to say "this free text means that canonical `Tag` row" — resolving
colloquial slang, abbreviations, and a provider's own wording onto an
existing tag instead of minting a duplicate. It also makes `content_rating`/
`demographic`'s display label freely renamable, matching every other tag
group.

## The sync key vs. the display label

`Tag.id` (`backend/src/taxonomy/models.py`) is the *sync key* — the stable
slug that MangaDex tag matching, `series_tag`, and `Series.content_rating`
all reference, and must never change once assigned. `Tag.name` is the
*display label* — purely cosmetic, already structurally independent of `id`.

Genre/theme/format/content tags could always be renamed freely
(`update_taxonomy()` only locks `id`/`group`/deletability for `system=True`
rows) — `SeriesOut.tags` returns live `{id, name}` pairs, not a cached copy,
so a rename in Settings shows up everywhere immediately with MangaDex sync
still matching by the untouched `id`. `content_rating`/`demographic` rows are
`system=True`, so they needed the same rename capability extended to them —
see "Settings surface" below.

`TagAlias` is a separate, narrower mechanism: **ingestion/sync-key
resolution only, never a display mechanism.** It resolves incoming free text
onto the *correct* `Tag.id`; what's shown is always whatever `Tag.name`
currently says.

## Schema

`backend/src/taxonomy/models.py`:

```python
class TagAlias(Base, TimestampMixin):
    id: str        # slug of the alias itself, primary key
    name: str       # display form, e.g. "Hentai" — shown only in the Settings admin table
    tag_id: str      # FK -> tag.id, ondelete=CASCADE
```

Aliases are globally unique by slug (not scoped per group), seeded
idempotently alongside tags (`taxonomy/seed.py`, insert-if-missing):

```python
_ALIASES = [
    ("Ecchi", "suggestive"),
    ("Hentai", "pornographic"),
    ("NSFW", "pornographic"),
    ("Yaoi", "boys-love"),
    ("BL", "boys-love"),
    ("Yuri", "girls-love"),
    ("GL", "girls-love"),
]
```

MangaDex's own raw `content_rating` values need no alias — they already
match a `Tag.id` directly (`safe`/`suggestive`/`erotica`/`pornographic`, see
[10](10-tagging-content-rating.md)).

## Two resolution paths, two failure modes

- **`reconcile_tags()`** (`catalog/metadata.py`) — the free-vocabulary path
  (genre/theme/format/content). Matches incoming `(name, group)` by slug,
  then name, then alias; if nothing matches, **creates a new tag**. Used by
  MangaDex tag sync, the local importer, and `lychee.info`'s `tags:` block.
- **`resolve_tag_id(session, raw, group)`** (`catalog/metadata.py`) — the
  closed-enum path (`content_rating`/`demographic`). Same slug → name →
  alias lookup, but an unresolved value **must never** fall back to creating
  a row — there's no "just make a new one" escape hatch for a closed enum.
  The caller (`apply_metadata`) logs a structured warning and leaves the
  field untouched rather than writing an unknown value.

Both resolve at the **write boundary only** — MangaDex provider apply, local
import, and `lychee.info` apply all call the resolver before touching
`Series`. Nothing downstream (`SeriesOut`, the OpenAPI contract, every
frontend display component) needs any alias-handling logic; they only ever
see canonical values. An alias's own text is never persisted against a
series and never shown series-facing — it's visible only as a secondary
annotation in the Settings → Content taxonomy admin table.

## Settings surface

`TaxonomyItemOut.aliases: list[AliasOut]` (`{id, name, tagId}`) plus
`POST`/`DELETE /api/taxonomy/{tag_id}/aliases[/{alias_id}]`. An alias whose
slug collides with an existing `Tag.id` is rejected (409); one pointing at a
*different* tag is rejected (409); re-adding the same alias→tag pair is a
no-op. `ContentPanel.vue` has inline rename (click a name to edit) and alias
chips with add/remove, for every group including the two system ones.

## Not built / explicitly out of scope

- **Localization.** An alias is a same-language synonym, not a translation —
  a deferred `tag_name(tag_id, lang, name)` table (ADR 10) is the right shape
  for actual translated tag names, kept conceptually separate even though
  some current aliases (yaoi/BL) read like both.
- **Fuzzy/typo-tolerant matching.** Exact slug/normalized-name lookup only —
  edit-distance matching risks false-positive merges of genuinely different
  tags, worse than the occasional duplicate this mechanism reduces.
- **No change to `lychee.info`'s schema strictness.** `content_rating`/
  `demographic` stay `Literal[...]`-validated at parse time
  (`ingest/lychee_info.py`) with zero DB access — an LLM agent is expected to
  write the canonical word directly; aliases exist for *ingesting* other
  sources' free text, not for loosening what an agent is asked to author.
- Alias-aware full-text search (FTS5 doesn't index tags at all, aliased or
  not) and an alias-aware typeahead in the browse-view tag filter (which has
  no search box for any tag today).
