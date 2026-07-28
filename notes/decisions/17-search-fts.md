# 17 — Full-text search tokenizer (FTS5 `trigram`)

**Status:** Implemented in code — but see [04](04-database-sqlite.md)'s
"Known gap": the FTS5 table is never actually created outside tests, so
production search silently runs `LIKE`-only today.

## Why `trigram`

FTS5's default `unicode61` tokenizer splits on spaces/punctuation into
words — useless for Japanese/Chinese, which have no spaces, so a whole
title becomes one un-searchable blob. `trigram` indexes every run of 3
characters instead, which gives substring matching *and* CJK support for
free (3-character windows don't need spaces) — exactly the wall Komga hit
in 2021 (dropped FTS5 for Lucene because of this) before `trigram` existed
in SQLite (added in 3.34, Dec 2020).

## What's indexed

`series_fts` (`backend/src/catalog/search_index.py`) — three columns only:

```sql
CREATE VIRTUAL TABLE series_fts USING fts5(
  series_id UNINDEXED, title, alt_titles, authors,
  tokenize = 'trigram'
);
```

**No `tags`, no `summary`/description column** — those aren't searchable, a
narrower scope than originally planned. `alt_titles` covers every title
variant ([18](18-title-variants.md)) concatenated, so a series is findable
by any of its known names (native/romanized/English) — this, not the
tokenizer, is what makes multilingual search actually work; `trigram`
doesn't transliterate.

It's a **standalone/own-content** table, not SQLite's `content=`
external-content mechanism — it duplicates the indexed text via insert/
update/delete triggers on `series`, `title_variant`, and `series_credit`,
rather than referencing the source columns directly.

## Tokenizer options

Plain `tokenize = 'trigram'`, no explicit `case_sensitive`/
`remove_diacritics` options set (FTS5's `trigram` tokenizer defaults
`case_sensitive` to 0 already; `remove_diacritics` defaults to 0/off — so
"Pokemon" is not guaranteed to match "Pokémon" the way the original design
intended).

## Query & ranking

`build_match()` requires ≥3-character whitespace-split terms (trigram's
minimum); shorter queries return `None` and the caller
(`catalog/repository.py:search_series`) falls back to a plain `LIKE` title
match. Ranked via `bm25(series_fts, 0.0, 10.0, 4.0, 1.0)` — title weighted
highest, then alt-titles, then authors.

## Portability

No `pysqlite3-binary` pin exists (`backend/pyproject.toml` has no such
dependency) — relies on Python 3.14's bundled SQLite as-is, and no startup
verification of compiled FTS5 options runs. This turned out fine in
practice since the bundled SQLite is new enough, but it's worth knowing the
originally-planned safety pin was never added.

## Escape hatches (not built, not needed yet)

A hybrid `unicode61` + `trigram` index (better Latin word-ranking) or
swapping to Tantivy/Meilisearch behind the same `search_series()`/
`search_ids()` interface remain options if FTS5 trigram ever proves
insufficient — neither has been started.
