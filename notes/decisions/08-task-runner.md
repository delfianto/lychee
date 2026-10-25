# 08 — In-process operations with bounded I/O and independent image workers

**Status:** Implemented; updated for the coordinated pipeline refactor.

## Ownership and lifetime

`backend/src/tasks/queue.py` runs operations on separate download and sync/scan
thread pools, each with a fixed coordination capacity of 10. These are internal
bounds, not user-adjustable whole-job limits. Persisted controls apply only to
resource stages: file fetching and shared scan/metadata I/O. A job does not keep
an I/O permit while waiting for conversion or thumbnails.

Settings → Libraries → I/O workers appears immediately before Image processing.
GET/PUT `/api/libraries/workers` exposes `downloadWorkers` and
`scanMetadataWorkers` (1–10), plus `conversionWorkers` and `thumbnailWorkers`
(1–64). One Save workers button persists all four limits in one transaction
before applying them. The adjacent Auto detect button refreshes CPU recommendations
and fills the image-worker inputs without saving or replacing I/O edits. The existing `task_queue_config` singleton retains
its `download_workers` / `sync_workers` columns so saved preferences survive this
refactor without a migration. Both default to 1 only when unsaved. The old
`parallelDownloads`, `parallelSyncs`, and image-processing endpoints remain
compatibility adapters;
the latter now controls scan/metadata I/O, never whole operation admission.
`tasks/config.py` serializes both settings paths, commits before applying live
limits, and restores them before startup recovers queued downloads.

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

- `downloadWorkers` bounds actual concurrent page HTTP requests globally. One
  chapter fetches at a time, using that entire budget (10 means up to 10 files
  within that chapter). Chapter rows are claimed only after fetch admission,
  preserving queued pause/resume. Its chapter-owned producer stages source files
  independently of conversion and releases fetch admission when the source is
  exhausted, allowing the next chapter to fetch while earlier chapters encode or
  generate thumbnails. At most 10 chapter pipelines retain staging globally;
  this internal bound is independent of the file setting. Initial download,
  resume, retry and startup recovery all use the same dispatcher.
- MangaDex results are consumed in completion order and staged immediately.
  Progress counts completed files rather than the highest page number. Only
  lightweight paths wait for an earlier page; conversion/archive entries retain
  reading order. HTTP buffers remain bounded by file concurrency. Live resizing
  changes active request submission; reductions drain running requests first.
- Waiting chapter workers do not query the database before admission. Planning
  releases its database connection before HTTP and child dispatch. Parent
  progress averages use a locked in-memory snapshot without nested database
  connections. Page writes coalesce within 250ms; stage completion and terminal
  status flush immediately. Fetch/CPU children are joined before staging cleanup.
  Generic task cancellation also retires its unclaimed queued chapter rows.
- `scanMetadataWorkers` bounds one global, cancellation-aware I/O limiter shared
  by filesystem discovery/inspection and provider metadata/chapter requests.
  Each fanout has fixed executor capacity and a live submission window; concurrent
  scans cannot multiply the configured budget. MangaDex API/list/account/taxonomy
  requests use this budget too. Nested calls reuse a permit only in the same
  thread; copied operation contexts do not transfer permits to child threads.
  Image worker limiters remain non-reentrant so multiple process submissions
  from one owner each consume their own permit.
- Repeated scans of the same library serialize indexing through its catalog
  commit, then release that identity lock before derivatives. Distinct libraries
  share I/O capacity without a whole-job tuning knob. Database reconciliation
  stays on its owner thread, outside I/O permits so SQLite writer waits cannot
  deadlock another scan's next file lookup. Background media coordinators and workers commit
  catalog changes/release read connections before slow source reads or CPU work,
  leaving the API's connection pool available during image processing.
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
