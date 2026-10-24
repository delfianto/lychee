# 19 — AVIF as the served image format

**Status:** Implemented — amends [09](09-image-serving.md)'s original WebP
choice.

## Why AVIF

The target deployment is a many-core machine, and the operator wants a compact
on-disk footprint with practical import and download throughput for
**downloaded** content. AVIF beats WebP/JPEG/PNG on compression ratio at
equal quality, and Pillow ≥11.3 ships native AVIF in its wheels (bundled
libavif) — no system dependency to install. The webapp is the only client
([15](15-api-surface.md)) and every modern engine decodes AVIF natively, so
no fallback format is served.

## Encoding

Pillow's native AVIF encoder uses balanced `speed=6` effort and `max_threads=1`.
The original effort 2 was disproportionately slow for full-size pages; allowing
native threads in every process also oversubscribed many-core hosts. Quality
values and chroma presets stay unchanged; encoder effort can change output bytes,
size, and fidelity. Existing images are not rewritten by this change.

A local synthetic 1600×2400 RGB noise benchmark at quality 63, one native thread,
took 33.8 seconds at speed 2 versus 1.36 seconds at speed 6. This measures one
input, not an expected speedup for every chapter. Pillow documents the speed and
thread controls in its [AVIF saving options](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#avif).

Pure image functions run in separate conversion and thumbnail process pools
(`media/encode_pool.py`), with independent persisted limits in Library settings.
Downloads spool source files while conversion runs, retaining ordered pages.
Cancellation joins active encodes before declaring the owning operation stopped.
See [ADR 08](08-task-runner.md).

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
- **Thumbnails are AVIF** — one 640px-wide derivative per image, shaped to the
  UI frame (square gallery tile or 2:3 cover), quality 75 / 4:4:4 and LANCZOS.
  Source proportions are preserved with a center crop; small sources are never
  enlarged. Versioned cache keys replace the old 320px/640px longest-edge policy
  and its forced photo preset for gallery artwork. See [ADR 09](09-image-serving.md).

## Consequences

- Large storage win on downloaded libraries; grids/readers get uniformly
  small, fast-decoding images.
- Scanned originals stay untouched — the "don't mutate the user's files"
  guarantee holds.
- One extra decode+encode per downloaded page, absorbed by the process pool.

## Not built

- No `?fmt=jpeg` fallback endpoint — moot while the webapp is the only
  client; would only matter if a non-webapp client ever appeared.
