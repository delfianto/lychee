# Overview 9 — Tag Aliases: Canonical Synonyms in the Unified Taxonomy

> **Status: implemented.** Formalized as
> [ADR 21](decisions/21-tag-aliases.md) — read that first for what actually
> shipped. One refinement made during implementation: the "familiar terms"
> ask (hentai, yuri) turned out not to need the alias mechanism at all — see
> "Two separate concerns" below, which this doc already anticipated but ADR 21
> records as the as-built decision.

Like [08](08-metadata.md), this isn't cross-project comparison research — it's
lychee's own design. Builds directly on [`decisions/10`](decisions/10-tagging-content-rating.md)
(the unified `Tag` table: one table, a `group` column spanning
`genre|theme|content|format|content_rating|demographic`), the `reconcile_tags`
matching path it introduced (`backend/src/catalog/metadata.py`), and
[`decisions/20`](decisions/20-lychee-info-metadata.md) (`lychee.info`, whose
`tags:` block already reconciles free text through that same function) — read
those first.

## Problem statement

Two distinct gaps prompted this, found while reviewing how MangaDex content
ratings actually flow into lychee:

1. **Free-vocabulary tag groups silently duplicate under a synonym.**
   `reconcile_tags()` (`catalog/metadata.py:107-125`) matches incoming tag
   names by slug or by exact (lowercased) name, and **creates a new `Tag` row**
   for anything that doesn't match. lychee already seeds `"Boys' Love"` /
   `"Girls' Love"` (`taxonomy/seed.py:26,31`) matching MangaDex's own tag
   names — but an agent-authored `lychee.info` (or a differently-worded
   provider tag) writing `"Yaoi"` or `"Yuri"` doesn't match either seeded
   slug/name, so it mints a duplicate tag sitting next to the canonical one
   instead of resolving to it.
2. **MangaDex's `content_rating` passthrough is unrenamed.** MangaDex's own
   API exposes exactly four values — `safe · suggestive · erotica ·
   pornographic` (confirmed directly against MangaDex's published OpenAPI
   spec) — but lychee's internal taxonomy seeds `safe · suggestive · erotica
   · mature` (`taxonomy/seed.py:103-108`). `decisions/10` already documents
   the intended fix ("MangaDex `pornographic` maps to `mature`"), but no code
   performs it: `catalog/metadata.py:46-47`'s provider-apply path is an
   unconditional, unvalidated passthrough of `meta.content_rating`. A series
   matched to a `"pornographic"`-rated MangaDex title gets that literal string
   written to `Series.content_rating` — a value absent from the seeded
   taxonomy, the `_CONTENT_RATINGS` set `catalog/service.py` enforces on
   manual edits, and every frontend `ContentRating`-keyed lookup
   (`frontend/src/lib/display.ts`).

Both gaps are instances of the same missing piece: **a way to say "this free
text means that canonical `Tag` row"** — colloquial slang (hentai, ecchi),
common abbreviations (BL, GL), and a provider's own differently-named value
(pornographic) are all the same shape of problem.

## Two separate concerns: the sync key vs. the display label

It's tempting to reach for a third mechanism here — a separate `lychee_tag`
field for tags that aren't provider-sourced, so lychee-native, "familiar"
naming (hentai, yuri) lives apart from whatever MangaDex calls things. Rejected:
that just recreates the duplication problem this doc exists to solve — two
sources of truth for the same concept, and now a question of which one
MangaDex sync is even allowed to touch. There's no need for it, because the
schema already separates the two things "use more familiar manga-esque terms,
but keep syncing cleanly with MangaDex" actually requires:

- **`Tag.id`** — the stable slug (`girls-love`, `mature`). This is the *sync
  key*: what MangaDex tag matching, `series_tag`, and `Series.content_rating`
  all reference. It must never change once assigned.
- **`Tag.name`** — the *display label* (`"Girls' Love"`, `"Mature"`). Purely
  cosmetic, and already structurally independent of `id`.

Wanting the UI to say "Yuri" instead of "Girls' Love," or "Hentai" instead of
"Mature," while MangaDex sync keeps working, is a request to edit `name`
without touching `id` — a capability that already exists for most of the
taxonomy:

- **Genre/theme/format/content tags — this already works today, no code
  change.** `update_taxonomy()` (`taxonomy/service.py:110-121`) lets you
  rename any non-system tag's `name` freely. `boys-love`/`girls-love` are
  non-system (`taxonomy/seed.py`'s `_rows()` only sets `system=True` for the
  `content_rating`/`demographic` groups). Rename `"Girls' Love"` → `"Yuri"`
  in Settings, and it shows as "Yuri" everywhere immediately — `SeriesOut.tags`
  returns live `{id, name}` pairs from the `Tag` table (`repository.py`'s
  `selectinload(Series.tags)`), not a cached/hardcoded copy. MangaDex sync
  keeps matching by `id` (`girls-love`), completely untouched.
- **`content_rating`/`demographic` tags need two small, targeted fixes** —
  see "Display label editability" below — because these rows are
  `system=True` (name-rename is currently blocked outright), and because,
  independently, the frontend doesn't read their label from the taxonomy at
  all today.

This reframes the rest of this doc: `TagAlias` (below) is solely an
**ingestion/sync-key resolution** mechanism — getting incoming free text
(MangaDex's raw value, an agent's wording) onto the *correct* `Tag.id` —
never a display mechanism. What gets displayed is always whatever `Tag.name`
currently says, and making that freely editable is a much smaller, more
targeted change than a parallel tag system.

## Non-goals

- **Not localization.** `decisions/10`'s own follow-ups already track a
  deferred `tag_name(tag_id, lang, name)` table for genuinely translated tag
  names. An alias is a *synonym* (same language, different word), not a
  *translation* — even though a couple of examples below (yaoi/BL) read like
  both. Keep them conceptually and structurally separate.
- **Not fuzzy or typo-tolerant matching.** Exact slug/normalized-name lookup
  only, mirroring `reconcile_tags`'s existing exact-match behavior. Edit-
  distance matching risks false-positive merges of genuinely different tags,
  which is worse than the occasional duplicate this doc is trying to reduce.
- **Not a change to `lychee.info`'s schema strictness.** `content_rating` /
  `demographic` stay `Literal[...]`-validated at parse time
  (`ingest/lychee_info.py`) with zero DB access — `decisions/20` and `08`
  are explicit that strict-fail validation on a wrong enum value is a
  *feature* for agent-authored files, and an LLM agent is fully capable of
  writing the canonical word (`mature`) directly. Aliases exist for
  *ingesting* other sources' free text (MangaDex's raw value, a human's
  search input), not for loosening what an agent is asked to author.

## Schema (v1 design)

One new table, hanging off the existing `Tag` row it resolves to:

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

plus `Tag.aliases: Mapped[list["TagAlias"]] = relationship(back_populates="tag", cascade="all, delete-orphan")`.

Design choices:

- **`id` is the alias's own slug**, not a nanoid — the same pattern `Tag.id`
  already uses (`taxonomy/models.py:34`: "Id is a stable slug"). Lookup is
  then a plain `session.get(TagAlias, slug)`, no extra unique index needed.
- **Aliases are globally unique across every group**, not scoped per-tag or
  per-category. An alias is unambiguous free text — "yaoi" always means the
  same canonical tag regardless of context — and a flat global lookup is what
  lets both consumers below (`reconcile_tags`, the content-rating resolver)
  share one lookup dict.
- **`ondelete="CASCADE"`** — deleting a user-created tag (system rows can't be
  deleted at all, `taxonomy/service.py:124-131`) cleans up its aliases with
  no extra code.
- **System-row tags can have aliases even though their `name` is read-only.**
  `update_taxonomy()` (`taxonomy/service.py:110-121`) blocks renaming a
  `system=True` row's `name` — that's unaffected; aliases are a separate,
  additive mechanism, and the `content_rating`/`demographic` groups (both
  `system=True`) are exactly where the "hentai"/"pornographic" aliases need
  to attach.

## Resolution & call sites

**`reconcile_tags()`** gains one more lookup tier, checked before the
create-new-tag fallback:

```python
by_alias = {a.id: a.tag for a in session.scalars(select(TagAlias))}
...
tag = by_slug.get(slug) or by_name.get(name.lower()) or by_alias.get(slug)
```

This one change reaches every current caller: MangaDex tag sync
(`metadata.py:65`), the local importer (`ingest/importer.py:91`), and —
without any change to `lychee_info.py`'s schema, since `tags:` is already a
free-text `list[str]` per group — `apply_lychee_info`'s tag block (it calls
the same `reconcile_tags`, per `decisions/20`). An agent writing
`theme: [Yaoi]` resolves to the existing `boys-love` tag instead of minting a
duplicate.

**A new `resolve_tag_id()` helper** covers the scalar-enum case
(`content_rating`/`demographic`), since those aren't m2m assignments but a
single stored string that must stay one of the four canonical values:

```python
def resolve_tag_id(session: Session, raw: str, group: str) -> str | None:
    slug = _slug(raw)
    if session.get(Tag, slug) is not None:
        return slug
    alias = session.get(TagAlias, slug)
    return alias.tag_id if alias else None
```

Wiring this into `catalog/metadata.py`'s content-rating assignment (in place
of today's bare passthrough) closes gap #2 above: seed `"Pornographic"` as an
alias of `mature` (below), and MangaDex's raw `"pornographic"` resolves to
the correct canonical value through the same general mechanism — not a
one-off translation dict living outside the taxonomy.

**Explicitly unchanged:** `lychee_info.py`'s `Literal[...]` fields, the
`_CONTENT_RATINGS` validation set in `catalog/service.py` for manual `PATCH`
edits, and the frontend's `ContentRating` type/badge maps
(`frontend/src/lib/display.ts`) — all three already only ever see canonical
values (the manual-edit path validates against the closed set directly; the
resolver above is what guarantees the *provider* path does too).

## Display label editability: the actual "familiar terms" mechanism

Two small, targeted changes make `Tag.name` fully user-controlled for the
`content_rating`/`demographic` groups too (genre/theme/format/content already
support this today, per "Two separate concerns" above):

1. **Loosen `update_taxonomy()`'s system-row lock to cover only `id`, group,
   and deletability — not `name`.** Today (`taxonomy/service.py:114-116`) it
   refuses to rename *any* `system=True` row's `name` at all. Narrow that
   check to keep protecting what actually needs protecting — the row can't
   be deleted (`delete_taxonomy`, `taxonomy/service.py:124-131`, unchanged),
   `id`/`group` are never editable for any tag, system or not — while letting
   `name` be renamed exactly like a non-system tag already can be.
2. **Make the content-rating badge read the live name, not a hardcoded
   map.** `frontend/src/lib/display.ts:23-35`'s `contentRatingLabel` /
   `contentRatingClass` are static TypeScript objects, completely
   disconnected from `Tag.name` in the database — unlike genre/theme tag
   chips, which already render live API data (`SeriesOut.tags`). Renaming
   the `mature` tag to "Hentai" via Settings would currently have **no
   visible effect anywhere**, because nothing re-reads the taxonomy for that
   label. Closing this means the badge component needs to source its label
   from `/api/taxonomy` (or `SeriesOut` needs to carry the resolved name
   alongside the raw `content_rating` id) instead of the static map. The
   color-class mapping (`badge-error` for the top tier, etc.) can stay keyed
   by the stable `id` — only the *text* needs to become dynamic.

With both in place: an admin renames the `mature` system tag's `name` to
"Hentai" in Settings; MangaDex sync keeps matching and writing
`Series.content_rating = "mature"` exactly as before (via the
`TagAlias`-backed resolver above); every badge in the UI shows "Hentai."
Three independent mechanisms — sync-key resolution, an editable label, and a
live-reading frontend — each doing exactly one job, none of them a parallel
tagging system.

## Display semantics: resolve-then-discard, never store-and-show

A question worth answering explicitly, since it's easy to assume the wrong
default: **once an alias resolves, the alias text itself is never persisted
against the series and never displayed anywhere series-facing.** The alias
table only exists to redirect free text at ingestion time onto the one
canonical `Tag` — after that, the series is linked to (or its scalar column
holds) the canonical row, exactly as if that canonical value had been given
directly.

Concretely:

| Input | Resolves to | What `SeriesOut` / the UI shows |
|---|---|---|
| MangaDex `contentRating: "pornographic"` | `mature` | `"Mature"` badge — never "Pornographic" |
| `lychee.info` `tags: {theme: [Yaoi]}` | `boys-love` tag | `"Boys' Love"` tag chip — never "Yaoi" |
| MangaDex's own tag `"Boys' Love"` | `boys-love` tag directly (no alias needed — seeded 1:1 per `decisions/10`) | `"Boys' Love"` |

In the common case — tags synced straight from MangaDex — no alias is
involved at all, since the seed data already mirrors MangaDex's own tag names
1:1. Aliases only activate when wording *diverges* from canonical (slang,
abbreviations, or MangaDex's differently-named rating tier), and in every
such case the series ends up linked to the single canonical row, so it's
never possible for one series to show "Yaoi" and another to show "Boys' Love"
for the same underlying tag.

The **only** place an alias's own text is ever rendered is the Settings →
Content taxonomy admin page, as a secondary annotation on the canonical row
(e.g. `Boys' Love (aka: Yaoi, BL)`) — purely for an admin managing the
taxonomy. It's never surfaced on a series card, detail page, tag chip, or
filter button.

### Enforcing it: resolve at the write boundary, not at render time

This isn't a rule the display layer has to honor — it's a consequence of
where resolution is allowed to happen. **Alias resolution only ever runs at
an input boundary** (somewhere free text is entering the system), **never at
an output boundary** (API serialization, frontend rendering). There are
exactly three input boundaries in the current code, and all three must go
through the resolver before a value touches `Series`:

1. **MangaDex provider apply** (`catalog/metadata.py`'s content-rating
   assignment + `reconcile_tags`).
2. **Local import / embedded-metadata scan** (`ingest/importer.py`'s
   `reconcile_tags` call).
3. **`lychee.info` apply** — tags only, via the same `reconcile_tags`;
   `content_rating`/`demographic` don't need resolution since the schema
   already forces the agent to write the canonical word.

Because resolution is finished before anything is persisted, `SeriesOut`,
the OpenAPI contract, and every frontend component (`display.ts`'s
`contentRatingLabel`/`contentRatingClass`, tag chips, filter buttons) need
**zero new alias-handling logic** — they already only have to handle the
closed set of canonical values, exactly as today. That's the actual "proper
display semantics": push all the complexity to the one input boundary so the
output side stays exactly as simple as it already is.

**The failure case is what makes this a safety net, not just a convenience.**
If `resolve_tag_id()` finds neither a matching `Tag` nor a matching alias for
a `content_rating`/`demographic` value, **it must not write the raw value** —
that's precisely today's bug. Instead: leave the field untouched and log a
structured warning, the same warn-and-skip convention `lychee.info` already
uses for a bad field rather than failing the whole apply
(`decisions/20`). This is an asymmetry worth calling out: for the *tag*
groups (genre/theme/format/content), an unresolved name is a legitimate new
tag and `reconcile_tags` correctly creates one — only the closed
`content_rating`/`demographic` enums need a hard "refuse to write an unknown
value" guarantee, since unlike tags they have no "just make a new one" escape
hatch.

(If alias-aware search/filtering is ever built — see Deferred, below — it
fits the same rule: a typed query like "hentai" is resolved to a canonical
tag id *before* running the filter. The results shown back are still 100%
canonical names; it's just another input boundary, not an exception to this
section.)

## Seed data

```python
# (display name, canonical tag id)
_ALIASES = [
    ("Ecchi", "suggestive"),
    ("Hentai", "mature"),
    ("Pornographic", "mature"),   # MangaDex's own raw value — closes the passthrough gap
    ("NSFW", "mature"),
    ("Yaoi", "boys-love"),
    ("BL", "boys-love"),
    ("Yuri", "girls-love"),
    ("GL", "girls-love"),
]
```

Idempotent insert (insert-if-missing by slug), same pattern as
`seed_taxonomy()` (`taxonomy/seed.py:133-142`) — user-created aliases and any
edits survive restarts; a later release can add more seeded aliases without
clobbering them.

## Settings / API surface

- `TaxonomyItemOut` (`taxonomy/schema.py`) gains `aliases: list[str]`
  (names only) so the Content settings table can show "aka: Hentai, NSFW"
  under a rating row, or under any genre/theme/format/content tag.
- Two small nested endpoints, not a field on `TaxonomyUpdate` — an alias set
  is a collection, not a scalar, matching how `decisions/14` handles
  authors/artists (partial-replace-by-role) rather than cramming lists into a
  single PATCH-able field:
  - `POST /api/taxonomy/{tag_id}/aliases` — body `{name: str}`; slugifies,
    rejects if the slug collides with an existing `Tag.id` (can't alias over
    a real, distinct tag) or an existing alias pointing elsewhere.
  - `DELETE /api/taxonomy/{tag_id}/aliases/{alias_id}`.

## Validation & failure handling

- **Alias slug collides with an existing `Tag.id`:** reject — a name that's
  already a real, independent tag can't also be redefined as a synonym of
  something else; that would silently merge two distinct taxonomy rows.
- **Alias slug already points to a *different* tag:** reject with a
  conflict — same alias can't mean two things. (Re-pointing an existing
  alias is a delete + recreate, not an update; aliases are simple enough
  that an update endpoint isn't worth adding.)
- **Alias slug collides with itself (already points to the same tag):**
  no-op, not an error — creating the same alias twice shouldn't be treated as
  a conflict by whatever's calling this (e.g. a re-run seed step or an
  idempotent admin action).

## Consequences

- Splitting "sync key" from "display label" (above) shrinks this from one
  feature into two much smaller ones: genre/theme/format/content tags get
  fully renamable "familiar terms" for **zero code changes** (the capability
  already exists); only the two-group, two-fix carve-out for
  `content_rating`/`demographic` and the `TagAlias` sync-resolution mechanism
  are net-new.
- `reconcile_tags` stops creating duplicate tags for known synonyms across
  all three current callers (MangaDex sync, local import, `lychee.info`)
  with one shared lookup, not three separate fixes.
- Closes the `decisions/10`-documented-but-never-implemented
  `"pornographic"` → `"mature"` rename, using the general alias mechanism
  instead of a special-cased dict — the fix and the feature are the same
  code path.
- One more relation to reason about in the unified taxonomy (`Tag` ←
  `TagAlias`), but the core "one table, `group` column" shape from
  `decisions/10` is untouched — this is additive, not a redesign.
- `catalog/metadata.py:24`'s `_slug()` and `taxonomy/service.py:92`'s
  `_slugify()` are near-duplicate implementations of the same
  normalization; alias resolution needs the identical slugifier on both
  sides of a lookup (whatever a tag/alias was seeded under), so implementing
  this is a natural, low-risk point to unify them into one shared helper
  rather than adding a third copy.

## Deferred / explicitly not in v1

- **Localized tag names** — stays `decisions/10`'s separate, already-tracked
  follow-up; not this table's job.
- **Fuzzy / prefix / typo-tolerant matching** — exact match only, as above.
- **Alias-aware global text search.** The FTS5 index
  (`decisions/17`, `catalog/search_index.py`) covers title/alt-titles/authors
  only — it doesn't index tag names at all today, aliased or not. Extending
  full-text search to tags is a separate, larger change; out of scope here.
- **Alias-aware tag-filter typeahead in the browse UI.**
  `frontend/src/components/FilterPanel.vue` renders every tag in a group as a
  flat button list today (no search/typeahead box exists for the ~70-tag
  vocabulary). Introducing one — and wiring alias text into it — is a
  reasonable future UI improvement but isn't required to ship this design;
  the alias table is useful on the ingestion side (`reconcile_tags`,
  `resolve_tag_id`) independent of any frontend search affordance.

## Alternatives considered

- **A separate `lychee_tag` field/table for non-provider-sourced tags**
  (raised during design review) — rejected: it recreates the exact
  duplication problem this doc solves, just one level up (now there are two
  tag identities to reconcile instead of one), and is unnecessary once
  `Tag.id` (sync key) and `Tag.name` (display label) are recognized as
  already-separate concerns — see "Two separate concerns," above.
- **A hardcoded `{"pornographic": "mature"}` translation dict** local to the
  MangaDex provider — rejected: fixes only gap #2, duplicates a concept
  (canonical-name resolution) the taxonomy already has room for, and doesn't
  help the yaoi/yuri case at all.
- **Per-group alias scoping** (an alias only resolves within its own tag
  group) — rejected: adds a disambiguation dimension neither consumer needs.
  Alias text is unambiguous free text in this domain; a flat global lookup
  keeps `reconcile_tags`/`resolve_tag_id` a single dict check.
- **Storing aliases as a JSON/CSV column on `Tag` itself** (e.g.
  `Tag.alias_names: list[str]`) instead of a child table — rejected: loses
  the ability to enforce global uniqueness at the DB level (a JSON column
  can't be the target of a `UNIQUE` constraint or an FK-style lookup), and
  can't cheaply answer "does this alias already exist anywhere" without
  scanning every row. A child table with `id` as its own slug gets both for
  free, matching how `Tag` itself is modeled.

## Promotion path

Done — formalized as [ADR 21](decisions/21-tag-aliases.md), following the
same design-doc-then-ADR sequence [08](08-metadata.md) →
[ADR 20](decisions/20-lychee-info-metadata.md) followed. That ADR is now the
authoritative record of what shipped; this doc stays as the deeper design
rationale it references.
