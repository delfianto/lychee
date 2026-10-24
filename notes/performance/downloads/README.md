# Download concurrency benchmarks

These are offline synthetic integration benchmarks, not MangaDex/network speed claims.
The production container and database are never changed by the harness.

Run from the repository root:

```sh
just bench-downloads --engine sqlite --output /tmp/download-benchmark.json
just bench-downloads --engine turso --output /tmp/turso-benchmark.json
```

Each fresh run seeds 2,000 catalog entries and downloads three series with ten
chapters each, eight deterministic 640×960 grayscale noise pages per chapter.
Network responses are simulated with a 5ms latency, bounded by ten file requests.
AVIF conversion (16 workers), thumbnailing (8 workers), archive creation,
filesystem staging, SQLAlchemy sessions, FastAPI routes and JSON responses are real.
Encoder process startup is warmed before timing. Three API readers continuously
request the series grid, downloads, and libraries, with 20ms between requests.

The database pool matches production's 5+10 connections. Its timeout is shortened
from 30s to 0.3s to expose contention without spending minutes in the baseline.
SQLite uses WAL, foreign keys, synchronous=NORMAL and a 2s busy timeout. Compare
identical settings across runs. Results came from a shared 32-thread host with
other services running; repeated samples are indicative, not a controlled CPU
performance claim. API timings measure FastAPI's in-process HTTP transport,
without TLS, a network proxy, or a browser.

`baseline-*.json` use application commit `4f18066` before the connection fixes.
All three series operations fail under connection pressure, leaving unfinished
chapter rows. Completed-page throughput is therefore not a successful full-job
throughput measurement. Treat completion/error counts as acceptance criteria
before comparing latency and throughput.

## SQLite optimization stage

Waiting chapter workers now acquire admission before querying the database.
Progress averages are calculated from live counters instead of nested SQL reads;
phase persistence coalesces page counters within 250ms while stage boundaries and
terminal states flush immediately. Failed writes roll back before recording failure.
The regression suite also runs three series against a two-connection pool while
chapter capacity is held, asserting API reads remain available.

| Stage | Completed chapters per run | Median API p95 | Worst API request | Median background SQL |
| --- | --- | --- | --- | --- |
| Baseline | 27/30, 24/30, 28/30 | 26.1ms | 311.4ms | 1091 |
| Optimized SQLite | 30/30, 30/30, 30/30 | 17.6ms | 66.6ms | 591 |

All optimized runs finish their three operations successfully. The baseline
operations fail, so their shorter wall times must not be interpreted as higher
throughput. Optimized successful throughput is about 65 pages/second for this
synthetic workload. The accelerated timeout limits the baseline latency spikes;
production was waiting up to 30 seconds instead.

## Initial local Turso stage

`turso-initial-*.json` use pyturso 0.8.3, MVCC/BEGIN CONCURRENT and the same
workload, worker counts and pool limits. All runs complete 30/30 chapters and all
three operations, with no API errors. Median wall time is 3.723s (64.46 pages/s),
API p95 44.9ms, worst API request 82.1ms, and median background SQL 1149.
This stage still checks the native search dirty queue on every write commit,
including page progress writes that cannot affect searchable metadata.

The native driver is opt-in, not a production cutover. Conversion was also tested
on a private 1,671-series SQLite backup: all application table contents matched,
including 31,043 provider chapters, and a new process reopened the converted file
with all 1,671 series indexed, MVCC enabled and integrity check `ok`. Alembic's
native schema drift check reports no changes. No source library data is included
in this repository.

## Turso progress-write tuning

`turso-optimized-*.json` skip search queue checks for compiled writes to unrelated
tables, while retaining them for catalog writes, library cascades and unknown raw
SQL. Median background SQL falls from 1149 to 617 (46.3%). All chapters and
operations complete; every API response succeeds. Median wall time is 3.752s,
63.97 pages/s, API p95 45.4ms and worst request 77.4ms. This reduces database work
but does **not** demonstrate a throughput or p95 latency improvement.

Per-endpoint timings added here identify the series grid as the remaining Turso
hotspot: its median is about 40ms while the other two endpoints are around 8–9ms.
Aggregate timings remain directly comparable with previous runs; the workload
and request pacing are unchanged.

## Final grid query tuning and comparison

The series grid now selects its filtered, ordered candidate page before computing
display counts and progress. Filters and sort expressions that require aggregates
still run during candidate selection; display-only aggregates run for the bounded
page. Both engines use this query. Tests combine favorite/read-state filters,
keyset pagination, ties, rating/title/unread sorts and per-row chapter counts;
existing tests cover recently updated publication dates and gallery scoping.
The native search marker is also cleared after its own projection writes, avoiding
an unnecessary queue check on the next transaction using that pooled connection.
Fresh application startup, automatic migration/seeding and HTTP library/grid
requests were smoke-tested in separate processes with each real DATABASE_URL scheme.

`sqlite-final-*.json` and `turso-final-*.json` alternate engines across three rounds.
All successful stages complete all 30 chapters and three parent tasks with zero
API errors. The final code passes 412 tests on each engine; SQLite's full branch
coverage gate reports 89.91% (85% required). CI now checks native migrations and
runs the native suite too.

Medians except the worst request; SQL counts include search synchronization.

| Stage | Wall time (s) | Pages/s | API p95 (ms) | Worst request (ms) | Background SQL |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 3.380 | 63.91 | 26.1 | 311.4 | 1091 |
| sqlite-optimized | 3.679 | 65.24 | 17.6 | 66.6 | 591 |
| turso-initial | 3.723 | 64.46 | 44.9 | 82.1 | 1149 |
| turso-optimized | 3.752 | 63.97 | 45.4 | 77.4 | 617 |
| sqlite-final | 3.627 | 66.17 | 16.4 | 49.5 | 582 |
| turso-final | 3.766 | 63.73 | 21.2 | 56.5 | 612 |

Baseline wall time/throughput are from failed operations and are **not** a valid
successful-job speed comparison. Final Turso p95 is about 53% lower than its initial
integration; its throughput remains similar. Final SQLite is still ahead of Turso
on this workload, so changing engines is not presented as a performance win.
The important reliability change is eliminating connections held by waiting workers.
These short shared-host samples cannot establish small percentage differences in
media throughput; they do expose errors, pool saturation and large query costs.

Local staged commits: `11e243f` benchmark baseline, `e7fadda` SQLite connection fix,
`3b69042` native engine/conversion, `b118c0e` progress-write tuning, followed by the
candidate-page optimization in the commit containing these final samples.
No production cutover, image rebuild or version change is performed by this work.
