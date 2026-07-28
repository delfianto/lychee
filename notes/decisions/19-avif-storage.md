# 19 — AVIF as the served image format

**Status:** Implemented — amends [09](09-image-serving.md)'s original WebP
choice.

## Why AVIF

The target deployment is a many-core machine where CPU is not a constraint,
and the operator wants the smallest possible on-disk footprint for
**downloaded** content. AVIF beats WebP/JPEG/PNG on compression ratio at
equal quality, and Pillow ≥11.3 ships native AVIF in its wheels (bundled
libavif) — no system dependency to install. The webapp is the only client
([15](15-api-surface.md)) and every modern engine decodes AVIF natively, so
no fallback format is served.

## Encoding

Pillow's native AVIF encoder, `speed=2` (slow, best ratio — CPU being free).
A pure function, fanned out on a `ProcessPoolExecutor`
(`media/encode_pool.py`).

## Content-aware presets

| Content class | Chroma / mode | quality | Used for |
|---|---|---|---|
| `LINE_ART`  | monochrome (`L`, 4:0:0) | 63 | manga/manhwa pages — screentones stay crisp, tiny files |
| `COLOR_ART` | 4:4:4                   | 80 | covers, official/illustrated art — no chroma bleed on ink/text |
| `PHOTO`     | 4:2:0                   | 60 | cosplay/photo galleries — subsampling invisible, ~30-40% smaller |

The class is supplied by the caller when known, otherwise inferred by
`classify()` — a cheap heuristic on a 64px downsample: near-zero per-pixel
RGB spread → `LINE_ART`; else high unique-color density → `PHOTO`; else
`COLOR_ART`. (Full detail in [09](09-image-serving.md).)

## What gets rewritten vs. preserved

- **Downloaded images → AVIF on ingest; the original PNG/JPEG is discarded.**
- **Scanned local archives (the user's own files) are never rewritten.**
  Original page bytes are still served as-is; only AVIF thumbnails and
  on-demand resized derivatives are generated and cached separately.
- **Thumbnails are AVIF** — a content-addressed, sharded store
  (`<root>/<id[:2]>/<id>.<cover|detail>.avif`), two sizes (~320/~640 px),
  idempotent + atomic generation.

## Consequences

- Large storage win on downloaded libraries; grids/readers get uniformly
  small, fast-decoding images.
- Scanned originals stay untouched — the "don't mutate the user's files"
  guarantee holds.
- One extra decode+encode per downloaded page, absorbed by the process pool.

## Not built

- No `?fmt=jpeg` fallback endpoint — moot while the webapp is the only
  client; would only matter if a non-webapp client ever appeared.
