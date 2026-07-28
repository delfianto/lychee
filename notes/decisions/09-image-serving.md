# 09 — Image, thumbnail & page-serving pipeline

**Status:** Implemented for CBZ/ZIP/image-directory content — see "Not built"
for what the original scope included that didn't ship.

## Container abstraction

One `BookContainer` ABC (`backend/src/media/containers.py`) with exactly two
implementations — `ImageDirContainer` (directories, also serves
`avif_dir` downloads) and `ZipContainer` (CBZ/ZIP via stdlib `zipfile`, no
`rarfile`/`libarchive-c`/`py7zr`/`pymupdf`/`ebooklib`):

```python
class BookContainer(ABC):
    def page_count(self) -> int: ...
    def page_name(self, index: int) -> str: ...
    def read_page(self, index: int) -> bytes: ...
```

A synchronous byte-return, not a streamed/generator API. Container kind
comes from a fixed extension map at scan time (`Book.content_kind`), not
content-sniffing.

## Page ordering

A natural sort of media filenames (`natural_key()`), with covers/junk
excluded via `is_cover_file` (matches `cover`/`folder` stems). No
cover-to-front or credits-to-back reordering heuristic, and no macOS-junk
(`__MACOSX/`, `._*`) stripping.

## Encode: AVIF, content-adaptive

`backend/src/media/avif.py` — Pillow only (native AVIF via bundled libavif,
no `pyvips`, no `pillow-heif`). A cheap classifier (`classify()`, per-pixel
RGB spread + distinct-color density on a 64×64 downsample) picks one of
three presets before encoding:

| Content class | Preset |
|---|---|
| `LINE_ART` (grayscale/mono) | quality 63, no chroma subsampling |
| `COLOR_ART` | quality 80, 4:4:4 |
| `PHOTO` | quality 60, 4:2:0 |

`ENCODE_SPEED = 2`. This content-adaptive classify-then-encode design isn't
just a detail — it's the reason quality holds up across both flat-color
manga pages and photographic gallery content without a single fixed preset
being wrong for one or the other.

## Thumbnails

`backend/src/media/thumbnails.py` — `ThumbnailStore`, two variants (`cover`
320px, `detail` 640px longest edge), sharded content-addressed filesystem
path `<root>/<id[:2]>/<id>.<variant>.avif`, atomic write (temp file +
`os.replace`), idempotent unless `overwrite=True`.

## Covers: a separate mechanism from thumbnails

`backend/src/catalog/media.py` maintains a canonical on-disk `Cover.avif`
beside a series' books for managed (download/import) libraries, or reads a
`cover.*`/`folder.*` convention for scanned libraries. When no cover exists
on disk, the fallback chain differs by kind: gallery → first local page;
manga/comic → provider HTTP `cover_source` (downloaded once and cached) →
first local page. `Series.cover_source` is a plain nullable URL string, not
a `generated|sidecar|user` enum. On a thumbnail-store miss, `get_cover`
materializes both variants from the canonical/provider source on the spot,
so a cover always renders even before a scan has warmed it — the same
lazy-generate-on-miss pattern covers gallery item thumbnails.

## Page serving

`GET /api/chapters/{chapter_id}/pages/{n}` (`?w=<width>` for on-demand
resize) → `media.get_page`. `ETag` is a sha1 hash of the **actual served
bytes**, computed fresh each response (`_etag`) — not a composite of
`partial_hash` + index + transform params. `Cache-Control: public,
max-age=86400`; 304 on a matching `If-None-Match`.

On-the-fly resize (`?w=`) goes through `RenderCache`
(`backend/src/media/render_cache.py`): clamped 100-3000px, downscale-only
(Lanczos), re-encoded as AVIF, disk-cached keyed
`<root>/<book_id[:2]>/<book_id>-<index>-<width>.avif`. **No eviction, no
size cap** — it was originally scoped as `diskcache`-backed and
size-capped/evictable; the shipped version grows unbounded on disk as plain
files.

## Caches

1. **Page-list** — `functools.lru_cache(maxsize=512)` keyed on `(path,
   mtime)`, `ImageDirContainer` only (`ZipContainer` re-sorts its namelist
   on open — cheap enough not to need caching).
2. **Thumbnail store** — filesystem, permanent, sharded, as above.
3. **Render cache** — filesystem, unbounded, as above.

All three are rebuildable — safe to clear at any time.

## Gallery video posters

`backend/src/media/video.py` (`extract_poster_png`, `ffmpeg`-based) — poster
thumbnails for gallery video items (MP4/M4V/WEBM), entirely outside the
original scope of this ADR, gallery-specific.

## Errors

A corrupt CBZ raises `BadRequestError` (caught `zipfile.BadZipFile`); an
unreadable book during scan is skipped with a logged warning — there's no
persisted error-state column on `Book` at all, no Komga-style `ERR_`
taxonomy.

## Not built

- **RAR/7z/PDF/EPUB support** — not planned; CBZ + image directories cover
  the common case.
- **Cover-to-front / credits-to-back page reordering**, macOS-junk stripping.
- **Prefetch** — neither the backend nor the reader (`frontend/src/views/
  ReaderView.vue`) prefetches upcoming pages.
- **Render-cache eviction/size cap** (`diskcache` was the original plan).
- **Per-page reader thumbnails** (grid/strip view) — confirmed still open in
  `notes/plan.md`.

## Why AVIF over WebP, Pillow over pyvips

AVIF gives materially better compression than WebP at comparable quality,
which matters more here than encode speed since thumbnails/pages are
generated once and served many times. Pillow's native AVIF support (via
bundled libavif) covered decode/encode/resize without adding `pyvips` as a
second image-processing dependency — the content-adaptive presets do the
work `pyvips`'s speed advantage would have targeted anyway.
