"""Offline attribution of DB-API, query, ORM, and concurrent-write costs.

Uses only disposable synthetic databases. No provider, media or production I/O.
Private native statement APIs are used only for a labeled diagnostic control.
"""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import io
import json
import platform
import pstats
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.models  # noqa: E402, F401
import turso  # noqa: E402
from sqlalchemy import event, insert  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from src.catalog.models import Book, Chapter, Library, ProviderChapter, Series  # noqa: E402
from src.catalog.repository import SeriesFilters, list_series  # noqa: E402
from src.catalog.search_index import (  # noqa: E402
    mark_turso_search,
    reset_turso_search,
    sync_turso_search,
)
from src.core.persistence.base_model import Base  # noqa: E402
from src.core.persistence.database import create_database_engine  # noqa: E402
from src.progress.models import ReadingProgress  # noqa: E402


def format_plan(rows):
    return [f"{row[0]}:{row[1]}:{row[2]} {row[3]}" for row in rows]


def measure(function, count: int) -> dict[str, Any]:
    for _ in range(3):
        function()
    samples = []
    cpu = time.process_time()
    for _ in range(count):
        start = time.perf_counter()
        function()
        samples.append((time.perf_counter() - start) * 1000)
    cpu = (time.process_time() - cpu) * 1000
    ordered = sorted(samples)
    return {
        "iterations": count,
        "mean_ms": round(sum(samples) / count, 6),
        "p50_ms": round(ordered[(count - 1) // 2], 6),
        "p95_ms": round(ordered[int((count - 1) * 0.95)], 6),
        "cpu_ms_per_call": round(cpu / count, 6),
    }


def seed(path: Path, catalog: int) -> dict[str, tuple[str, tuple]]:
    engine = create_database_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(Library),
            [{"id": "library", "name": "Synthetic", "path": "/synthetic", "kind": "manga"}],
        )
        connection.execute(
            insert(Series),
            [
                {
                    "id": f"s{i:011d}",
                    "library_id": "library",
                    "title": f"Synthetic {i:05d}",
                    "sort_title": f"synthetic {i:05d}",
                    "kind": "manga",
                    "provider": "mangadex",
                    "created_at": now,
                    "rating": float(i % 10),
                }
                for i in range(catalog)
            ],
        )
        connection.execute(
            insert(Book),
            [
                {
                    "id": f"b{i:011d}",
                    "series_id": f"s{i:011d}",
                    "library_id": "library",
                    "path_rel": f"{i}/",
                    "content_kind": "image_dir",
                    "page_count": 40,
                }
                for i in range(catalog)
            ],
        )
        connection.execute(
            insert(Chapter),
            [
                {
                    "id": f"c{i:010d}{j}",
                    "series_id": f"s{i:011d}",
                    "book_id": f"b{i:011d}",
                    "number": str(j),
                    "number_sort": float(j),
                    "page_count": 20,
                    "provider": "mangadex",
                    "provider_chapter_id": f"{i}-{j}",
                    "created_at": now,
                }
                for i in range(catalog)
                for j in range(2)
            ],
        )
        connection.execute(
            insert(ProviderChapter),
            [
                {
                    "series_id": f"s{i:011d}",
                    "provider": "mangadex",
                    "provider_chapter_id": f"{i}-{j}",
                    "number": str(j),
                    "number_sort": float(j),
                    "published_at": now,
                    "last_seen_at": now,
                }
                for i in range(catalog)
                for j in range(20)
            ],
        )
        connection.execute(
            insert(ReadingProgress),
            [
                {
                    "series_id": f"s{i:011d}",
                    "chapter_id": f"c{i:010d}0",
                    "current_page": 20,
                    "completed": True,
                }
                for i in range(0, catalog, 2)
            ],
        )
        connection.exec_driver_sql(
            "CREATE TABLE bench_counter (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO bench_counter VALUES (?,0)", [(i,) for i in range(10)]
        )
    captured = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture(_connection, _cursor, statement, parameters, _context, _many):
        captured.append((statement, parameters))

    queries = {}
    for sort in ("recentlyAdded", "recentlyUpdated", "unread"):
        captured.clear()
        with Session(engine) as session:
            rows, _ = list_series(session, SeriesFilters(kind="manga", sort=sort))
            assert len(rows) == 24
        queries[sort] = captured[0]
    event.remove(engine, "before_cursor_execute", capture)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)").all()
    engine.dispose()
    return queries


def connect(path: Path, mode: str):
    if mode.startswith("sqlite"):
        connection = sqlite3.connect(
            path, check_same_thread=False, cached_statements=0 if mode == "sqlite-no-cache" else 128
        )
        journal = "wal"
    else:
        connection = turso.connect(
            str(path), isolation_level="CONCURRENT" if mode == "turso-mvcc" else "DEFERRED"
        )
        journal = "mvcc" if mode == "turso-mvcc" else "wal"
    for pragma in (
        f"journal_mode={journal}",
        "foreign_keys=ON",
        "synchronous=NORMAL",
        "busy_timeout=10000",
    ):
        connection.execute("PRAGMA " + pragma).fetchall()
    return connection


def prepared_control(connection, sql, parameters, count):
    """Diagnostic only: bypass public cursor bookkeeping and reuse native SQL."""
    from turso.lib import Status, _step_once_with_io

    statement = connection._conn.prepare_single(sql)
    try:

        def run():
            statement.reset()
            if parameters:
                statement.bind(parameters)
            rows = []
            while _step_once_with_io(statement, None) == Status.Row:
                rows.append(tuple(statement.row()))
            return rows

        expected = connection.execute(sql, parameters).fetchall()
        assert run() == expected
        return measure(run, count)
    finally:
        statement.finalize()


def writes(path: Path, mode: str, workers: int, dwell_ms: float, iterations: int):
    barrier = threading.Barrier(workers)
    verifier = connect(path, mode)
    before = dict(verifier.execute("SELECT id,value FROM bench_counter").fetchall())
    verifier.close()

    def worker(index):
        connection = connect(path, mode)
        completed, errors = 0, []
        try:
            barrier.wait(timeout=15)
            start = time.perf_counter()
            for _ in range(iterations):
                try:
                    connection.execute(
                        "UPDATE bench_counter SET value=value+1 WHERE id=?", (index,)
                    )
                    if dwell_ms:
                        time.sleep(dwell_ms / 1000)
                    connection.commit()
                    completed += 1
                except Exception as error:
                    connection.rollback()
                    errors.append(f"{type(error).__name__}: {error}")
            return completed, errors, time.perf_counter() - start
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(worker, range(workers)))
    completed = sum(result[0] for result in results)
    elapsed = max(result[2] for result in results)
    errors = [error for result in results for error in result[1]]
    verifier = connect(path, mode)
    after = dict(verifier.execute("SELECT id,value FROM bench_counter").fetchall())
    verifier.close()
    assert all(after[index] - before[index] == result[0] for index, result in enumerate(results))
    return {
        "workers": workers,
        "dwell_ms": dwell_ms,
        "attempted": workers * iterations,
        "completed": completed,
        "errors": errors[:3],
        "error_count": len(errors),
        "wall_s": round(elapsed, 6),
        "transactions_per_s": round(completed / elapsed, 2),
        "committed_values_verified": True,
    }


def run(args):
    result = {
        "python": platform.python_version(),
        "pyturso": version("pyturso"),
        "sqlite": sqlite3.sqlite_version,
        "config": vars(args)
        | {
            "output": str(args.output),
            "temp_root": str(args.temp_root) if args.temp_root else None,
        },
        "modes": {},
    }
    with tempfile.TemporaryDirectory(
        prefix="lychee-db-attribution-", dir=args.temp_root
    ) as directory:
        root = Path(directory)
        source = root / "source.db"
        queries = seed(source, args.catalog)
        modes = ["sqlite", "sqlite-no-cache", "turso-wal", "turso-mvcc"]
        if args.reverse:
            modes.reverse()
        for mode in modes:
            path = root / (mode + ".db")
            shutil.copyfile(source, path)
            connection = connect(path, mode)
            try:
                metrics = {
                    "pragmas": {
                        name: connection.execute("PRAGMA " + name).fetchall()
                        for name in ("journal_mode", "synchronous", "foreign_keys")
                    },
                    "raw": {},
                    "plans": {},
                }
                cases = {
                    "select_one": ("SELECT 1", ()),
                    "primary_key": ("SELECT title FROM series WHERE id=?", ("s00000000001",)),
                    "narrow_page": ("SELECT id FROM series LIMIT 25", ()),
                    "wide_page": ("SELECT * FROM series LIMIT 25", ()),
                    "candidate_page": (
                        "SELECT id FROM series WHERE kind=? ORDER BY created_at DESC,id DESC LIMIT 25",
                        ("manga",),
                    ),
                    **queries,
                }
                for name, (sql, parameters) in cases.items():
                    count = (
                        args.iterations * 10
                        if name in {"select_one", "primary_key"}
                        else args.iterations
                    )

                    def execute(sql=sql, parameters=parameters, connection=connection):
                        return connection.execute(sql, parameters).fetchall()

                    rows = execute()
                    metrics["raw"][name] = measure(execute, count) | {
                        "rows": len(rows),
                        "digest": hashlib.sha256(
                            json.dumps(rows, default=str).encode()
                        ).hexdigest(),
                    }
                    if name in queries:
                        metrics["plans"][name] = format_plan(
                            connection.execute("EXPLAIN QUERY PLAN " + sql, parameters).fetchall()
                        )
                if mode.startswith("turso"):
                    metrics["prepared_control"] = {
                        name: prepared_control(connection, *cases[name], args.iterations)
                        for name in ("select_one", "recentlyAdded", "wide_page")
                    }
                profiler = cProfile.Profile()
                sql, parameters = queries["recentlyAdded"]
                profiler.enable()
                for _ in range(args.iterations):
                    connection.execute(sql, parameters).fetchall()
                profiler.disable()
                output = io.StringIO()
                pstats.Stats(profiler, stream=output).strip_dirs().sort_stats(
                    "cumulative"
                ).print_stats(18)
                metrics["profile_recentlyAdded"] = output.getvalue()
                if mode in {"sqlite", "turso-mvcc"}:
                    scheme = "sqlite+turso" if mode.startswith("turso") else "sqlite"
                    engine = create_database_engine(f"{scheme}:///{path}")
                    try:

                        def orm_grid(engine=engine):
                            with Session(engine) as session:
                                rows, _ = list_series(session, SeriesFilters(kind="manga"))
                                assert len(rows) == 24

                        metrics["orm_grid"] = measure(orm_grid, args.iterations)
                        if mode.startswith("turso"):
                            for name, function in [
                                ("after_cursor_execute", mark_turso_search),
                                ("commit", sync_turso_search),
                                ("rollback", reset_turso_search),
                            ]:
                                event.remove(engine, name, function)
                            metrics["orm_grid_without_hooks"] = measure(orm_grid, args.iterations)
                    finally:
                        engine.dispose()
                # Counterfactual indexes exist only in this disposable fixture.
                # All source values and query texts stay identical.
                connection.commit()
                for ddl in (
                    "CREATE INDEX bench_series_added ON series(kind,created_at DESC,id DESC)",
                    "CREATE INDEX bench_provider_published ON provider_chapter(series_id,provider,published_at)",
                    "CREATE INDEX bench_chapter_uploaded ON chapter(series_id,source_uploaded_at)",
                    "CREATE INDEX bench_chapter_created ON chapter(series_id,created_at)",
                ):
                    connection.execute(ddl).fetchall()
                connection.commit()
                metrics["with_candidate_indexes"] = {}
                metrics["plans_with_candidate_indexes"] = {}
                for name, (sql, parameters) in (
                    queries | {"candidate_page": cases["candidate_page"]}
                ).items():

                    def indexed_query(sql=sql, parameters=parameters, connection=connection):
                        return connection.execute(sql, parameters).fetchall()

                    rows = indexed_query()
                    assert (
                        hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest()
                        == metrics["raw"][name]["digest"]
                    )
                    metrics["with_candidate_indexes"][name] = measure(
                        indexed_query, args.iterations
                    )
                    metrics["plans_with_candidate_indexes"][name] = format_plan(
                        connection.execute("EXPLAIN QUERY PLAN " + sql, parameters).fetchall()
                    )
            finally:
                connection.close()
            if mode != "sqlite-no-cache":
                metrics["writers"] = [
                    writes(path, mode, workers, dwell, args.writes)
                    for workers in (1, 4, 10)
                    for dwell in (0, 2)
                ]
            result["modes"][mode] = metrics
            print(f"finished {mode}", flush=True)
    reference = result["modes"]["sqlite"]["raw"]
    for metrics in result["modes"].values():
        for name, data in metrics["raw"].items():
            assert data["digest"] == reference[name]["digest"], (name, "query contents differ")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=int, default=2000)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--writes", type=int, default=40)
    parser.add_argument(
        "--temp-root",
        type=Path,
        help="Filesystem for disposable databases; default is the OS temp directory",
    )
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
