# 18 — Title & name variants (multilingual titles)

**Status:** ✅ Accepted (refines [05](05-domain-model.md))

## Context

A manga/manhwa/manhua work has several **equally valid** title forms:
- **native** — the original script (Japanese 進撃の巨人, Chinese, Korean),
- **romanized** — romaji / pinyin / romaja (*Shingeki no Kyojin*),
- **English** — the translated title (*Attack on Titan*),

plus **synonyms**, abbreviations, and other-language translations. [05](05-domain-model.md) sketched a single `name` + vague "alt titles"; search ([17](17-search-fts.md)) needs *all* forms; and the MangaDex provider ([13](13-metadata-providers.md)/[14](14-metadata-mapping.md)) already hands them to us as `altTitles[]`. This ADR fixes how titles are stored.

## Decision

Store titles as a **language-tagged one-to-many** table — the MangaDex model (`title` + `altTitles[]`), which is strictly more flexible than AniList's fixed `romaji/english/native` trio.

```
series_title(
  id, series_id → series,
  language,        -- BCP-47 incl. romanization: ja, ja-ro, zh-Hans, zh-ro (pinyin),
                   --   ko, ko-ro, en, es, ...   (the "-ro" suffix = a romanization, MangaDex's convention)
  title,           -- the string
  is_primary BOOL, -- exactly one per series = the canonical entry
  source,          -- provenance: manual | comicinfo | epub | mangadex | filename
  UNIQUE(series_id, language, title))
```

On `series` (denormalized for the hot list path, recomputed when titles or the preference change):
- **`display_title`** — the resolved title to show (this is what [05](05-domain-model.md)'s `series.name` becomes).
- **`sort_name`** — the normalized sort key ([05](05-domain-model.md)).

**Native / romanized / English are just language codes — not special columns.** So manhwa (`ko` / `ko-ro`), manhua (`zh` / `zh-ro` pinyin), and manga (`ja` / `ja-ro`) all work identically, and multiple synonyms or translations per language are allowed. A UI that wants to show the three "roles" simply queries by the relevant codes. (We follow MangaDex's `*-ro` tag for romanizations so provider data maps 1:1; BCP-47 `-Latn` is an equivalent if we ever prefer strict standards — the code is treated as an opaque tag.)

**Display resolution** (which title to show): the entry whose `language` matches the **preferred title language** setting → else the romanized (`*-ro`) → else English (`en`) → else `is_primary` → else any. v1 has one **global** `preferred_title_language` setting (single-user, [12](12-auth-users.md)); it becomes per-user when auth lands (resolved per-request or per-user cache). The `is_primary` choice is a **lockable** field ([14](14-metadata-mapping.md)) so a manual pick survives provider re-sync.

**Population & merge** ([14](14-metadata-mapping.md)): every source contributes titles as a **union** into `series_title` — MangaDex `altTitles[]` map 1:1 (each is already `{lang: string}`); ComicInfo `Series` (+ `LocalizedSeries`); EPUB `dc:title` (+ alternate-script title); the folder name enters as a `source=filename` title. De-duplicated on `(series_id, language, title)`.

**Search** ([17](17-search-fts.md)): the FTS `alt_titles` column is the concatenation of **all** `series_title.title` values, so a series is findable by *any* of its names — exactly the point 17 relies on (trigram can't transliterate, so findability comes from indexing every known form).

**Sort** ([05](05-domain-model.md)): `sort_name` stays on `series`, defaulting to the romanized or English title (ASCII-sortable), natsort-normalized; user-overridable + lockable.

**Scope:** this is for **series/work** titles. Per-book *chapter* titles stay a single `book.title` ([05](05-domain-model.md)) — they're single-form and don't need this treatment.

## Consequences

- Faithful to MangaDex; handles every CJK origin + synonyms + extra translations with one uniform mechanism.
- Drives per-language **display** and all-name **search** from a single source of truth.
- Denormalized `display_title` / `sort_name` keep list rendering join-free at scale.

## Alternatives considered

- **Fixed columns `title_native / title_romaji / title_english`** (AniList-style) — rejected as *storage*: too rigid (one romanization only, no synonyms, Japanese-centric role names). AniList itself spills over into a `synonyms[]` list for exactly this reason; we keep those three as ordinary language codes in the flexible table.
- **Single `title` string** — rejected: loses language semantics and per-language display.
- **A JSON `{lang: title}` map on `series`** — rejected: not relationally searchable/indexable; the child table joins and feeds FTS cleanly.
