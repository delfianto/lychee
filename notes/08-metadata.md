# Overview 8 — lychee.info: A Native Metadata Sidecar Format

Unlike 00–07, this isn't cross-project comparison research — it's lychee's own
design, arrived at by deliberately rejecting ComicInfo.xml (XML, Western-comic-
shaped, "never really a standard" per the discussion that produced this doc) in
favor of a lychee-native YAML sidecar. Builds directly on
[`05-metadata-tagging.md`](05-metadata-tagging.md)'s ComicInfo.xml findings and
[`decisions/05`](decisions/05-domain-model.md) (domain model/filesystem mapping),
[`decisions/10`](decisions/10-tagging-content-rating.md) (taxonomy),
[`decisions/13`](decisions/13-metadata-providers.md) (providers),
[`decisions/14`](decisions/14-metadata-mapping.md) (field mapping + locking —
the mechanism this format plugs into), and
[`decisions/18`](decisions/18-title-variants.md) (title variants) — read those
first; this doc assumes their schema/precedence machinery as given.

## Goal & intended author

**`lychee.info` is written by an LLM (via an agent tool — e.g. `mcp/`), not
typed by hand.** The target workflow: point an agent at a folder of unmatched
local content — old scanlations, doujinshi, image galleries — that MangaDex
has no hope of matching, and have it infer what it can (title, tags, franchise/
characters, credits) and write a `lychee.info` file. On the next scan, that
file becomes the *base* truth for the series; a MangaDex match, if one is ever
possible, fills in whatever the file didn't set. Because the intended author
is a model, not a person, three things follow:

- **A flat, low-ambiguity schema an LLM can reliably reproduce** beats one
  that's merely convenient to hand-type — no shorthand-vs-full-form
  polymorphism. `crossovers` (below) is always a list, even for a single-
  franchise doujin, rather than "a list or a single object depending on count."
- **Strict schema validation is a feature, not friction.** A hallucinated
  field name or wrong enum value should fail loudly (logged, flagged) rather
  than silently doing something wrong.
- **Regeneration must read-merge-write, never blind-overwrite.** This is a
  requirement on whatever *writes* these files (the agent/MCP tool), not a
  field in the schema — nothing here encodes "don't overwrite me"; the
  expectation is simply that any writer reads the existing file first and
  updates it in place rather than regenerating from scratch.

## Placement & scope

- One file per **series or gallery folder** — sibling to the chapter
  archives / image files, the same level `Cover.avif` already lives at
  ([ADR 19](decisions/19-avif-storage.md)).
- **Series-level only.** No chapter/book-level block. Per-chapter embedded
  metadata (title, credits) is out of scope here — if it's ever wanted,
  that's ComicInfo.xml-inside-the-archive territory, untouched by this doc.
- Literal filename `lychee.info`, no `.yaml`/`.yml` extension, despite the
  content being YAML — a deliberate choice, matching `Cover.avif`'s
  meaningful-name-over-convention precedent. Editors won't syntax-highlight
  it by default; acceptable given it's machine-written, not hand-edited.

## Schema (v1)

```yaml
schema: 1                       # format version — bump only on a breaking shape change

kind: manga                     # manga | comic | gallery — MUST match the owning library's kind (see below)

title: "Bloodmoon Apothecary"   # overrides the folder-derived name — same power ComicInfo.xml's <Series> has (ADR 05)
titles:                         # optional — mirrors TitleVariant (ADR 18) exactly
  - lang: ja
    type: native                # native | romanized | english | alt
    title: "血月の薬局"
  - lang: ja
    type: romanized
    title: "Ketsugetsu no Yakkyoku"

description: |
  A night-shift pharmacist discovers her new clinic sits on a ley line
  that only the dead can find...

status: ongoing                 # ongoing | completed | hiatus | cancelled — manga/comic only
year: 2023
originCountry: kr               # ISO 3166-1 alpha-2, lowercase

contentRating: suggestive       # safe | suggestive | erotica | mature — same scale as everywhere else, no new axis
demographic: shonen             # shonen | shojo | seinen | josei | none — manga/comic only

tags:
  genre: [horror, medical]
  theme: [supernatural]
  format: [doujinshi]           # presence of "doujinshi" here *is* the "is this a doujin" signal — no separate boolean

credits:                        # mirrors SeriesCredit (name, role, position = list order)
  - name: "Ha-eun Park"
    role: author                # author | artist
  - name: "Seo-yeon Kang"
    role: artist

crossovers:                     # generalizes today's gallery-only source/characters to any kind
  - series: "Some Existing Series"   # the franchise/parody/depicted work; omit entirely for a wholly original work
    characters: [Character A, Character B]
  # - series: "A Second Franchise"   # a second entry is how a crossover/multi-fandom doujin is expressed
  #   characters: [Character C]

provider:                       # optional — pre-seeds a match; applying this triggers the normal match/refresh flow
  mangadex: "<provider-series-id>"
external:                       # → external_ids_json (tracker matching)
  anilist: "<id>"
  myanimelist: "<id>"

generated:                      # provenance — describes the LAST write, not a full history
  by: "lychee-mcp"                # tool/agent that produced this file
  model: "claude-..."               # model identifier, if applicable
  at: "2026-07-28T12:00:00Z"          # ISO timestamp of last write
  version: 1                            # increments on every write (maintained by whatever writes the file)
```

Every field is optional except `schema` and `kind` — this is a partial patch,
not a full record (mirrors `SeriesUpdate`'s existing "absent fields are left
unchanged" semantics exactly — see Enforcement below).

**Explicitly out of scope, by design:** `favorite`, `libraryStatus`,
`userRating`, `rating` (community) — all per-user or provider-owned state,
not descriptive metadata about the work itself.

## Enforcement: how "the file wins" actually happens

Per-field precedence already exists ([ADR 14](decisions/14-metadata-mapping.md)):
manual edits auto-lock and always win; embedded sources (ComicInfo/OPF) sit
below that, only protected by locks some *other* source already set.
`lychee.info` specifically needs the **auto-locking** behavior — "the file
provides a base MangaDex sync doesn't clobber" only works if applying it
behaves like a manual edit, not like ComicInfo.xml's passive "read on scan,
respect existing locks" behavior.

**Mechanism:** don't add a new precedence tier. On scan, when `lychee.info`
is found: parse → validate (strict Pydantic model) → build a
`SeriesUpdate`-shaped payload → apply it through the **exact same internal
path** `PATCH /api/series/{id}` already uses. That path already auto-locks
every field it touches (ADR 14 item 1) — this needs **zero new locking
logic**, only a second *caller* of the existing update function.

**Re-apply on change, not blindly on every scan.** Store a content hash of
the applied file (`series.metadata_file_hash`, mirroring how
`file_last_modified` already tracks book files) plus the file's own declared
`generated.version` (human-readable audit trail — "this series is on cut 3
of the agent's analysis"). A scan reapplies `lychee.info` only when the
on-disk hash differs from the stored one. Editing the file and rescanning is
the update mechanism; an unchanged file costs nothing on repeat scans.

**Partial application, always.** Since every field is optional, an
incomplete file (e.g. only `tags` + `crossovers`, no `title`/`description`
because the agent wasn't confident) locks only what it set — MangaDex
match/refresh (or a later human edit) fills in the rest normally, exactly as
it would for any other field today.

## Validation & failure handling

- **Schema:** a Pydantic model (the same tool used everywhere else in the
  backend) is the single source of truth — it validates on read *and* can be
  exported as a JSON Schema for whatever writes these files, so the MCP tool
  can validate its own output against the identical shape before writing.
  The two sides structurally can't drift.
- **Kind mismatch** (`kind` disagrees with the owning library's kind): **not
  an override.** A manga library holds manga; a `lychee.info` claiming
  `kind: gallery` inside it doesn't get to reclassify the series. Ignore the
  `kind` field specifically, log a structured warning, and still apply every
  other valid field in the file — one bad field shouldn't discard an
  otherwise-good file. Surface the mismatch count/list via the scan task's
  `result` (the same `TaskOut.result` JSON slot `thumbsGenerated` already
  uses for gallery-scan output — see `plan.md` PART H), so the frontend has
  something to toast/display without inventing a new notification channel.
- **Kind-inapplicable fields** (e.g. `demographic`/`status` set on a
  `kind: gallery` file): validated per-kind by the same Pydantic model
  (conditional fields), same warn-and-skip-that-field treatment as a kind
  mismatch — never fail the whole file over one inapplicable field.
- **Malformed / fails validation entirely** (bad YAML, hallucinated field,
  wrong enum value): log the path + reason, skip applying the file for that
  scan pass — the series still gets indexed normally from disk, just without
  `lychee.info` enrichment — and count it in the same scan-result warning
  slot. Never fail the scan itself over one bad sidecar file.
- **Unknown tag values** (a tag name not in the current taxonomy): auto-create
  it in the stated group as a regular user-created tag (`is_default = false`,
  enabled). [ADR 10](decisions/10-tagging-content-rating.md) already supports
  arbitrary user-created tags via the same `tag` table, so this needs no
  schema change — just reuses the existing "create tag" path. Rejected
  alternative: strict-only + warn-and-drop unknown tags — too brittle given
  the agent is likely to propose real, useful tags that simply aren't seeded
  yet.

## Consequences

- A local doujin/gallery collection with zero MangaDex matches can still get
  full taxonomy, credits, franchise/character data, and content rating — via
  one agent pass instead of clicking through the Edit-series modal per folder.
- The locking mechanism is entirely reused, not reinvented — from the merge
  engine's point of view, `lychee.info` is just "a manual edit sourced from a
  file."
- `Cover.avif` and `lychee.info` are now both meaningful, non-content sidecar
  files a scan must know to skip when resolving books/pages — extends the
  existing `is_cover_file()`-style exclusion (PART H) so a `lychee.info` at a
  series root is never mistaken for a page or a book.

## Deferred / explicitly not in v1

- Chapter/book-level metadata overrides (title, per-chapter credits) — stays
  ComicInfo.xml-in-archive territory if that's ever built.
- A "human reviewed, don't touch" marker in the file itself — superseded by
  the harder requirement that any writer must read-merge-write rather than
  regenerate from scratch, so there's no blind-overwrite risk to guard
  against in the first place.
- Collection/list membership via the file — collections are personal
  curation, not descriptive metadata about the work.
- Full write history / multiple past `generated` entries — `generated`
  reflects only the latest write; anything more belongs in server logs, not
  the sidecar.

## Promotion path

This doc is the design; it isn't yet an accepted ADR. If/when this gets
built, formalize it as a numbered decision in `decisions/` (the natural next
slot, following the same design-doc-then-ADR sequence [ADR 19](decisions/19-avif-storage.md)
followed for `Cover.avif`) rather than leaving the real spec living only here.
