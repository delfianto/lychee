# Overview 5 — Metadata & Tagging

Metadata model, embedded parsing, external scraping/matching, tags, and search.
Per-project detail: [komga](komga/README.md) · [kamiyomu](kamiyomu/README.md) · [mango](mango/README.md) · [lanraragi](lanraragi/README.md).

## Comparison

| Aspect | Komga | KamiYomu | Mango | LANraragi |
|---|---|---|---|---|
| Metadata store | `SERIES_METADATA` / `BOOK_METADATA` tables (+ author/tag/link child tables) | crawler-returned `Manga`/`Chapter` (LiteDB) | split: SQLite (tags, sort_title) + `info.json` (display names, covers) | archive Redis hash (`title`, `tags`, `summary`, `toc`) |
| Embedded parsing | **ComicInfo.xml, EPUB OPF, Mylar `series.json`, ISBN barcode (ZXing), local artwork** | **writes** ComicInfo.xml; parses none | none | ComicInfo plugin; many others |
| External scraping | **none** (embedded/sidecar only) | none (crawler is the source) | via JS **download** plugins (MangaDex etc.) — not enrichment | **plugin scrapers**: EH, nhentai, Hitomi, Pixiv, Fakku, Hentag (image lookup), MangaUpdates-style, … |
| Matching strategy | n/a (reads what's embedded) | crawler id | plugin returns metadata for what it downloads | by title / filename / **cover-image SHA-1 reverse lookup** (Hentag) / source URL |
| Manual edit + locking | **per-field `*Lock` flags**; providers skip locked fields | none | display name / sort title / tags via admin API | tag edits; tag-rewrite rules |
| Tag model | `*_TAG` / `*_GENRE` child tables; sharing labels | crawler `Tags[]` (no user tags) | `tags` table (titles only) | **namespaced comma-string** (`artist:`, `parody:`, `series:` …) + `INDEX_<tag>` sets |
| Tag rewriting | — | — | — | **tag rules** (remove/strip-ns/replace-ns/rename/map) applied before commit |
| Search | **Lucene** (n-gram, multilingual, faceted `SearchCondition` DSL) | LiteDB `Contains` on title | tag filter only (no FTS) | Redis SET intersection + `KEYS INDEX_*x*` wildcard (O(N)) + title ZSET |
| Sort keys | `titleSort`, `numberSort`, many facets | title | `sort_title`, 5 sort methods | title ZSET, tag-namespace value sorts |
| Content rating/filter | age rating + per-user restrictions + sharing labels | `IsFamilySafe` boolean | — | EH-style `female:`/`male:` tags |

## Patterns & divergences

- **ComicInfo.xml is the lingua franca.** Komga *reads* it (full field mapping: Series/Volume/Number/Writer/Penciller/Genre/AgeRating/LanguageISO/StoryArc→ReadList/GTIN→ISBN/Web…), KamiYomu *writes* it into every CBZ it builds, LANraragi has a ComicInfo metadata plugin. EPUB OPF is the ebook equivalent (Komga). → **parse ComicInfo.xml + EPUB OPF on import; write ComicInfo.xml on export.** This is the single highest-leverage interop feature.
- **The lock-flag pattern is essential for a server that both auto-imports and allows manual edits.** Komga gives every metadata field a `*Lock` boolean; providers emit *patches* that a merger applies only to **unlocked** fields, and locked fields even survive move/rename restore. Without this, a rescan clobbers the user's hand-corrections. (A single `locked_fields` JSON/relation is a less verbose encoding of the same idea.)
- **Two sources of metadata, two philosophies.** Komga is **embedded-only** (authoritative files: ComicInfo/OPF/Mylar) and deliberately does **no** internet scraping. LANraragi is **scraper-first** via a rich **plugin system** (each plugin implements `get_tags($info)` and returns `tags/title/summary`; matching by title, filename, source URL, or **cover-image hash reverse search**). KamiYomu gets everything from the crawler. → lychee should start embedded-only (predictable, offline) and add a **plugin scraper interface** later (AniList/MangaUpdates/MangaDex/ComicVine), always merging onto unlocked fields.
- **Namespaced tags are the best tag model seen.** LANraragi's `namespace:value` (`artist:`, `series:`, `character:`, `language:`, `source:`…) plus **tag-rewrite rules** (normalize/rename/strip namespaces before commit) is powerful and portable. Its weakness is *storage* (one comma-string field) and *search* (`KEYS` wildcard, O(N)). → keep the namespace model, store relationally.
- **Search is where the projects diverge most sharply.** Only Komga has real search — and it **tried SQLite FTS5 in 2021 and removed it 9 days later** in favor of Lucene, specifically because FTS5 lacked **n-gram tokenization for CJK** (Japanese/Chinese/Korean titles) and rich filtering. Mango has *no* text search (tag-click only); KamiYomu does `Contains`; LANraragi does set-intersection + `KEYS` wildcards that don't scale. → FTS5 is a fine *start* but has a known CJK ceiling.
- **Faceted filtering.** Komga's `SearchCondition` sealed hierarchy (composable AllOf/AnyOf over typed conditions: library, tag, author, read-status, age-rating, publisher, language, …) is worth emulating as a typed filter API even without Lucene behind it.

## Recommendation for lychee

- **Model:** relational `series_metadata` / `book_metadata` with child tables for authors (name+role), tags, links, alternate titles (Komga). Store tags as a proper **M2M with a `namespace` column** (LANraragi's semantics, relational storage), allowed on both Series and Book.
- **Embedded first:** implement **ComicInfo.xml** (full Komga field map) and **EPUB OPF** parsing on import; optionally Mylar `series.json` and ISBN barcode. **Write ComicInfo.xml on export** for round-trip interop.
- **Locking:** adopt per-field locks (a `locked_fields` set/relation) so auto-import never overwrites manual edits; preserve locks across move/rename restore.
- **Tag hygiene:** port LANraragi's **tag-rewrite rules** (rename, strip/replace namespace, map) applied before persisting scraped tags.
- **Search:** **SQLite FTS5** for phase 1 (title, tags, authors, summary), with a typed **faceted filter API** modeled on Komga's `SearchCondition`. Document the **CJK escape hatch** (Tantivy/Meilisearch with n-gram) and keep the search layer swappable behind an interface — this is a known wall, not a hypothetical.
- **Scrapers later:** a Python **metadata-provider plugin protocol** (`get_metadata(context) -> patch`), matching by title/filename/cover-hash/source-URL (LANraragi), running in the task queue, merging onto unlocked fields. Sources to target: AniList, MangaUpdates, MangaDex, ComicVine, Kitsu.
- **Content filtering:** age rating + per-user allow/exclude restrictions + sharing labels (Komga) from the start given multi-user is a day-one goal.
- **Avoid:** metadata split across DB + JSON sidecars (Mango); comma-string tags + `KEYS`/`Contains` search (LANraragi, Mango, KamiYomu).
