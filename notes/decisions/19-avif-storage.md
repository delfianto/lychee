# 19 — AVIF as the served image format

**Status:** ✅ Accepted — amends [09](09-image-serving.md).

## Context

ADR 09 chose WebP thumbnails and served full pages as their original bytes. Since
then the target deployment is a **16-core machine where CPU is a non-constraint**,
and the operator explicitly wants the smallest possible on-disk footprint for
**downloaded** content. AV1 image coding (AVIF) beats WebP/JPEG/PNG on ratio at
equal quality, and — crucially — Pillow ≥11.3 ships **native AVIF** in its wheels
(bundled libavif), so there is *no system dependency* to install. The webapp is
the only client (ADR 15) and every modern engine decodes AVIF (Chrome 85+,
Firefox 93+, Safari 16.4+), so no fallback format is needed in v1.

## Decision

**Serve images as AVIF.** Encoder = Pillow's native AVIF; CPU being free, encode
at a slow `speed` (2) for the best ratio. Encoding is a pure function, fanned out
on a `ProcessPoolExecutor` by the ingest/download task runner.

### Content-aware presets (line art ≠ photo)

| Content class | Chroma / mode | quality | Used for |
|---|---|---|---|
| `LINE_ART`  | monochrome (mode `L`, 4:0:0) | 63 | manga/manhwa pages — screentones stay crisp, tiny files |
| `COLOR_ART` | 4:4:4                        | 80 | covers, official/illustrated art — no chroma bleed on ink/text |
| `PHOTO`     | 4:2:0                        | 60 | cosplay / photo galleries — subsampling invisible, ~30–40% smaller |

The class is supplied by the caller when the context is known (a manga page vs a
cover vs a cosplay set) and otherwise inferred by a cheap heuristic on a 64px
downsample: near-zero per-pixel RGB spread → `LINE_ART`; else high unique-color
density → `PHOTO`; else `COLOR_ART`.

### What gets rewritten vs preserved

- **Downloaded images → AVIF on ingest; the PNG/JPEG original is discarded.** The
  operator opted into this to avoid PNG/JPEG bloat.
- **Scanned local archives (the user's own files) are never rewritten.** Their
  original page bytes are still served (ADR 09 §5); only **AVIF thumbnails** and
  on-demand resized/transcoded derivatives are generated, cached on disk.
- **Thumbnails are AVIF** (this supersedes ADR 09's WebP): a content-addressed,
  sharded store `<root>/<id[:2]>/<id>.<cover|detail>.avif`, two sizes (~320 / ~640
  px longest edge), idempotent + atomic generation.

### Serving

`GET /api/chapters/{id}/pages/{n}` and `/api/series/{id}/cover` stream AVIF with an
`ETag` (content hash) + `Cache-Control`, answering `304` on `If-None-Match`
(unchanged from ADR 09 §5).

## Consequences

- Big storage win on downloaded libraries; grids/readers get uniformly small,
  fast-decoding images.
- Scanned originals stay untouched (safe, reversible), so the "don't mutate the
  user's files" guarantee from ADR 05/09 holds.
- One extra decode+encode per downloaded page — absorbed by the process pool.

## Backlog

- Optional `?fmt=jpeg` fallback endpoint *only if* a non-webapp client ever
  appears (ADR 15 keeps us webapp-only for now).
- Revisit `speed`/`quality` defaults after measuring real libraries.
