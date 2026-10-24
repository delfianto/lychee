"""Offline, disposable download/API contention benchmark with real AVIF/CBZ work.

uv run python scripts/bench_downloads.py --output result.json
Network latency is simulated; accelerated pool timeout avoids 30s baseline stalls.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import platform
import random
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def percentile(values, fraction):
    ordered = sorted(values)
    return round(ordered[int((len(ordered) - 1) * fraction)], 3) if ordered else 0


def run(args):
    import src.models  # noqa: F401
    from PIL import Image
    from sqlalchemy import event, select
    from sqlalchemy.orm import sessionmaker
    from src.core.config import settings

    settings.auto_bootstrap = False
    from fastapi.testclient import TestClient
    from src.catalog.models import Library, Series
    from src.catalog.search_index import create_search_index
    from src.core.persistence.base_model import Base
    from src.core.persistence.database import create_database_engine, get_db
    from src.downloads.deps import get_storage_root
    from src.downloads.models import DownloadTask
    from src.downloads.provider import RemoteChapter, register_provider
    from src.main import app
    from src.media import encode_pool
    from src.media.avif import ContentClass
    from src.seed import seed_all
    from src.tasks.concurrency import parallel_map
    from src.tasks.context import cooperative_wait
    from src.tasks.queue import queue
    from src.tasks.tracker import tracker

    ready = threading.Barrier(args.series)
    image = io.BytesIO()
    Image.frombytes(
        "L", (args.width, args.height), random.Random(7).randbytes(args.width * args.height)
    ).convert("RGB").save(image, "PNG")
    raw = image.getvalue()

    class OfflineProvider:
        id = "benchmark"

        def list_chapters(self, series_id, *, language="en"):
            ready.wait(timeout=10)
            return [
                RemoteChapter(f"{series_id}-{i}", str(i), 1, None, language)
                for i in range(args.chapters)
            ]

        def fetch_pages(self, *_a, **_kw):
            raise AssertionError("streaming path required")

        def iter_pages_to(self, chapter, directory, *, data_saver=False, on_page=None):
            def fetch(index):
                with queue.file_limit.slot():
                    cooperative_wait(args.network_ms / 1000)
                    return index

            if on_page:
                on_page(0, args.pages)
            for count, index in enumerate(
                parallel_map(
                    fetch, range(args.pages), workers=10, ordered=True, limit=queue.file_limit
                ),
                1,
            ):
                path = directory / f"{index:04d}.source"
                path.write_bytes(raw)
                if on_page:
                    on_page(count, args.pages)
                yield path

    with tempfile.TemporaryDirectory(prefix="lychee-benchmark-") as root:
        work = Path(root)
        scheme = "sqlite+turso" if args.engine == "turso" else "sqlite"
        engine = create_database_engine(
            f"{scheme}:///{work / 'bench.db'}",
            pool_size=5,
            max_overflow=10,
            pool_timeout=args.pool_timeout,
        )

        @event.listens_for(engine, "connect")
        def configure(connection, _record):
            connection.execute("PRAGMA busy_timeout=2000").fetchall()

        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            create_search_index(connection)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as session:
            seed_all(session)
            library = Library(name="Benchmark", path=str(work / "manga"), kind="manga")
            session.add(library)
            session.flush()
            session.add_all(
                [
                    Series(
                        library_id=library.id,
                        title=f"Catalog {i:05}",
                        sort_title=f"catalog {i:05}",
                        kind="manga",
                    )
                    for i in range(args.catalog)
                ]
            )
            targets = [
                Series(
                    library_id=library.id,
                    title=f"Download {i}",
                    sort_title=f"download {i}",
                    kind="manga",
                    provider="benchmark",
                    provider_series_id=str(i),
                )
                for i in range(args.series)
            ]
            session.add_all(targets)
            session.commit()
            ids = [series.id for series in targets]
        encode_pool.configure_workers(args.conversion, args.thumbnails)
        list(encode_pool.encode_pages([raw] * args.conversion))
        encode_pool.encode_thumbnail(raw, 640, ContentClass.PHOTO, 75)
        lock = threading.Lock()
        held = []
        active = 0
        peak = 0
        statements = Counter()

        @event.listens_for(engine, "checkout")
        def checkout(_connection, record, _proxy):
            nonlocal active, peak
            record.info["bench_since"] = time.monotonic()
            with lock:
                active += 1
                peak = max(peak, active)

        @event.listens_for(engine, "checkin")
        def checkin(_connection, record):
            nonlocal active
            with lock:
                active -= 1
                held.append(
                    (time.monotonic() - record.info.pop("bench_since", time.monotonic())) * 1000
                )

        @event.listens_for(engine, "before_cursor_execute")
        def statement(*_a):
            with lock:
                bucket = (
                    "background" if threading.current_thread().name.startswith("lychee-") else "api"
                )
                statements[bucket] += 1

        def database():
            with factory() as session:
                yield session

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_storage_root] = lambda: work / "storage"
        queue.configure(factory)
        queue.set_download_workers(10)
        queue.set_sync_workers(1)
        samples = []
        endpoint_samples = [[], [], []]
        codes = Counter()
        stopped = threading.Event()
        paths = ["/api/series?kind=manga&limit=24", "/api/downloads", "/api/libraries"]
        with TestClient(app, raise_server_exceptions=False) as client:
            register_provider(OfflineProvider())

            def probe(index):
                while not stopped.is_set():
                    start = time.monotonic()
                    response = client.get(paths[index])
                    with lock:
                        duration = (time.monotonic() - start) * 1000
                        samples.append(duration)
                        endpoint_samples[index].append(duration)
                        codes[response.status_code] += 1
                    stopped.wait(0.02)

            start = time.monotonic()
            with ThreadPoolExecutor(max_workers=args.series + 3) as callers:
                probes = [callers.submit(probe, index) for index in range(3)]
                requests = [
                    callers.submit(client.post, "/api/downloads", json={"seriesId": sid})
                    for sid in ids
                ]
                submitted = [request.result(timeout=15).status_code for request in requests]
                deadline = time.monotonic() + args.seconds
                while time.monotonic() < deadline:
                    tasks = [task for task in tracker.snapshot() if task.kind == "download"]
                    if len(tasks) == args.series and all(
                        task.status in {"done", "failed", "cancelled"} for task in tasks
                    ):
                        break
                    time.sleep(0.02)
                elapsed = time.monotonic() - start
                stopped.set()
                for probe_job in probes:
                    probe_job.result(timeout=5)
            for task in tracker.snapshot():
                if task.status in {"queued", "running", "cancelling"}:
                    tracker.cancel(task.id)
            queue.wait_idle(timeout=10)
            with factory() as session:
                statuses = Counter(session.scalars(select(DownloadTask.status)))
            result = {
                "python": platform.python_version(),
                "cpu_threads": os.process_cpu_count(),
                "config": vars(args) | {"output": str(args.output)},
                "submitted_http": submitted,
                "wall_s": round(elapsed, 3),
                "chapter_states": dict(statuses),
                "completed_pages_per_s": round(statuses["done"] * args.pages / elapsed, 2),
                "api_requests": len(samples),
                "api_http": dict(codes),
                "api_p50_ms": percentile(samples, 0.5),
                "api_p95_ms": percentile(samples, 0.95),
                "api_max_ms": round(max(samples, default=0), 3),
                "api_endpoints": {
                    path: {
                        "requests": len(values),
                        "p50_ms": percentile(values, 0.5),
                        "p95_ms": percentile(values, 0.95),
                        "max_ms": round(max(values, default=0), 3),
                    }
                    for path, values in zip(paths, endpoint_samples, strict=True)
                },
                "sql_statements": sum(statements.values()),
                "background_sql_statements": statements["background"],
                "api_sql_statements": statements["api"],
                "db_peak_connections": peak,
                "db_hold_p95_ms": percentile(held, 0.95),
                "tasks": [task.status for task in tracker.snapshot() if task.kind == "download"],
            }
        encode_pool.shutdown()
        app.dependency_overrides.clear()
        engine.dispose()
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name, value in [
        ("series", 3),
        ("chapters", 10),
        ("pages", 8),
        ("catalog", 2000),
        ("width", 640),
        ("height", 960),
        ("conversion", 16),
        ("thumbnails", 8),
    ]:
        parser.add_argument("--" + name, type=int, default=value)
    parser.add_argument("--engine", choices=("sqlite", "turso"), default="sqlite")
    parser.add_argument("--network-ms", type=float, default=5)
    parser.add_argument("--pool-timeout", type=float, default=0.3)
    parser.add_argument("--seconds", type=float, default=15)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
