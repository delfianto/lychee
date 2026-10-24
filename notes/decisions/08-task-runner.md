# 08 — In-process operations with bounded I/O and independent image workers

**Status:** Implemented; updated for the coordinated pipeline refactor.

## Ownership and lifetime

`backend/src/tasks/queue.py` runs operations on separate download and sync/scan
thread pools. The executors have a fixed capacity of 10; cancellation-aware live
limiters enforce each configured 1–10 operation limit without replacing executors
or leaving old pools draining outside the new limit. The independent download
and sync limits persist in the singleton `task_queue_config` row. Both default
to 1 only when no preference has been saved. `tasks/config.py` serializes settings
saves, commits before applying live limits, and restores them before startup
recovers queued downloads. Changing one limit preserves the other. The existing
settings endpoints keep their response shapes.

Every operation owns a `tasks/context.py` context: task ID, cancellation
checkpoint, phase reporter, pause checks, and finalizers. `tasks/concurrency.py`
copies that context into bounded child I/O workers. It stops submission and joins
children on cancellation or failure, before the operation or its staging directory
can finish. ORM sessions are never shared between worker threads.

A library scan owns inspection, indexing, matching, covers, and gallery thumbnails.
Catalog changes are committed before derivative generation so content becomes
available early, but the operation stays active until its derivatives finish.
There is no detached post-scan thumbnail task. A download operation owns all its
chapter workers; resume and retry use the same fanout as initial downloads.

## Progress and cancellation

`TaskTracker` is an in-memory registry, with `queued`, `running`, `cancelling`,
`cancelled`, `done`, and `failed` states. It retains active operations and bounded
completed history, publishes SSE lifecycle events, and records independent
`phases` counters (`completed` / `total`). `GET /api/tasks` supplies a snapshot
for initial connection and reconnect. The stream sends idle heartbeats every
15 seconds. The UI seeds accepted operations from action responses immediately,
loads a snapshot without waiting for SSE to open, and reconciles missed terminal
events on reconnect or return to a visible tab. `POST /api/tasks/{id}/cancel` requests
cancellation of the entire operation. The UI keeps cancelling work visible until
its child workers stop.

The existing sync job log links to the owning task and exposes its phase counters.
Cancelling a scan/account job cancels that owner; cancel-all also reaches queued
operations. Individual chapter-check jobs can still be cancelled independently.
Download rows persist their own phase counters in `phases_json`, including
thumbnail work, and become done only after that work returns. A retry after
publication reuses the existing chapter rather than downloading it again.

Cancellation is cooperative: checkpoints run during file discovery, inspection,
page fetch callbacks, conversion, and thumbnail generation. Queued process work
is cancelled; already-running native image encodes are joined before the owner
finishes. In-flight HTTP requests remain bounded by their request timeout. Video
poster extraction polls the operation state and kills/reaps ffmpeg on cancellation.

## Resource limits

- Download operation and chapter limits use `parallelDownloads`. A separate global
  file-request limiter of the same size bounds actual MangaDex file requests
  across chapter workers. A chapter-owned producer stages downloaded source files
  to disk independently of conversion; the queue holds paths, not image bytes.
  HTTP response buffering remains bounded by file concurrency. Progress crosses
  an owner-thread mailbox, keeping ORM sessions on their original thread. The
  producer and CPU jobs are joined before staging cleanup. Chapter and file dispatchers recheck
  the live limit while waiting, so increasing it expands an active download.
  Reducing it stops new chapter claims until active chapters drain below the
  new limit; running chapters are not interrupted.
- Sync operation and provider-item limits use `parallelSyncs`; filesystem/container
  inspection uses bounded workers too. Database reconciliation stays on its owner
  thread, with short commits before CPU work.
- `media/encode_pool.py` owns separate conversion and thumbnail process pools.
  Settings → Libraries → Image processing persists independent 1–64 worker
  limits in `image_processing_config`, restored before startup download recovery.
  The legacy `LYCHEE_ENCODE_WORKERS` supplies initial defaults until saved.
  GET/PUT `/api/libraries/image-processing` exposes these budgets and CPU-based
  recommendations (32 CPU threads suggests 16 conversion / 4 thumbnail workers).
  Live resizing retains one limiter per stage across old and new executors;
  running jobs count until completion and reductions drain before admitting more.
  At 1, that stage runs in-process under its own limiter. Gallery items and covers
  use the thumbnail budget independently of download and sync concurrency.
- Every AVIF job uses one native encoder thread, with balanced `speed=6` effort.
  The old effort 2 and unrestricted codec threading made each image expensive
  and could oversubscribe the host when several worker processes ran together.
- Image artifact locks deduplicate concurrent generators. Unique temporary image
  files and atomic replacement protect publication; chapter CBZ staging remains
  under the library's reserved `temp/` directory.

## Persistence and scope

The operation queue, task history, and sync job log are not persistent. Download
rows are persisted; startup recovery requeues orphaned downloading rows. There is
no scheduler, priority queue, retry policy, or durable generic job table.

The originally proposed SQLite task database, leases, and APScheduler were never
implemented. Bounded in-process work remains the intended design.
