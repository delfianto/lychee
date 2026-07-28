# 20 — `lychee.info`: a native YAML metadata sidecar

**Status:** Implemented — reader and writer both.

## What this is

`lychee.info` is a **series/gallery-folder-level YAML sidecar**, written by an
LLM agent pointed at local content no provider can match (old scanlations,
doujinshi, image galleries). On scan, the file is parsed, strictly validated,
and applied through the exact same path a manual edit uses — no new
precedence tier.

The writer is a **Claude Skill**, not this repo's `mcp/` server: the
`cosplay-metadata` skill in the separate
[`delfianto/lychee-agents`](https://github.com/delfianto/lychee-agents) repo.
It reasons about a gallery set's folder name (web search when ambiguous) to
infer franchise/character, samples and views actual frames (via a bundled
`ffmpeg`-based preview converter) to set an accurate content rating, and
writes the sidecar through its own schema-strict, read-merge-write Python
script — a direct filesystem writer, independent of `mcp/` and the backend
API. `mcp/` ([13](13-metadata-providers.md) territory — batch REST-API
operations like bulk tagging/downloads) has no `lychee.info`-writing tool at
all; the two are unrelated mechanisms that happen to serve the same library.

It exists instead of ComicInfo.xml because ComicInfo is XML, shaped for
Western comics, and not something an LLM agent should be generating by hand —
a flat, low-ambiguity YAML schema is far more reliable for a model to produce
and re-produce correctly (e.g. `crossovers` is always a list, never "a list or
a single object depending on count"). Strict validation (`extra="forbid"`
Pydantic, at every level) is deliberate: a hallucinated field or wrong enum
value should fail loudly, not silently do something wrong.

## Schema (v1)

`backend/src/ingest/lychee_info.py`'s `LycheeInfoFile` — the same strict
Pydantic model both parses the file and, exported as JSON-Schema, is what a
writer validates its own output against:

```yaml
schema: 1                       # required — only 1 is currently supported
kind: manga                     # required — manga | comic | gallery
                                 #   (mismatch vs. the owning library's kind never
                                 #   reclassifies the series — warns, kind ignored)

title: "Bloodmoon Apothecary"   # overrides the folder-derived name
titles:                         # additional forms — union-merged by (lang, title),
  - lang: ja                    #   never locked (ADR 18: titles are always a union)
    type: native                # native | romanized | english | alt
    title: "血月の薬局"

description: |
  A night-shift pharmacist discovers her new clinic sits on a ley line
  that only the dead can find...

status: ongoing                 # ongoing | completed | hiatus | cancelled
                                 #   — manga/comic only; warns + skipped on a gallery
year: 2023
originCountry: kr               # ISO 3166-1 alpha-2, lowercase (pattern-validated)

contentRating: suggestive       # safe | suggestive | erotica | pornographic (manga/comic) | explicit (gallery)
demographic: shonen             # shonen | shojo | seinen | josei | none
                                 #   — manga/comic only; warns + skipped on a gallery

tags:                           # the 4 user-assignable taxonomy groups (ADR 10) —
  genre: [horror, medical]      #   union-merged into Series.tags, not replaced
  theme: [supernatural]
  format: [doujinshi]
  content: [gore]

credits:                        # → SeriesCredit; split by role, each role replaced
  - name: "Ha-eun Park"         #   only if that role has ≥1 entry in the file
    role: author                # author | artist
  - name: "Seo-yeon Kang"
    role: artist

crossovers:                     # only the FIRST entry is applied (see below) —
  - series: "Some Existing Series"  # → Series.source / characters_json
    characters: [Character A, Character B]

provider:                       # site -> id; seeds a match (catalog.matching.set_match)
  mangadex: "<provider-series-id>"
external:                       # tracker -> id -> external_ids_json, by internal key
  anilist: "<id>"               #   (al / mal / mu — Tracker.external_id_key)
  myanimelist: "<id>"
  mangaupdates: "<id>"

generated:                      # provenance of the last write only, no history
  by: "lychee-mcp"
  model: "claude-..."
  at: "2026-07-28T12:00:00Z"    # informational — not parsed into a datetime
  version: 1                    # → Series.metadata_file_version (audit trail only)
```

Every field is optional except `schema`/`kind` — a partial patch, not a full
record. Explicitly out of scope: `favorite`, `libraryStatus`, `userRating`,
`rating` — all per-user or provider-owned state, not descriptive metadata
about the work. Any unknown top-level or nested key, a wrong enum value, or an
unsupported `schema` version fails the **whole file** — a bad file is skipped
(logged + counted) rather than partially misapplied.

## How it's wired in

- **Zero new locking logic.** `catalog.service._apply_metadata_fields` is the
  refactored-out core of `PATCH /api/series/{id}` (`update_series`);
  `catalog.service.apply_lychee_info` builds the same `SeriesUpdate`-shaped
  `fields` dict from a parsed file and calls it directly. Every field the file
  sets gets auto-locked exactly the way a manual edit would.
- **Re-apply gating:** `Series.metadata_file_hash` (xxh3-128 of the raw file
  bytes, mirroring `Book.partial_hash`) — a scan only re-parses/re-applies
  when it differs. A malformed file's hash is deliberately **not** stored, so
  it keeps warning every scan until fixed rather than silently going quiet.
  `Series.metadata_file_version` separately mirrors the file's own
  `generated.version` — audit trail only, not used for gating.
- **Titles are a pure union, never locked.** `SeriesUpdate` gained a `titles`
  field (mirroring [18](18-title-variants.md)'s `TitleVariant`); applying it
  merges by `(language, title)` key and never replaces or locks — every
  source contributes titles as a union, and a pure-additive merge can't
  clobber anything. Contrast with `title` itself, `tags`, `authors`/`artists`,
  which use manual-edit *replace-what-you-give* semantics and do lock.
- **Tags are unioned, not replaced**, unlike the human-facing `PATCH`
  `tag_ids` (full replace) — an agent's partial file (e.g. `format:
  [doujinshi]` only) shouldn't drop tags a provider match already set in
  groups it doesn't mention. Unknown tag names auto-create via the existing
  `catalog.metadata.reconcile_tags` (no new "create tag" path).
- **`provider:` seeds a match** by calling `catalog.matching.set_match`
  directly (same function the manual match-picker UI uses) — an
  unavailable/unknown provider id becomes a warning, not a failure.
  **`external:`** merges into `external_ids_json` by key, mapping the
  sidecar's friendly names to the trackers' own keys (`anilist`→`al`,
  `myanimelist`→`mal`, `mangaupdates`→`mu`, matching `Tracker.external_id_key`);
  an unrecognized name warns and is skipped.
- **`crossovers`: only the first entry is applied** (→ `Series.source` /
  `characters_json`). The schema allows a list "for multi-fandom"; the
  underlying columns are single-value fields with no junction table. A
  second+ entry is dropped with a warning.
- **Kind mismatch / kind-inapplicable fields:** `series.kind` is never set
  from the file (it's derived from the owning library) — a mismatch is purely
  a warning. `status`/`demographic` are silently inapplicable-but-warned on a
  `kind=gallery` series; every other field still applies.
- **Scan-result surfacing:** `ScanSummary` gained `lychee_info_applied`
  (count) and `lychee_info_warnings` (`{path, reason}` list), surfaced as
  `lycheeInfoApplied` / `lycheeInfoWarnings` in the scan task's
  `TaskOut.result` — the same JSON slot `thumbsGenerated` uses, no new
  notification channel.
- **File discovery:** exact literal filename `lychee.info`, read at the same
  directory a scanned series' books live (or, for `kind=gallery` two-level
  scans, at each per-work folder) — the same level `Cover.avif`/`cover.*` are
  read from. `.info` was already outside every image/media extension
  allowlist in `media.containers`, so it was never at risk of being mistaken
  for a page or a book.

## Not built

- Chapter/book-level overrides, a "human reviewed" marker in the file,
  collection membership via the file, full write history.
- True multi-crossover/multi-franchise support (would need a
  `series_crossover`-shaped junction table) — today's `source`/
  `characters_json` are single-value by design; revisit only if multi-fandom
  doujin metadata turns out to matter in practice.
