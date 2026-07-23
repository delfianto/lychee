# 08 — Task runner: custom SQLite-backed queue + scheduler

**Status:** ✅ Accepted

## Context

The scan pipeline ([07](07-scan-pipeline.md)) needs a **persisted** task queue with **priorities** and **per-series serialization**, and [02](02-backend-stack.md) left the runner open. We chose SQLite for zero-ops / single-container self-hosting ([04](04-database-sqlite.md)); adding a broker (Redis) just for a queue cuts against that. Broker-less Python queues are sparse (essentially Huey or custom), so — unlike the filename parser — a small custom queue is the tightest fit, not reinventing a solved wheel. Both comparable servers are broker-less: Komga (SQLite task table + thread pool) and KamiYomu (Hangfire on SQLite).

**Decision by review:** a custom SQLite-backed queue + a lightweight scheduler.

## Decision

### Storage
A `task` table in a **separate `tasks.sqlite`** file (Komga's split) so the high-churn queue writes don't contend with domain writes under WAL. (Single-file is acceptable; separate is the safer default.)

```
task(
  id            PK (surrogate),
  type          text,        -- scan_library | scan_series | analyze_book | generate_thumbnail | empty_trash | …
  payload_json  text,        -- {library_id, series_id, book_id, scope, …}
  priority      int,         -- higher = sooner
  group_key     text NULL,   -- tasks sharing a key are serialized, e.g. "series:<id>"
  dedup_key     text NULL,   -- coalesce duplicate enqueues (unique among pending)
  status        text,        -- pending | running | failed
  attempts      int,  max_attempts int,
  available_at  datetime,    -- delay / backoff gate
  lease_until   datetime NULL,
  created_at, started_at, finished_at, last_error
)
-- indexes: (status, available_at, priority DESC, created_at), (group_key), unique(dedup_key) WHERE status='pending'
```

### Enqueue (with coalescing)
Enqueue = an insert. If a **pending** task with the same `dedup_key` exists, skip (or raise priority) instead of stacking — critical with the watcher, so a burst of events on one series collapses to a single `scan_series` (dedup_key `scan_series:<id>`).

### Claim — the mechanism that gives priority + per-series serialization
A worker atomically claims the next runnable task under a write lock:

```sql
BEGIN IMMEDIATE;
UPDATE task SET status='running', started_at=:now, lease_until=:now+:lease
WHERE id = (
  SELECT id FROM task
  WHERE status='pending' AND available_at <= :now
    AND (group_key IS NULL
         OR group_key NOT IN (SELECT group_key FROM task
                              WHERE status='running' AND group_key IS NOT NULL))
  ORDER BY priority DESC, created_at ASC
  LIMIT 1)
RETURNING *;
COMMIT;
```

The `group_key NOT IN (running groups)` clause is Komga's trick: a grouped task is **not** claimed while its group is already running, so **different series parallelize while same-series tasks serialize** — without tying up a worker on a blocking lock. `BEGIN IMMEDIATE` prevents two workers double-claiming.

### Workers & concurrency
A small pool of worker coroutines runs **in the FastAPI process** (single-deployable), claiming tasks in a loop. I/O-bound steps (walk, reconcile, metadata read) run inline (async/threads); **CPU-bound steps (image decode/resize, PDF render) are dispatched to a `ProcessPoolExecutor`** to avoid blocking the event loop. Worker count is configurable. (A fully separate worker process is a drop-in future option if isolation is wanted.)

### Retries, backoff, crash recovery
- On failure: `attempts++`, `available_at = now + expbackoff(attempts)`, back to `pending`; after `max_attempts` → `failed` (kept for visibility).
- **Lease / reaper:** a task whose `lease_until` has passed while still `running` (worker crashed) is requeued. On startup, all `running` tasks are requeued. This is **at-least-once** execution → **tasks must be idempotent** (our scan/reconcile and thumbnail steps already are — a hard requirement, not a nicety).

### Scheduling (periodic)
A lightweight **APScheduler** `AsyncIOScheduler` runs a single **tick** (~every 60 s) that:
- enqueues `scan_library` for libraries whose `scan_interval` has elapsed since `last_scanned_at` (dynamic per-library schedule via "check what's due", not static cron), with dedup so it never stacks;
- enqueues `empty_trash` per the retention policy.
On startup it enqueues scans for scan-on-startup libraries. (A plain asyncio ticker is a valid dependency-free substitute; APScheduler is kept for robust interval/cron handling.)

### Priorities (initial scheme)
`user-triggered (manual scan / read-now analyze)` > `scan_library / scan_series` > `analyze_book` > `generate_thumbnail` > `empty_trash / maintenance`. Interactive work preempts bulk backfill.

### Observability
The `task` table **is** the dashboard: an admin API lists pending/running/failed and surfaces `last_error`; progress is pushed over SSE ([07](07-scan-pipeline.md)).

## Consequences

- Zero extra services — lychee stays a single container.
- **Native** priority + per-series serialization (the claim query), exactly what 07 assumed.
- Persisted → survives restarts; crash recovery via lease/requeue.
- We own ~a few hundred lines; the real risk is getting **claim atomicity, the lease/reaper, and dedup** right — so they get focused tests.
- Reinforces that all tasks must be **idempotent** (at-least-once).

## Alternatives considered

- **Huey (SQLite)** — off-the-shelf and broker-less, but runs a separate consumer, its SQLite backend is less battle-tested than Redis, and per-series serialization would be bolted on via a lock rather than native.
- **ARQ / Celery / Dramatiq** — mature, but all want **Redis/RabbitMQ**, adding a service that undercuts the zero-ops rationale.
- **In-process fibers, no persistence** (Mango) — lost on restart; rejected.

## Follow-ups

- Finalize the exact `type` catalogue + priority constants during implementation.
- Confirm `tasks.sqlite` (separate) vs a table in the main DB after measuring write contention.
