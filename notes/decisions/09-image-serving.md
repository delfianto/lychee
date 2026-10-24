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

`backend/src/media/thumbnails.py` stores one fixed-resolution preview per image:
640×640 for gallery item tiles and 640×960 for 2:3 cover frames. `ImageOps.fit`
uses LANCZOS and preserves proportions while center-cropping exactly as the UI's
`object-cover` did. Small sources are not upscaled. Preview encoding uses AVIF
quality 75 with 4:4:4 chroma, independently of downloaded-page presets. There is
no `srcset`, size ladder, or generation of multiple sizes during scans.

Versioned cache filenames are `<root>/<id[:2]>/<id>.<cover-v2|gallery-v2>.avif`;
API image URLs include `?v=2` to bypass previously cached low-resolution images.
Successful publication removes that image's old `.cover.avif` / `.detail.avif`
derivatives. Originals and canonical `Cover.avif` files are never removed.
Existing previews upgrade on access or the next scan; no synchronous rebuild of
the whole library is required. `size=detail` remains an API compatibility alias
of the same cover preview, using one disk file.

On wide screens the gallery uses fluid columns near 240–300 CSS pixels rather
than stretching five tiles across the whole monitor. That keeps 640px previews
useful at 2x display density. The three sampled live sources encoded to 17–29 KB
per 640px square preview (quality 75, 4:4:4), roughly 220–370 MB for 12,985 items;
actual size depends on the library. Covers add one preview per series.

Concurrent generators share an artifact lock; unique temporary files and atomic
replacement protect publication. All preview generation uses the shared AVIF
process pool described in [ADR 08](08-task-runner.md).

Thumbnail location is configurable in **Settings → Libraries → Thumbnail storage**.
The `thumbnail_config` singleton persists an optional absolute path; unset uses
`STORAGE_PATH/thumbnails`. `media/storage.py` resolves that choice for both lazy
serving and background scan/download/import/provider jobs. The API
(`GET`/`PUT /api/libraries/thumbnail-storage`) checks that the folder can be
created and written before saving. Switching folders leaves existing thumbnails
in place; cache misses regenerate in the selected folder. Original media,
canonical covers, and the page-render cache keep their existing locations.

## Covers: a separate mechanism from thumbnails

`backend/src/catalog/media.py` maintains a canonical on-disk `Cover.avif`
beside a series' books for managed (download/import) libraries, or reads a
`cover.*`/`folder.*` convention for scanned libraries. When no cover exists
on disk, the fallback chain differs by kind: gallery → first local page;
manga/comic → provider HTTP `cover_source` (downloaded once and cached) →
first local page. `Series.cover_source` is a plain nullable URL string, not
a `generated|sidecar|user` enum. On a thumbnail-store miss, `get_cover`
materializes its single preview from the canonical/provider source on the spot,
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
