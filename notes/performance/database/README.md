# SQLite / local Turso performance attribution (2026-10-25)

The original integration benchmark demonstrated connection-pool starvation and
verified its fix. It did not isolate engine speed: AVIF and thumbnail work dominate
that short workload, and its temporary media/database live on tmpfs on this host.
A roughly 4% difference in a 3.7-second download job is not strong evidence of a
causal database throughput penalty. This study isolates the substantial read gap.

## Reproduce and scope

```sh
just bench-database --output /tmp/db-attribution.json
just bench-database --temp-root /srv/project/github/lychee --output /tmp/db-attribution-nvme.json
```

`backend/scripts/bench_database.py` creates disposable synthetic databases only:
2,000 manga, 4,000 local chapters, 40,000 provider chapter records, and 1,000 reading
progress records. It clones one checkpointed SQLite fixture into separate files
for cached SQLite, uncached SQLite, native Turso WAL, and native Turso MVCC. No
production DB, providers, media, or external requests are involved. FTS is omitted
to isolate ordinary grid queries; the previous integration benchmark covers real
search hooks and media processing.

`attribution-{1,2,3}.json` use `/tmp` (tmpfs); `attribution-nvme-{1,2,3}.json` use the
project's btrfs/NVMe filesystem, the same mount as production appdata. Each filesystem
has three independent fixture runs; round two reverses engine order. Each query
gets three warmups and 100 measured executions (1,000 for trivial SELECT/PK tests).
Measurements include execute **and all fetched rows**, avoiding the misleading
execute/fetch split between eager sqlite3 and lazy pyturso. All raw result digests
must match across engines and before/after candidate indexes. The harness captures
EXPLAIN QUERY PLAN, Python CPU profiles, process CPU time and wall time. Results are
warm-cache, single-client query measurements, not HTTP latencies or cold-disk tests.
The host still runs other services; small differences are not statistically proven.

Python 3.14.8, sqlite3 3.54.0, pyturso 0.8.3; all use foreign keys, synchronous NORMAL
and a 10s busy timeout. Installed pyturso 0.8.3 also matched PyPI's latest release at
investigation time. The raw WAL and MVCC controls use the same pyturso package and
public DB-API. WAL uses DEFERRED writes; MVCC uses CONCURRENT writes. Live application
settings and production data are unchanged.

## 1. Most of the read gap is native execution, especially MVCC mode

Medians of each NVMe run's query p50, in milliseconds. These are the actual primary
SQL statements captured from `list_series()` with the existing schema and page
size 24 (+ one cursor sentinel), not simplified substitute queries.

| Grid sort | SQLite WAL | Turso WAL | Turso MVCC |
| --- | ---: | ---: | ---: |
| Recently added | 0.451 | 1.152 | 3.399 |
| Recently updated | 4.478 | 25.980 | 109.980 |
| Unread | 1.668 | 6.134 | 36.787 |

Tmpfs produces the same ordering and similar values. CPU time is close to wall
time, consistent with CPU work rather than waiting on storage. All plans use the
expected foreign-key/identity indexes; the gap is not explained by one engine
missing all indexes. Both must sort the candidate set, and the generated SQL
contains repeated correlated subqueries for counts and publication timestamps.
Turso's MVCC path is disproportionately expensive on these repeated indexed reads.

A representative MVCC profile spends about 0.307s of 0.343s (89%) inside native
`PyTursoStatement.step`; about 0.029s (8%) is statement preparation. That locates
most cost past the Python wrapper. It does **not** identify the exact internal Rust
function: separating version lookup, B-tree traversal and VM dispatch would need a
native CPU profile. `perf` is not installed here. We should not claim the Python
profile proves a particular internal MVCC algorithm is responsible.

## 2. Driver overhead is real but secondary here

For `SELECT 1`, SQLite takes about 0.5µs, uncached SQLite 1.4µs and pyturso about
3.7µs. The installed pyturso cursor prepares/finalizes each statement and fetches
through Python; sqlite3 caches prepared statements and performs fetching in C.
SQLAlchemy's statement cache caches SQL compilation, not native prepared statements.

A diagnostic control reuses a native statement and bypasses public cursor
bookkeeping. It checks that every returned row matches the public API. Turso MVCC's
main grid drops only from about 3.40ms to 3.14ms; Turso WAL drops from 1.15ms to
0.81ms. Removing SQLite's own cache raises its query from 0.45ms to 0.53ms.
Caching can help, but cannot explain or fix the majority of this read gap.
The private native API control is an attribution probe, not a proposed production
adapter or safe statement-cache implementation.

Fetching 25 wide series rows without the nested aggregates is about 0.034ms in
SQLite and 0.042ms in Turso MVCC. Row conversion alone is also not the main cost.

## 3. Our SQLAlchemy integration adds very little of the gap

Full repository grid calls, including fresh Session/pool checkout, ORM hydration
and eager relationship queries, are about 1.75ms on SQLite versus 4.98ms on Turso
MVCC. Removing the native search event hooks gives about 4.94ms, within normal
sample variation. No FTS/index work executes in these read-only calls. The
integration is not inadvertently doing milliseconds of extra search maintenance.

## 4. Index/query shape can improve both, with tradeoffs

The harness experiments with four indexes **only in its temporary fixture**:

- `series(kind, created_at DESC, id DESC)`
- `provider_chapter(series_id, provider, published_at)`
- `chapter(series_id, source_uploaded_at)`
- `chapter(series_id, created_at)`

The candidate-page plan changes from scanning/sorting the matching catalog to
using a covering order index. Timestamp aggregates can use covering indexes too.
The resulting query p50 values, again milliseconds, are:

| Engine | Recently added | Recently updated | Unread |
| --- | ---: | ---: | ---: |
| SQLite | 0.149 | 1.445 | 1.452 |
| Turso WAL | 0.562 | 9.865 | 5.365 |
| Turso MVCC | 1.679 | 45.533 | 41.961 |

Both engines improve on the first two sorts. However, the combined index set
regresses Turso MVCC's unread sort from about 36.8ms to 42.0ms, despite identical
results. This rules out applying all four blindly. Query-plan selection matters.

Next optimization candidates are to test indexes individually across filters and
cursors, compute each timestamp/count aggregate once instead of repeating scalar
subqueries, and compare indexed MAX versus an ordered LIMIT 1 lookup. A cached
summary table is not justified before those simpler query changes are measured.
These are proposed follow-ups; no index migration or runtime query change is made
by this investigation.

## 5. MVCC wins when we actually create write contention

Each writer owns its connection and distinct counter row. The harness measures
40 UPDATE+commit attempts per worker, with 1/4/10 workers, and either no deliberate
delay or 2ms held inside each write transaction. It uses no outer writer lock and
no automatic retries. A fresh connection verifies per-row increments exactly match
reported successful commits; all runs completed with zero errors.

On NVMe, ten writers with the 2ms transaction hold complete 400 commits in roughly
1.010s on SQLite versus 0.084s on Turso MVCC: about **396 vs 4,736 commits/s**, a
12× advantage. Native Turso WAL behaves like SQLite in this forced-lock test;
only MVCC removes the serialization. With ten tiny writers and no hold, median
observed rates are about 3,111/s SQLite, 11,762/s Turso WAL, and 29,231/s Turso MVCC.
The latter short bursts are noisy and should not be treated as steady-state rates.

These controls isolate counter updates, exclude FTS and business side effects, use
NORMAL sync and make no crash-durability claim. The 2ms hold is an artificial
contention control, not a recommendation to leave media/network work in a write
transaction. It demonstrates that MVCC works, rather than proving our downloader
needs it. Same-row conflicts/retries remain outside this disjoint-row benchmark.

Our fixed downloader releases connections before admission/network waits and
coalesces progress writes. At the old benchmark's roughly 600 background SQL
statements over 3.7s, it has little opportunity to benefit from tens of thousands
of tiny write commits per second. Its expensive media work is outside these
short commits; the grid is read-heavy. This is the workload-based explanation for
Turso's write advantage not translating into a faster whole download job.

## Decision and validation

Keep SQLite as the default for the current read-heavy application. Retain local
Turso as an opt-in engine and a useful comparison target. Do not interpret this as
“Turso is always slower”: the same hardware demonstrates its concurrent-write win.
The next production optimization should target query/index shape on both engines,
with regression checks across all sorts, rather than speculative worker or pool
increases.

The new benchmark contains assertions for result identity and committed counters.
The backend format/lint/type/coverage gate and full Turso suite were rerun; 412
tests pass on each engine, with 89.91% coverage for the default gate. No API contract
or application database schema is changed by this study.

Primary references: [pyturso Python source](https://github.com/tursodatabase/turso/blob/main/bindings/python/turso/lib.py),
[Python SDK](https://docs.turso.tech/sdk/python/reference),
[MVCC transaction semantics](https://docs.turso.tech/tursodb/concurrent-writes),
[Turso 0.8's write-concurrency focus](https://turso.tech/blog/turso-0.8.0),
[workloads where concurrent writes help](https://turso.tech/blog/concurrent-writes-in-practice).
