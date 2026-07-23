# 13 — Metadata providers & (optional) downloader

**Status:** ✅ Accepted

## Context

Beyond embedded metadata (ComicInfo/OPF), lychee wants **external enrichment** and an **optional downloader**. The [MangaDex research](../mangadex-api/README.md) shows it's the natural first provider (free public API, taxonomy wire-compatible with [10](10-tagging-content-rating.md)). Flagged as a follow-up in [10](10-tagging-content-rating.md) / [05](../05-metadata-tagging.md). The patches produced here are merged by the rules in [14](14-metadata-mapping.md); work runs on the task queue ([08](08-task-runner.md)); downloads feed the scan ([07](07-scan-pipeline.md)).

## Decision

### Provider interface (native-Python plugin registry)
```
class MetadataProvider(Protocol):
    id: str                                      # "mangadex"
    capabilities: set[metadata | cover | download]
    def search(q: SeriesQuery) -> list[Match]    # candidates + confidence 0..1
    def fetch(external_id) -> MetadataPatch      # series/book fields, tags, cover ref
    # download-capable only:
    def list_chapters(external_id, lang) -> list[ChapterRef]
    def fetch_pages(chapter: ChapterRef) -> Iterator[PageBytes]   # rate-limited
```
A **registry** of providers; **MangaDex is the first built-in**. Extensible for AniList / MangaUpdates / ComicVine (metadata-only) later. Native Python protocol — **no embedded JS engine** (rejecting Mango/Duktape; per [00-overview](../00-overview.md)); a LANraragi-style plugin discovery model, done in-language.

### External-id mapping (the linchpin)
```
external_link(
  id, entity_type[series|book], entity_id,
  provider,            -- "mangadex"
  external_id,         -- manga / chapter uuid
  url, created_at,
  UNIQUE(provider, entity_type, entity_id),
  INDEX(provider, external_id))              -- reverse lookup / dedup
```
Enables **idempotent re-sync** (fetch by stored id, no re-matching) and **download dedup** (skip chapters already linked / on disk).

### Matching flow
1. `search()` → candidates ranked by **confidence** (title/altTitle similarity + year + language).
2. **High confidence → auto-link; low → queue for manual confirm** — never silently apply a weak match. A "match / relink" UI action lets the user pick; the chosen `external_id` is stored in `external_link`.
3. Linked → `fetch(external_id)` → `MetadataPatch`.

### Merge & refresh
Patches go through [14](14-metadata-mapping.md)'s merge (unlocked fields only, precedence-ordered); provider data never touches locked fields ([05](05-domain-model.md)). Cover images fetched → [09](09-image-serving.md) with `cover_source = provider` (safe from thumbnail regeneration). A `refresh_metadata` task re-fetches on demand/schedule.

### Downloader (optional, capability-gated, off by default)
- `download_chapter` / `download_series` tasks ([08](08-task-runner.md)), gated by a **per-provider rate limiter** (token bucket sized to the provider — MangaDex: 5 req/s global **and** 40/min on `/at-home/server`).
- **Output reuses the scan:** fetch pages → write a **CBZ + `ComicInfo.xml`** (populated from the provider metadata, **crediting the scanlation group**) into a **watched library folder** → the normal scan ([07](07-scan-pipeline.md)) ingests it. No separate ingest path.
- **Link reconciliation:** the downloader records an `external_link` keyed to the file path it wrote; the scan, on creating the book at that path, binds the link to the new `book.id`.
- **Idempotent:** skip chapters already in `external_link` or already on disk (KamiYomu's `File.Exists` check). Path templating (`{series}/{series} - c{chapter}.cbz`) configurable.

### ToS / good-citizen guardrails (baked in, not optional)
Real `User-Agent`; exponential **back-off on 429**; MangaDex@Home **report** each page fetch; **credit scanlation groups** (ComicInfo `<Notes>` + UI) and **honor takedown/removal requests**; **no monetization**; obey rate limits. These are hard requirements for any download-capable provider. Metadata-only is the default posture; downloading is opt-in.

## Consequences

- Clean provider extensibility; MangaDex ships first, others slot in behind the same interface.
- The downloader reuses the entire scan/ingest/thumbnail pipeline instead of duplicating it.
- `external_link` gives exact re-sync and download dedup.
- ToS compliance lives in one well-behaved, rate-limited client component.

## Follow-ups

- More providers (AniList / MangaUpdates / ComicVine — some metadata-only); a **login-plugin** pattern for providers needing auth (LANraragi's model).
- Per-library **preferred language** + **scanlation-group selection** policy (a chapter may exist from many groups/languages).
- Chapter-level `external_id` granularity for `book` re-sync.

## Alternatives considered

- **Embedded JS plugin engine** (Mango/Duktape) — rejected: native Python protocol is simpler and safer.
- **Crawler-first architecture** (KamiYomu) — rejected as the model; lychee is scan-first, the downloader is an optional *add-on that feeds the scanner*.
- **Separate download→DB ingest path** — rejected in favor of writing CBZ+ComicInfo into a library and reusing the scan.
