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
