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

The navbar badge counts concrete work via GET `/api/activity`, independently of
the grouped operations shown in its dropdown. `downloadChapters` counts persisted
queued/downloading chapter rows once, including encoding and thumbnails, regardless
of how many parent drain operations reference them. `syncJobs` counts outstanding
MangaDex series checks and gallery work folders. Gallery tasks publish `workUnits`
and `workUnitKind`; a folder remains outstanding through covers and its final item
thumbnail, then decrements once. Files/images within a folder and the parent library
scan are not extra jobs. Paused, successful, failed, and cancelled work is excluded;
cooperative cancellation stays counted until the workers stop. `otherJobs` covers
discovery/preparation and other operations without concrete child units yet.

Committed chapter-state changes and sync/folder updates publish lightweight
`activity.changed` invalidations over the shared SSE stream. The browser coalesces
these into count requests rather than loading full queues or polling. Reconnect,
tab focus, and opening the activity dropdown refresh authoritative snapshots.
Tasks absent from a snapshot are removed unless newer events arrived during the
request, and late progress cannot revive a terminal task. The sync log's history
cap prunes finished entries only; large active queues retain every job.

The existing sync job log links to the owning task and exposes its phase counters.
Cancelling a scan/account job cancels that owner; cancel-all also reaches queued
operations. Individual chapter-check jobs can still be cancelled independently.
Download rows persist their own phase counters in `phases_json`, including
thumbnail work, and become done only after that work returns. A retry after
publication reuses the existing chapter rather than downloading it again.

## Work ordering

Downloads and Sync display processing/cancelling work first, then queued, paused,
failed, cancelled, and completed entries. Each group uses case-insensitive natural
title/folder order; chapter labels use numeric ascending order, including decimals
(`2`, `9.5`, `10`). Named extras and oneshots follow numbered chapters. Stable ties
keep rows from changing places between progress updates. Both the API and settings
views apply this policy; a completion moves a row below unfinished work.

Download planning sorts the provider's chapter feed before applying a limit.
Chapter claims sort the persisted remote number numerically in SQL before timestamp
and ID ties, so bulk inserts sharing a timestamp cannot start with a random nanoid's
chapter. Resume/retry uses the same claim path, and paused chapters stay excluded.
The global chapter-capacity and fetch-admission limiters serve waiting requests
FIFO and remove cancelled waiters; they retain live resizing and independent CPU
stages. This provides fair admission between concurrent drains, not whole-series
serialization. Chapters already fetching/encoding are never preempted by new work.

Provider sync plans titles in natural ascending order, and filesystem scan discovery
does the same for artist/work folders. Parallel I/O and image stages still complete
in readiness order; display order does not constrain or serialize completion.

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

Downloads and Sync each expose an independent **Auto-clear completed** toggle,
off by default. Both save immediately to boolean columns on `task_queue_config`
and restore before startup download recovery. PATCH `/api/downloads/config` and
`/api/sync/config` accept `autoClearCompleted` independently of the compatibility
worker fields, so toggling cleanup cannot reset a worker budget. Enabling clears
existing successful entries; failures, cancellations, paused, and active entries
remain visible. Download cleanup deletes queue history only, after encoding and
thumbnails complete; Book/Chapter records and files remain intact. Sync/scan/import
cleanup runs in the job manager; scan/import owners retain their rows until the
whole operation's finalizer runs. The browser need not remain open. Generic task
history in the background activity modal retains its existing bounded policy.
Migration `c6a9f024e318` adds both preferences with false defaults and preserves
existing worker settings. Manually clearing completed entries keeps its existing
behavior (including failed/cancelled sync entries).

The originally proposed SQLite task database, leases, and APScheduler were never
implemented. Bounded in-process work remains the intended design.
