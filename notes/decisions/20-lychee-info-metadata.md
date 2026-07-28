# 20 — `lychee.info`: a native YAML metadata sidecar

**Status:** ✅ Accepted — implemented.

## Context

Full design + rationale lives in [`../08-metadata.md`](../08-metadata.md) (promoted
here per its own "Promotion path" section); read it for the complete schema and the
"why YAML, why LLM-authored, why not ComicInfo.xml" discussion. This ADR records the
decision as built and the handful of judgment calls the design doc left open.

In short: `lychee.info` is a **series/gallery-folder-level YAML sidecar**, intended to
be written by an LLM agent ([`mcp/`](../../mcp/), [plan.md PART J](../plan.md)) pointed
at unmatched local content (old scanlations, doujinshi, image galleries) that no
provider can match. On scan, the file is parsed, strictly validated (Pydantic,
`extra="forbid"`), and applied as if it were a manual edit — reusing [14](14-metadata-mapping.md)'s
lock mechanism as-is.

## Decision

- **Schema** (`backend/src/ingest/lychee_info.py`, `LycheeInfoFile`): schema v1 exactly
  as specced in `08-metadata.md` — `schema`/`kind` required, everything else optional.
  Wire fields are camelCase (`CamelModel`-based, same tool as every other API schema),
  which happens to line up with the design doc's own YAML examples (`contentRating`,
  `originCountry`, …) with zero translation needed. `schema_version != 1` and any
  unknown/hallucinated field both fail the whole file, by design.
- **Enforcement — zero new locking logic.** `catalog.service._apply_metadata_fields` is
  the refactored-out core of the existing `PATCH /api/series/{id}` handler
  (`update_series`); `catalog.service.apply_lychee_info` builds the same
  `SeriesUpdate`-shaped `fields` dict from a parsed file and calls it directly. Every
  field the file sets gets auto-locked exactly the way a manual edit would — this ADR
  adds no new precedence tier.
- **Re-apply gating:** `Series.metadata_file_hash` (xxh3-128 of the raw file bytes,
  mirroring `Book.partial_hash`) — a scan only re-parses/re-applies when it differs.
  A malformed file's hash is deliberately **not** stored, so it keeps warning every
  scan until fixed rather than silently going quiet. `Series.metadata_file_version`
  separately mirrors the file's own `generated.version` — audit trail only, not used
  for gating.
- **Titles are a pure union, never locked.** `SeriesUpdate` gained a `titles` field
  (mirroring [18](18-title-variants.md)'s `TitleVariant`); applying it merges by
  `(language, title)` key and never replaces or locks — per 18, every source
  contributes titles as a union, and a pure-additive merge can't clobber anything, so
  there's nothing to protect with a lock. (Contrast with `title` itself, `tags`,
  `authors`/`artists`, which use the existing manual-edit *replace-what-you-give*
  semantics and do lock.)
- **Tags are unioned, not replaced**, unlike the human-facing `PATCH` tag_ids
  (full replace) — an agent's partial file (e.g. `format: [doujinshi]` only)
  shouldn't drop tags a provider match already set in groups it doesn't mention.
  Unknown tag names auto-create via the existing `catalog.metadata.reconcile_tags`
  (no new "create tag" path, per the design doc).
- **`provider:` seeds a match** by calling `catalog.matching.set_match` directly
  (same function the manual match-picker UI uses) — an unavailable/unknown provider
  id becomes a warning, not a failure. **`external:`** merges into
  `external_ids_json` by key, mapping the sidecar's friendly names to the trackers'
  own keys (`anilist`→`al`, `myanimelist`→`mal`, `mangaupdates`→`mu`, matching
  `Tracker.external_id_key`); an unrecognized name warns and is skipped.
- **`crossovers`: only the first entry is applied** (→ `Series.source` /
  `characters_json`). The doc's schema allows a list "for multi-fandom"; the
  underlying columns are single-value (today, gallery-only-in-practice) fields with
  no junction table. A second+ entry is dropped with a warning rather than silently
  ignored or forcing a schema change nothing else needs yet.
- **Kind mismatch / kind-inapplicable fields:** `series.kind` is never set from the
  file (it's derived from the owning library, same as always) — a mismatch is purely
  a warning. `status`/`demographic` are silently inapplicable-but-warned on a
  `kind=gallery` series; every other field still applies.
- **Scan-result surfacing:** `ScanSummary` gained `lychee_info_applied` (count) and
  `lychee_info_warnings` (`{path, reason}` list), surfaced as `lycheeInfoApplied` /
  `lycheeInfoWarnings` in the scan task's `TaskOut.result` — the same JSON slot
  `thumbsGenerated` already uses (PART H), no new notification channel.
- **File discovery:** exact literal filename `lychee.info`, read at the same
  directory a scanned series' books live (or, for `kind=gallery` two-level scans, at
  each per-work folder) — the same level `Cover.avif`/`cover.*` are read from. No new
  exclusion logic was needed in `media.containers` — `.info` was already outside
  every image/media extension allowlist, so it was never at risk of being mistaken
  for a page or a book.

## Consequences

- A local doujin/gallery collection with zero provider matches can get full
  taxonomy, credits, franchise/character data, and content rating from one agent
  pass — no per-folder Edit-series clicking.
- The locking mechanism is entirely reused: from the merge engine's point of view,
  `lychee.info` is just another manual-edit caller.
- `SeriesUpdate` (and therefore the OpenAPI contract) gained a `titles` field it
  didn't have before — a side effect of giving the file a path to write structured
  title variants through the same auto-lock mechanism as everything else. The
  human-facing edit UI doesn't need to expose it; the field existing and being
  unused there is harmless.

## Deferred / explicitly not built

Same list as `08-metadata.md`'s: chapter/book-level overrides, a "human reviewed"
marker in the file, collection membership via the file, full write history. Also
newly identified during implementation: **true multi-crossover / multi-franchise
support** would need a `series_crossover`-shaped junction table — not built, since
today's `source`/`characters_json` predate this feature and are single-value by
design; revisit only if multi-fandom doujin metadata turns out to matter in practice.

## Alternatives considered

See `08-metadata.md` (ComicInfo.xml rejection, why the file is a YAML mapping, why
strict-fail over lenient-defaults). Additionally, for this ADR specifically:

- **A separate `titles`-only lock key** — rejected: `apply_metadata`'s MangaDex path
  already gates both `Series.title` and `title_variants` behind one `"title"` lock
  check; a second key would either do nothing (if titles alone doesn't set it) or
  create two ways to protect the same data. Not locking at all (pure union) is
  simpler and matches ADR 18's stated merge policy for the collection.
- **Full-replace for file-sourced tags** (matching the human `PATCH` behavior) —
  rejected: a partial, agent-authored file shouldn't be able to silently delete
  tags from groups it never mentions.
