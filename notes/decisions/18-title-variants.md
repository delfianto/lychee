# 18 — Title & name variants (multilingual titles)

**Status:** Implemented — storage only; display-resolution logic was never
built.

## Storage

`TitleVariant` (`backend/src/catalog/models.py`), a language-tagged
one-to-many table **with an explicit role column**, not just a language
code:

```python
title_variant(
  id, series_id → series,
  title: str,
  language: str,                                          # default ""
  variant_type: "native" | "romanized" | "english" | "alt",  # default "alt"
  is_primary: bool,
)
```

`Series.title` is the plain display value (not a separately-denormalized
`display_title` field) — set directly by whichever unlocked writer last
touched it. `Series.sort_title` is the sort key, populated as
`title.lower()` (no natsort normalization at that call site).

## Population — `variant_type` isn't meaningfully set by MangaDex sync

MangaDex ingestion (`_build_variants` in `catalog/metadata.py`) creates the
primary title with `is_primary=True` but leaves `variant_type` at its
default `"alt"` for every title, including the primary and every
alt-title — MangaDex's raw language tags are passed through as-is with no
romanization-suffix normalization. So after a MangaDex sync, essentially
every variant ends up tagged `"alt"` regardless of whether it's actually the
native/romanized/English form. `variant_type` only gets a meaningful value
via a manual edit or a `lychee.info` sidecar
([20](20-lychee-info-metadata.md)), both of which accept `type:
native|romanized|english|alt` directly.

Titles are always a pure **union** merge, never locked or replaced — every
source (MangaDex, manual edit, `lychee.info`) contributes into
`title_variant`, deduplicated on `(language, title)`.

## Not built

- **No `display_title` resolution algorithm.** The originally-planned
  "preferred-language → romanized → English → is_primary → any" lookup
  doesn't exist — `Series.title` is just whatever value the last unlocked
  writer set, not a computed resolution over the variant set.
- **No `preferred_title_language` setting**, global or per-user — grep
  confirms nothing in the codebase reads or writes it.
- No BCP-47 `-ro` romanization-suffix convention actively applied — MangaDex's
  language codes are stored verbatim.

## Search

The FTS `alt_titles` column ([17](17-search-fts.md)) concatenates every
`TitleVariant.title`, so a series is findable by any of its known names —
this is the part of the original design that did ship and matters most in
practice, since `trigram` can't transliterate on its own.
