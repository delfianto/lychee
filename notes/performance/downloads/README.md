# Download concurrency benchmarks

These are offline synthetic integration benchmarks, not MangaDex/network speed claims.
The production container and database are never changed by the harness.

Run from `backend/`:

```sh
uv run python scripts/bench_downloads.py --output /tmp/download-benchmark.json
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
