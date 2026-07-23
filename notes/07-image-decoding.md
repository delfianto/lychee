# Overview 7 — Image Decoding & Archives

Container formats, image formats, page extraction/ordering, thumbnails, and streaming.
Per-project detail: [komga](komga/README.md) · [kamiyomu](kamiyomu/README.md) · [mango](mango/README.md) · [lanraragi](lanraragi/README.md).

## Comparison

| Aspect | Komga | KamiYomu | Mango | LANraragi |
|---|---|---|---|---|
| ZIP/CBZ | Apache Commons Compress | `System.IO.Compression.ZipFile` | Crystal stdlib `Compress::Zip` | `Archive::Libarchive` |
| RAR/CBR | junrar (v4) + nightcompress (v5, native) | **not supported** | `archive.cr` (libarchive) | `Archive::Libarchive` |
| 7z / tar / others | **no 7z** | no | no | **yes** (7z/tar/lzma/xz/zst via libarchive) |
| PDF | PDFBox (render on demand) | export only (QuestPDF) | no | **libvips** via FFI (render pages) |
| EPUB | custom extractor (2/3, fixed-layout, KEPUB) | export only (minimal) | no | libarchive (it's a ZIP) |
| Loose-image folder | no (dirs = series) | no | **yes** (DirEntry) | no |
| Container type detect | **Apache Tika** (magic bytes, not ext) | extension | MIME from extension | extension (`is_archive`) |
| Image formats decoded | JPEG/PNG/GIF/WebP/TIFF/**JXL/HEIF/AVIF/JP2/JBIG2** (ImageIO + TwelveMonkeys + nightmonkeys) | JPEG/PNG/WebP | JPEG/PNG/WebP/APNG/AVIF/GIF/SVG/JXL (dimensions via `image_size.cr`) | PNG/JPG/GIF/BMP/WebP/AVIF/HEIF/JXL |
| Resize/thumbnail lib | Thumbnailator | none (served at original res) | `image_size.cr` resize | **libvips** (pref) / ImageMagick |
| Thumbnail sizes | 300 / 600 / 900 / 1200 (longest edge) | — | portrait w=200 / landscape h=300 | height 500 (q50, or q80 HQ) |
| Thumbnail storage | **SQLite BLOB** (or sidecar URL) | **LiteDB blob** | **SQLite BLOB** | **filesystem**, hash-prefixed dirs |
| Page ordering | natural sort of image entries | lexicographic, excludes `cover.*` | `compare_numerically` | natural sort + **cover/credit reordering** |
| On-the-fly resize | convert/resize (no upscale); PDF rendered per request (no cache) | none | none (ETag cache on raw) | optional resize→JPEG, cached (CHI FastMmap) |
| Page cache | — | — | ETag (SHA-1 of bytes) + `Cache-Control` | CHI FastMmap disk cache; CBW prefetch |
| Corrupt/encrypted | error codes (ERR_100x); encrypted/multivol/solid RAR → UNSUPPORTED | minimal (file-count check) | keeps as visible error entry | dies + logs + skips; no password UI |

## Patterns & divergences

- **Two archive strategies:** a **single library that reads everything** (LANraragi's `Archive::Libarchive` = libarchive covers ZIP/RAR/7z/tar/lzma/zst/EPUB) vs **per-format libraries** (Komga: Commons Compress + junrar + nightcompress + PDFBox + custom EPUB). libarchive is the least-code path to broad format support; per-format libs give finer control and better error taxonomy. **7z support only exists where libarchive is used** (LANraragi); Komga has none, Mango/KamiYomu none.
- **Detect container by content, not extension.** Komga uses **Apache Tika** to sniff MIME from bytes, so a mislabeled `.cbz` that's actually RAR still works. The others trust the extension. → use `python-magic`/`libmagic`.
- **Page ordering is always natural sort — but LANraragi adds smarts.** All four natural-sort page filenames. LANraragi additionally **reorders covers to the front** (regex for `cover` excluding `back/rear/…`) and **credits/`999*` to the end**, and filters macOS `__MACOSX`/`._*` junk. Worth copying — those junk files and misplaced covers are real.
- **PDF is render-on-demand.** Komga (PDFBox) and LANraragi (libvips) both rasterize PDF pages when requested. Komga notably does **not cache** rendered pages — an obvious win LANraragi captures with its CHI page cache. → cache rendered PDF pages.
- **Thumbnail storage is the clearest anti-pattern cluster.** Three of four (Komga, Mango, KamiYomu) store thumbnails as **DB BLOBs**, which bloats the database and blocks nginx/CDN offload; every analysis (including theirs) flags it. **LANraragi's filesystem layout is the good pattern:** `<thumbdir>/<id[:2]>/<id>.jpg` for covers and `<thumbdir>/<id[:2]>/<id>/<page>.jpg` for per-page, with a 2-char hash-prefix subdir to avoid huge flat directories.
- **Streaming vs buffering.** KamiYomu reads whole pages into a `MemoryStream` (memory-heavy for big pages); libarchive/zipfile allow streaming a single entry. Serve pages as streams. LANraragi's **CBW prefetch** (async-fetch the next 3 pages) is a nice latency trick for the reader.
- **Cover fallback.** Mango serves `get_thumbnail() || read_page(1)` so a cover always exists even before generation — cheap robustness.

## Recommendation for lychee (Python)

- **Containers:**
  - CBZ/ZIP → `zipfile` (stdlib, streaming).
  - CBR/RAR → `rarfile` (needs `unrar`/`unar`) or **`libarchive-c`**.
  - 7z/tar/… → `libarchive-c` (one dependency for broad coverage, LANraragi-style) or `py7zr`.
  - PDF → **`pymupdf`** (fast render) or `pypdf`; **cache rendered pages** (don't repeat Komga's no-cache).
  - EPUB → `ebooklib` (+ the OPF metadata path from [05](05-metadata-tagging.md)).
  - Loose-image folders → support them (Mango's DirEntry) as a container type.
  - **Detect by content** with `python-magic`, not extension (Komga/Tika).
- **Images:** **`pyvips`** (libvips — fast, low-memory, what LANraragi uses) as primary decode/resize; **Pillow** (+`pillow-heif`) as fallback/coverage for HEIF/AVIF; treat JXL as best-effort. Output thumbnails as WebP or JPEG.
- **Page ordering:** natural sort + LANraragi's **cover-to-front / credits-to-back reordering** + strip `__MACOSX`/`._*`.
- **Thumbnails:** **filesystem**, content-addressed, hash-prefixed dirs (LANraragi layout); store only the *path* (or derive it) in the DB. Generate a small set of sizes (e.g. 300 cover / 600 detail); regenerate lazily. Keep Mango's `thumbnail || first_page` fallback.
- **Streaming & cache:** stream a single archive entry to the response (no whole-archive buffering); set **ETag (content hash) + `Cache-Control`** on page/thumbnail responses (Mango); consider a disk page cache for expensive (PDF/resize) outputs (`diskcache`), and reader **prefetch** of the next N pages (LANraragi).
- **Robustness:** an explicit error taxonomy for unreadable/encrypted/multivolume archives (Komga's ERR_ codes) so bad files surface as visible "error" entries rather than failing a whole scan; no password prompts needed for v1.
- **Gaps to close vs the field:** add **7z** and **PDF/EPUB** (Mango/KamiYomu lack them), **cache PDF renders** (Komga lacks), and **keep thumbnails off the DB** (Komga/Mango/KamiYomu wart).
