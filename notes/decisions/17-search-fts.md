# 17 — Full-text search tokenizer (FTS5 `trigram`)

**Status:** ✅ Accepted (resolves the open question from [04](04-database-sqlite.md))

## Context

[04](04-database-sqlite.md) chose SQLite **FTS5** for search but left one choice open: which **tokenizer** — `trigram` everywhere, or a hybrid `unicode61` + `trigram`. This decides whether **CJK** (Japanese/Chinese/Korean) titles and **substring** search work — the exact wall Komga hit (it dropped FTS5 for Lucene in 2021 because the default tokenizer can't do CJK). Note we only search **short metadata fields** (titles, alt-titles, authors, tags), not book contents.

## Plain-language background (why the tokenizer matters)

A *tokenizer* decides how text is chopped into searchable pieces:

- **`unicode61`** (FTS5's default) splits on spaces/punctuation into **words**. Great for "Attack on Titan"; **useless for Japanese/Chinese**, which have no spaces — the whole title becomes one un-searchable blob — and it can't match a piece in the middle of a word.
- **`trigram`** indexes every run of **3 characters**: "Titan" → `Tit`, `ita`, `tan`. That makes **substring** search work (`tita` finds "Titan") and — the important part — **CJK works too**, because 3-character windows don't need spaces. The cost is a larger index and a **3-character minimum** query length.

For a library search box over short titles, **"contains" (substring) is exactly what users expect** (type a few characters, see matches), and CJK is a hard requirement for manga. So trigram's tradeoffs are upside here, not a compromise.

## Decision

**Use the FTS5 `trigram` tokenizer everywhere — one search index — case-insensitive and diacritics-folded.**

- **Indexed unit:** an **external-content FTS5 table mirroring `series`**, columns `title, alt_titles` (all title forms from [18](18-title-variants.md) concatenated)`, authors, tags, summary`, kept in sync by insert/update/delete **triggers** (raw DDL in an Alembic migration, per [04](04-database-sqlite.md)). Series-centric search ([10](10-tagging-content-rating.md)); a book-level FTS table can be added the same way later.
- **Tokenizer options:** `tokenize = 'trigram case_sensitive 0 remove_diacritics 1'` — so "Pokemon" matches "Pokémon" and case is ignored.
- **Multilingual is solved by indexing every title variant, not by the tokenizer.** trigram can't transliterate (typing romaji won't match kana). So we index **all known title forms** — `title` + `alt_titles` (MangaDex supplies native + romaji + English, [13](13-metadata-providers.md)/[14](14-metadata-mapping.md)) — so a series is findable by any of its names. **This is the real key to good manga search.**
- **Query handling:** sanitize input and `MATCH` the trigram index; for **1–2 character** queries (below trigram's floor) fall back to a `LIKE`/prefix query on the raw `title` column, or require ≥3 chars in the search-as-you-type UI.
- **Ranking:** `bm25()` with column weights (title ≫ alt_titles ≫ authors/tags ≫ summary), optionally boosted app-side by exact-prefix match and popularity/recency. Ranking matters less here than in long-document search (the fields are short).
- **Behind the search interface** ([04](04-database-sqlite.md)) so the whole thing stays swappable.

## Portability

`trigram` needs SQLite ≥ 3.34 (2020); the `remove_diacritics` option for trigram needs ≥ 3.45. Python 3.14's bundled SQLite is newer, but to guarantee it on every deploy target we **pin SQLite via `pysqlite3-binary`** (already flagged in [04](04-database-sqlite.md)) and verify the compiled FTS5 options at startup.

## Escape hatches (unchanged from 04)

- If Latin **word-ranking** quality ever proves insufficient → upgrade to the **hybrid** (add a parallel `unicode61` index for Latin word/prefix search, query both, merge) — additive, no schema change.
- If we outgrow FTS entirely (typo tolerance, synonyms, heavy CJK analysis, very large scale) → swap the implementation for **Tantivy** or **Meilisearch** behind the same interface.

## Consequences

- **CJK + substring search work out of the box**, with **zero extra runtime dependencies** — the Komga wall is gone.
- "Contains" search-as-you-type matches user expectation for a title box.
- Slightly larger index + a 3-char floor — both immaterial at lychee's scale; the floor is covered by a small `LIKE` fallback.

## Alternatives considered

- **`unicode61` only** — rejected: no CJK, no substring (Komga's exact failure mode).
- **Hybrid `unicode61` + `trigram`** — deferred as the escape hatch: better Latin word-ranking, but two indexes + merge logic; not worth the complexity for short metadata fields up front.
- **ICU tokenizer** — rejected: needs SQLite compiled with ICU (build/portability burden) and its CJK segmentation is imperfect.
- **External engine (Tantivy / Meilisearch) now** — rejected: overkill; reserved as the scale escape hatch.
