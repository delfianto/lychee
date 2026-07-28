# 08 — Task runner: in-process thread-pool queue

**Status:** Implemented — a much simpler design than originally planned; see
"What was originally planned" below.

## What this is

A plain, in-memory, non-persistent queue — `backend/src/tasks/queue.py`'s
`TaskQueue`, one `ThreadPoolExecutor(max_workers=1)` by default and nothing
overrides that, so **every task of every kind runs strictly one at a time**,
in submission order, process-wide. There is no SQLite-backed task table, no
dedup, no priority, no per-series grouping, and no scheduler.

```python
# tasks/queue.py
class TaskQueue:
    def __init__(self, *, max_workers: int = 1): ...
    def submit(self, kind: str, label: str, work: Work) -> None: ...
    def submit_task(self, kind: str, label: str, work: Work) -> TaskOut: ...
    def wait_idle(self, timeout: float = 30.0) -> None: ...
```

`Work = Callable[[Session, ProgressFn], dict | None]` — each job gets its
own DB session from a `sessionmaker` (`configure(session_factory)`,
overridden by tests), commits/rolls back itself, and reports progress via a
`lambda pct, detail: tracker.progress(task, pct, detail)` closure.

## Tracking & events

`TaskTracker` (`tasks/tracker.py`) holds an in-memory, bounded (`keep=50`,
FIFO-evicted) list of `TaskInfo` (`id, kind, label, status[running|done|
failed], progress 0-100, detail, result`) — **not a database table**. All
task history is lost on process restart. `GET /api/tasks` returns
`tracker.snapshot()` directly. `EventBroker` (`tasks/events.py`) fans
`<kind>.started`/`.progress`/`.done`/`.failed` out to SSE subscribers
(`GET /api/events`).

Task kinds in use, all free strings with no enum and no priority:
`scan`, `thumbs`, `download`, `localimport`, `sync`.

## Failure handling

On an exception, `TaskQueue._run` rolls back the session, logs
`task_failed`, and marks the task `failed` via `tracker.finish(error=...)` —
no retry, no backoff, no requeue; a failed task just sits as `failed` in the
(ephemeral) in-memory list until it ages out of the last-50 window.

**One domain-specific exception:** downloads are a real persisted table
(`DownloadTask`), and `bootstrap()`'s `reclaim_orphaned_downloads()` flips
any `downloading` rows back to `queued` on startup and re-kicks them via
`queue.submit("download", ...)`. This is bespoke crash-recovery for the
downloads domain specifically, driven by the download table's own rows —
not a generic task-queue feature.

## CPU-bound work

There's no generic CPU-offload dispatcher wired into the queue. AVIF page
encoding has its own narrowly-scoped `ProcessPoolExecutor`
(`media/encode_pool.py`, sized by `LYCHEE_ENCODE_WORKERS`, default 1 =
serial in-process) — unrelated to `TaskQueue`, and its own comment notes
"the task queue runs jobs serially, so there's never concurrent use" of that
pool anyway, since only one task runs at a time in the first place.

## No scheduler

No APScheduler dependency, no periodic ticker of any kind. All scans are
user-triggered via the API — confirmed intentional (`notes/plan.md`:
"auto-scheduler not planned"), not a gap.

## What was originally planned (didn't ship)

This ADR originally specified a persisted SQLite `task` table (own file,
`tasks.sqlite`), an atomic `BEGIN IMMEDIATE` claim query giving priority +
per-series serialization (`group_key NOT IN (running groups)`, so different
series would parallelize while same-series tasks serialized), retry with
exponential backoff, a lease/reaper for crash recovery, and an APScheduler
tick for periodic scans/trash cleanup. None of it was built — the simpler
`ThreadPoolExecutor` design above shipped instead, and single-worker
serialization turned out to be sufficient in practice (nothing has since
needed the concurrency a multi-worker/per-series-group scheme would enable).
Revisit this ADR properly if that stops being true rather than treating the
original design as a target still being worked toward.
