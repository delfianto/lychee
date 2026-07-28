# 14 — Metadata field mapping & lock-merge rules

**Status:** Implemented — much simpler than originally scoped: two writers,
one lock check, no embedded-format (ComicInfo/OPF) support.

## What actually writes metadata

Exactly two call sites, both funneling through the same lock check:

- **`apply_metadata`** (`backend/src/catalog/metadata.py`) — MangaDex
  provider data. Skips any field present in `series.locked_fields_json`
  via an `unlocked()` closure.
- **`_apply_metadata_fields`** (`backend/src/catalog/service.py`) — shared
  by manual `PATCH /api/series/{id}` (`update_series`) and
  `apply_lychee_info` ([20](20-lychee-info-metadata.md)'s sidecar apply).
  Every field it touches gets added to `locked_fields_json` on write —
  auto-locking, exactly like a manual edit, because `lychee.info` *is*
  applied through the manual-edit path.

There is no "5-tier precedence" merge and no `MetadataPatch` object — the
filename parser ([06](06-filename-parser.md)) only derives `Chapter.number`/
`volume`/`number_sort` at scan time, it never participates in a
Series-level merge at all.

## Locking

A single `locked_fields_json` set per `Series` (not one boolean per field).
A manual edit or `lychee.info` write auto-locks every field it touches; a
later MangaDex refresh skips locked fields via `apply_metadata`'s
`unlocked()` check. Locks survive move/rename restore
([07](07-scan-pipeline.md)) and every re-scan/refresh.

## Union vs. replace differs by writer, not by field

- **`apply_metadata`** (MangaDex): `tags` — **replaced** wholesale
  (`reconcile_tags` result assigned directly).
- **Manual `PATCH`**: `tags` — **replaced** via `_resolve_tags`; credits —
  replaced per edited role.
- **`apply_lychee_info`**: `tags` — **unioned** with existing (a partial
  agent-authored file shouldn't drop tags a provider match already set in
  groups it doesn't mention); `titles` — always unioned, never locked, per
  [18](18-title-variants.md).

## Content rating vs. embedded age rating

`content_rating` ([10](10-tagging-content-rating.md)) —
`safe/suggestive/erotica/pornographic` for manga/comic,
`safe/suggestive/erotica/explicit` for gallery — is the canonical
explicitness axis; MangaDex's `contentRating` maps onto it 1:1, no renaming.
A `ComicInfo AgeRating`→`content_rating` mapping table was planned but never
built — moot anyway, since ComicInfo isn't read at all (see below).

## Not built

**No embedded-metadata reading or writing of any kind.**
`backend/src/ingest/scanner.py`'s own module docstring lists "embedded
ComicInfo/OPF metadata" under deferred follow-ups. Concretely: no
ComicInfo.xml reading on scan, no ComicInfo.xml writing on export or
download (the downloader writes plain numbered AVIF pages into the CBZ, no
XML sidecar), no EPUB OPF parsing, no PDF info parsing — consistent with
there being no EPUB/PDF container support at all
([05](05-domain-model.md)). The role embedded metadata would have played —
an "escape hatch" source of series-level metadata beyond what the filename
carries — is instead filled by `lychee.info`
([20](20-lychee-info-metadata.md)), a sibling YAML file, not an embedded
format, and via a completely different application path than what this ADR
originally sketched (it goes through the manual-edit lock mechanism
directly, not a precedence-ranked patch merge).

No per-library "prefer provider over embedded" toggle either — moot, since
there's no embedded source to prefer over.
