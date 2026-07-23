# 07 — Library scan pipeline

**Status:** ✅ Accepted

## Context

The capstone that ties together the hybrid folder→entity resolver ([05](05-domain-model.md)), the filename parser ([06](06-filename-parser.md)), SQLite + no-page-table ([04](04-database-sqlite.md)), and the file-identity / soft-delete strategy ([../03-file-management-sync.md]). Goal: keep `Series → Book` consistent with disk **cheaply** (skip unchanged subtrees) and **safely** (never lose reading progress or metadata when files move/rename).

```
trigger ─▶ 1 walk+resolve ─▶ 2 diff ─▶ 3 analyze ─▶ 4 order ─▶ 5 reconcile ─▶ 6 post
          (hybrid resolver)  (cheap    (new/changed  (series-   (restore /     (thumbs,
                              gate)     only)         level)     soft-delete)   SSE)
```

## Decision

### Triggers — watcher **and** periodic (both)

- **Periodic full scan** per library (interval configurable; on startup; manual via API). The correctness backstop, and the only reliable option on **NFS/SMB** (Komga's documented reason for polling).
- **Optional filesystem watcher** (`watchfiles`) per library for low-latency pickup on local disks. Debounces event bursts and enqueues a **targeted scan scoped to the affected series folder**, not the whole library.
- Both funnel into one **idempotent** scan job (scope = whole library | one series subtree). This is LANraragi's Shinobu (watcher) + Minion (queue) split, adapted.

### Phases

0. **Trigger** → enqueue a scan job (full or targeted subtree).
1. **Walk & resolve** (hybrid model, [05](05-domain-model.md)): first folder level = **Series**; recurse each series folder — archive file → **Book**, image-only folder → **loose-image Book**, folders holding archives/sub-folders are **grouping** (feed volume parsing); a book file loose under the root → **one-shot** virtual series. Skip hidden / excluded-pattern / unsupported-extension entries. Collect per book: relative path, size, mtime, container kind, and the **path segments below the series folder** (for the parser).
2. **Diff (cheap gate → confirm):** a series folder whose signature is unchanged — `file_last_modified` with a **force-modified-time** recompute (`max(dir mtime, child mtimes)` for NFS/SMB) or a contents signature — **short-circuits the whole subtree** (Mango). Per book: `mtime + size` unchanged → skip; changed → compute `partial_hash` to confirm a *real* content change. Classify each as **unchanged / new / changed / missing**.
3. **Analyze** (new + changed only; enqueued, **serialized per series**): detect the container **by content** (`python-magic`), not extension; read **embedded metadata** (ComicInfo.xml / EPUB OPF / PDF info) → a patch; run the **parser** ([06](06-filename-parser.md)) over path-segments + filename with **series-name subtraction**; list image entries → `page_count` (**no page rows**, [04](04-database-sqlite.md)); compute `partial_hash`. **Precedence:** embedded metadata > parser, applied only to **unlocked** fields (`locked_fields`, [05](05-domain-model.md)).
4. **Order (series-level):** sort books by `(volume, number_sort)` with Mango's `ChapterSorter` as the tiebreak/fallback; assign decimal `number_sort` to **specials that lacked a base number** ([06](06-filename-parser.md) handoff); recompute `book_count`, choose the series cover, aggregate series metadata.
5. **Reconcile (transactional):**
   - **new** path → first try **restore**: match a **soft-deleted** book by `(file_size, partial_hash)`; if found, revive it at the new path, migrating **reading progress, metadata, tags, read-list membership** (Komga `tryRestore`); otherwise **insert**.
   - **missing** (in DB, not on disk) → **soft-delete** (`deleted_at`), never hard-delete.
   - **renamed series folder** (no content hash) → reconciled via its now-restored books; series metadata + collection membership restored by matching the stable, lock-respecting series title.
   - keep the **FTS5** index in sync on every upsert.
6. **Post:** enqueue **cover thumbnail** generation (async, lower priority); emit **SSE** events (scan progress; series/book added/updated/deleted) so the SPA updates live. **Trash retention** (purge soft-deleted rows older than N days) + an **auto-backup before bulk deletes** run as a separate scheduled job.

### Identity: `partial_hash` is an advisory restore hint, not the key

```
partial_hash = XXH3-128( first 64 KiB ‖ last 64 KiB ‖ file_size )
```

Fast, with negligible real-world collision risk. It is used **only** as a move/rename **restore hint** — a rare collision merely misses a restore (falls back to a clean insert), it never corrupts identity. The primary key stays the surrogate id ([05](05-domain-model.md)). (Contrast LANraragi's 512 KB SHA-1 used *as the key* — rejected in [04](04-database-sqlite.md) / [../00-overview.md].)

### Concurrency & transactions ([04](04-database-sqlite.md))

- Scans run as **task-queue jobs, serialized per series via a group id** (Komga) — two scans of one series can't interleave, while different series parallelize up to a worker cap.
- Writes are **batched per transaction**; SQLite **WAL + `busy_timeout`** absorb the single-writer constraint.
- Heavy per-book work (metadata read, thumbnails) are **separate lower-priority jobs**, so the reconciliation pass stays fast.

### Ingestion hardening ([../03-file-management-sync.md])

- Watcher-triggered adds **wait until the file is openable and size-stable** before hashing/importing (avoids partial-write races — LANraragi).
- A **corrupt / encrypted / unsupported** archive gives the book an explicit **error state** (Komga's `ERR_` taxonomy); the scan logs it and continues rather than failing the batch.

## Consequences

- Re-scans are cheap (unchanged subtrees short-circuit); large libraries rescan fast.
- Reorganizations are safe: soft-delete + `(size, partial_hash)` restore preserve progress/metadata/tags/read-lists.
- Correct on network shares (periodic + force-modified-time), low-latency on local disks (watcher).
- The UI stays live via SSE; the scan stays responsive by pushing heavy work to serialized, prioritized jobs.

## Follow-ups

- **Task runner** — decided in [08](08-task-runner.md): custom SQLite-backed queue + APScheduler, providing the priority + per-series group serialization this pipeline assumes.
- **Thumbnail + image + on-demand page-serving** pipeline (filesystem cache layout, streaming, ETag) → ADR 08.
- **Metadata field mapping & lock-merge rules** (full ComicInfo/OPF) → [14](14-metadata-mapping.md).

## Alternatives considered

- **Watcher-only** — rejected (misses NFS/SMB, fragile on bursts).
- **Periodic-only** (Komga, Mango) — good baseline; we add the watcher on top for local-disk latency.
- **Hard-delete on missing** — rejected; loses reading progress on reorg. Soft-delete + trash instead.
- **Content-hash as identity** (LANraragi) — rejected as the key; reused only as the advisory restore hint.
