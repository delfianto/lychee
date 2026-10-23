# 08 — In-process operations with bounded I/O and shared image workers

**Status:** Implemented; updated for the coordinated pipeline refactor.

## Ownership and lifetime

`backend/src/tasks/queue.py` runs operations on separate download and sync/scan
thread pools. The executors have a fixed capacity of 10; cancellation-aware live
limiters enforce each configured 1–10 operation limit without replacing executors
or leaving old pools draining outside the new limit. These settings remain
in-memory and default to 1 after restart.

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
for initial connection and reconnect. `POST /api/tasks/{id}/cancel` requests
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
  across chapter workers. Pages are fetched concurrently and fed to conversion
  in source order, with bounded buffering.
- Sync operation and provider-item limits use `parallelSyncs`; filesystem/container
  inspection uses bounded workers too. Database reconciliation stays on its owner
  thread, with short commits before CPU work.
- Page encodes, canonical covers, and thumbnails share `media/encode_pool.py`'s
  process pool, sized by `LYCHEE_ENCODE_WORKERS`. At 1, a shared limiter serializes
  image work in-process. Gallery item and cover jobs fan out across this budget.
- Image artifact locks deduplicate concurrent generators. Unique temporary image
  files and atomic replacement protect publication; chapter CBZ staging remains
  under the library's reserved `temp/` directory.

## Persistence and scope

The operation queue, task history, and sync job log are not persistent. Download
rows are persisted; startup recovery requeues orphaned downloading rows. There is
no scheduler, priority queue, retry policy, or durable generic job table.

The originally proposed SQLite task database, leases, and APScheduler were never
implemented. Bounded in-process work remains the intended design.
