# 07 — Library scan pipeline

**Status:** Implemented — manual/on-demand only, no watcher or scheduler.

## What this is

`backend/src/ingest/scanner.py`'s `scan_library()`, triggered only via
`POST /api/libraries/{id}/scan` / `/scan-all` — there's no filesystem
watcher and no periodic scheduler. Every scan walks the whole library root
every time; only the **per-book** `mtime`+`size` check
(`_reconcile_book`/`_same_mtime`, a flat 2-second tolerance) skips reopening
a container that hasn't changed. There's no series-folder-level
short-circuit gate.

## Phases

1. **Walk & resolve** (the hybrid model, [05](05-domain-model.md)):
   `resolve_books()` finds archive files and image-only directories,
   classifying grouping-vs-book folders. Container kind comes from a fixed
   extension map (`.cbz`/`.zip`), not content-sniffing — no `python-magic`
   dependency.
2. **Filename parsing** ([06](06-filename-parser.md)): `parse()` runs over
   path segments + filename; `order_chapters()` sorts by
   `(volume, number_sort)` and assigns the next whole integer to any
   chapter still missing a `number_sort` (a base-less special).
3. **Reconcile:** for a new path, first try **restore** — match a
   soft-deleted `Book` by `(file_size, partial_hash)`
   (`xxh3_128` of first 64 KiB + last 64 KiB + size); if found, revive it at
   the new path and re-apply its snapshotted reading progress
   (`Book.restore_progress_json`, taken before soft-delete, matched back by
   chapter `number` on restore). Otherwise insert fresh. A path missing from
   disk gets soft-deleted (`deleted_at`) — **never hard-deleted**; hard
   delete only happens on an explicit user-triggered purge
   (`catalog/purge.py`, one chapter at a time, not a scheduled sweep).
4. **`lychee.info` application** ([20](20-lychee-info-metadata.md)): if
   present, parsed and applied — gated by a content hash
   (`Series.metadata_file_hash`) so unchanged files aren't re-applied every
   scan.
5. **Post-scan:** covers are warmed for the whole library
   (`library/service.py:_finish_scan_phases` → `warm_library_covers`); a
   gallery library additionally enqueues a dedicated `"thumbs"` task
   (`warm_gallery_item_thumbs`) with its own progress bar. Scan progress is
   reported over SSE via the generic task lifecycle events
   (`scan.started`/`.progress`/`.done`/`.failed`) — there's no per-entity
   "series added" / "book updated" event, just the task's overall percent.

## Gallery libraries: a separate two-level scan

Not covered by the phases above at all — gallery-kind libraries
(`_ingest_artist`/`_ingest_entry` in `scanner.py`) scan a two-level
`<Artist>/<Work>/<files>` layout: each work folder becomes its own Series,
credited to the artist (`SeriesCredit(role="artist")`), auto-grouped into a
`Collection` named after the artist.

## Identity: `partial_hash` is a restore hint, never the primary key

```
partial_hash = xxh3_128(first 64 KiB ‖ last 64 KiB ‖ file_size)
```

Fast, negligible real-world collision risk, used only to match a moved file
back to its soft-deleted row. A collision just misses a restore (falls back
to a clean insert) — it never corrupts identity, since the primary key is
always the surrogate nanoid.

## Concurrency

One global `ThreadPoolExecutor` worker (`tasks/queue.py`, see
[08](08-task-runner.md)) — every task of every kind (scan, download, sync,
thumbs, local-import) runs strictly one at a time in submission order.
There's no per-series serialization concept and no cross-series
parallelism; it's accidental global serialization from a single worker
thread, not an intentional per-series group scheme.

## Not built

- **No filesystem watcher, no periodic scheduler.** All scans are manual/
  on-demand via the API — confirmed intentional, not a gap (`notes/plan.md`:
  "auto-scheduler not planned").
- **No content-sniffing** (`python-magic`) — container kind is
  extension-based only.
- **No embedded-metadata reading** (ComicInfo.xml/EPUB OPF/PDF info) — see
  [14](14-metadata-mapping.md). `lychee.info` fills a similar role via a
  sibling file instead of an embedded one.
- **No explicit per-book error state** for a corrupt/unreadable archive — it
  logs a warning and is skipped during scan; nothing is persisted on the
  `Book` row to flag it.
- **No scheduled trash-retention sweep** of old soft-deleted rows, no
  auto-backup-before-bulk-delete.

## Why soft-delete + hash-restore over hard-delete or content-hash identity

Soft-delete plus `(file_size, partial_hash)` restore means reorganizing
files on disk (renames, moves between folders) never loses reading progress
or metadata — a hard-delete-on-missing policy would. Keeping the primary key
a surrogate id rather than a content hash (contrast LANraragi, which uses a
hash as the key) means a hash collision degrades to "missed a restore, did
a clean insert" instead of corrupting identity.
