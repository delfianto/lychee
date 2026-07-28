# 13 — Metadata providers & (optional) downloader

**Status:** Implemented — MangaDex only, no second provider.

## Provider interface

Two separate Protocols (`backend/src/downloads/provider.py`), not one
unified interface with a capability set:

```python
class Provider(Protocol):        # download-capable
    def list_chapters(provider_series_id, *, language) -> list[RemoteChapter]: ...
    def fetch_pages(chapter, *, data_saver, on_page) -> list[bytes]: ...

class MetadataProvider(Protocol):  # metadata-capable
    def search(title, *, limit) -> list[MangaMatch]: ...
    def get_metadata(provider_series_id, *, language) -> SeriesMetadata: ...
    def list_new_chapters(provider_series_id, *, known, language) -> list[RemoteChapter]: ...
    def list_tags(*, language) -> list[tuple[str, str]]: ...
```

A registry (`register_provider`/`get_provider`/`get_metadata_provider`).
**Only MangaDex is implemented** (`backend/src/providers/mangadex.py`) — no
AniList/MangaUpdates/ComicVine metadata-only provider exists, even as a
stub.

## Linking: plain columns, not a generic join table

No `external_link` table. Linkage is two columns directly on the entity:
`Series.provider`/`Series.provider_series_id`, and
`Chapter.provider`/`Chapter.provider_chapter_id`. `ProviderChapter` caches
the remote chapter index (so a matched series can show available chapters
before anything is downloaded) — `download_status` is joined at read time
from `Chapter`/`DownloadTask`, not stored on the cache row.

## Matching

Not confidence-scored. `_auto_match_one` (`backend/src/catalog/matching.py`)
does an exact normalized-title string match (strip non-alphanumerics,
lowercase) — binary yes/no, not a ranked 0-1 score. A non-match is simply
left unmatched; there's no "queue for manual confirm" persisted state — the
user later calls the manual match/set-match endpoints
(`match_candidates`/`set_match`) same as any unmatched series.

## Merge & refresh

Provider data merges through [14](14-metadata-mapping.md)'s lock check
(`apply_metadata`, skips any field in `series.locked_fields_json`). Cover
images are fetched via `Series.cover_source` (a raw provider URL), consumed
by the cover pipeline in [09](09-image-serving.md).

## Downloader

Writes AVIF-paged CBZs and creates `Book`/`Chapter` rows **directly** —
`_download_chapter` (`backend/src/downloads/downloader.py`) both writes the
file to disk *and* `session.add(Book(...))`/`session.add(Chapter(...))` in
the same function. It does **not** reuse the scan pipeline (the "separate
download→DB ingest path" that was the original design's rejected
alternative is exactly what shipped). No ComicInfo.xml is written into the
CBZ — only numbered `NNN.avif` pages; scanlation group is stored as
`Chapter.group_name`, not embedded XML. Output path is hardcoded:
`{Series}/{Vol.XX or "No Volume"}/{Ch.YY - Title}.cbz` — not a configurable
template (the only configurable filename template in the codebase is for
*parsing* on local import, [06](06-filename-parser.md), unrelated to
download output).

Idempotent: `plan_downloads` dedups by `Chapter.number`/
`provider_chapter_id` against what's already local or queued.

## Rate limiting & good-citizen guardrails

Real and matches the original design: `TokenBucket`
(`backend/src/providers/ratelimit.py`) sized 5 req/s general + 40/min on
`/at-home/server`, 429/`Retry-After` handling with exponential backoff on
5xx, a real `User-Agent`, and a mandatory MangaDex@Home usage `report()`
after every page fetch.

## Not built

- Any second provider (AniList/MangaUpdates/ComicVine metadata-only).
- A login-plugin pattern for providers needing auth beyond MangaDex's own.
- Per-library preferred-language / scanlation-group-selection policy.
- Configurable download output path templating.
