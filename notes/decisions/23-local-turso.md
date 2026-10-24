# 23 — Optional local Turso MVCC database

**Status:** Implemented as an opt-in local engine. SQLite remains the default.

## Motivation and driver

Download workers exhausted SQLAlchemy's 15-connection pool by opening sessions
before waiting for chapter admission. Fixing that lifetime error is necessary on
either engine; changing databases cannot substitute for it. The
[benchmark report](../performance/downloads/README.md) separates those changes.

`pyturso==0.8.3` runs the native local Turso engine, not libSQL or a remote cloud
service. `core/persistence/turso.py` adapts its DB-API to SQLAlchemy's SQLite SQL
compiler. `create_database_engine()` is shared by runtime, Alembic, tests and tools.
The adapter removes unsupported pysqlite UDF/thread options and applies MVCC before
SQLAlchemy's first schema probe. Foreign keys, 30s busy timeout and synchronous
NORMAL are enabled. Runtime uses BEGIN CONCURRENT; migrations use DEFERRED because
DDL requires exclusive transactions. No remote URL/token, sync or new service is
introduced.

## Search compatibility

Turso does not implement FTS5. The same `search_ids()` interface uses a native
Tantivy index with n-gram tokenization and title/alternative/credit weights 10/4/1.
Both engines retain the existing LIKE fallback below three characters. Rankings
need not be numerically identical across engines.

Native FTS cannot delete and insert the same index row from a single trigger.
Triggers instead queue affected series IDs; a SQLAlchemy pre-commit hook refreshes
the projection with top-level SQL within the same transaction. A connection-local
marker skips this check for compiled ORM/Core writes outside series, variants,
credits and libraries. Unknown raw writes/DDL conservatively retain it, and
rollback clears the marker. This prevents progress-only commits from querying
search tables. Searching also
flushes that queue so explicit ORM flushes are visible before commit. Reparented
credits/variants refresh both old and new owners; deletes remove stale rows.

In pyturso 0.8.3, bound FTS query parameters match rows but produce zero relevance
scores; adding a secondary sort also bypasses relevance ordering in this version.
The query orders by the score alias alone. SQLAlchemy's `literal_execute` string parameter safely renders the query
literal, including apostrophes; raw input is never concatenated into SQL. Tests
cover ranking with adversarial ID order and SQL punctuation. Native FTS requires
`experimental_features='index_method'`; that is scoped to the adapter.

## Conversion and rollback

Never change the engine URL while pointing at the existing live SQLite file.

1. Stop application writes for an actual cutover (the tool's SQLite backup itself
   is consistent, but writes after its snapshot are absent from the copy).
2. Run `just db-to-turso /path/lychee.db /path/lychee-turso.db`.
3. The tool opens the source read-only, backs it up into a private staging directory,
   upgrades the copy, replaces FTS5 with the native index, verifies counts and SHA256
   of every column in every ORM table, and checks database integrity.
4. It checkpoints **both** MVCC `-log` and SQLite-style `-wal`, then publishes a new
   mode-0600 file atomically without overwriting an existing destination.
5. Set `DATABASE_URL=sqlite+turso:////path/lychee-turso.db` and start the application.
   In the container, use its mounted path, e.g. `sqlite+turso:////data/lychee-turso.db`.

The original SQLite file is retained. Switching back restores that snapshot;
writes made only to Turso are not automatically copied back. An active Turso DB
may have a `-log` as well as `-wal`: never back it up by copying only its main file.
Quiesce writers and checkpoint successfully before taking a single-file backup.

## Validation and limits

`just be-check` covers the default SQLite path; `just be-turso` runs the same
backend suite with native Turso fixtures. Additional tests cover overlapping
independent writes, fresh/idempotent migrations, rollback-visible search, safe
conversion, reopen and original-file preservation. `just db-check` works with an
explicit DATABASE_URL for either engine. Benchmarks are offline and use temporary
databases/media; existing production deployments are not switched by this change.

MVCC allows disjoint writers, but writes to the same data can conflict. The engine
surfaces those errors to the existing transaction error handling; there is no
blanket retry of arbitrary service work, which could replay provider or filesystem
side effects. This opt-in engine does not claim every overlapping business action
is retry-safe. Its experimental native index and observed workload performance
are reasons to keep SQLite as the default pending deployment evaluation.

References: [Python SDK](https://docs.turso.tech/sdk/python/quickstart),
[MVCC/conflicts](https://docs.turso.tech/tursodb/concurrent-writes),
[native FTS](https://docs.turso.tech/sql-reference/functions/fts).
