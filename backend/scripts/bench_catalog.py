"""Compare complete catalog operations with a historical implementation.

Only disposable synthetic databases are used. Includes migration-sized indexes,
checkpoint/reopen controls, filters, continuation pages and result equivalence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import types
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.bench_database import measure, seed  # noqa: E402
from sqlalchemy import insert, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from src.catalog import repository  # noqa: E402
from src.catalog.models import Library, SeriesCredit  # noqa: E402
from src.core.persistence.base_model import Base  # noqa: E402
from src.core.persistence.database import create_database_engine  # noqa: E402
from src.progress.models import ProviderReadingProgress  # noqa: E402
from src.taxonomy.models import Tag, series_tag  # noqa: E402

INDEX_NAMES = {
    "ix_series_kind_added",
    "ix_series_kind_title",
    "ix_series_kind_rating",
    "ix_chapter_series_read",
    "ix_chapter_series_created",
    "ix_chapter_series_uploaded",
    "ix_provider_chapter_published",
    "ix_reading_progress_read",
}


def reference(revision):
    root = Path(__file__).resolve().parents[2]
    code = subprocess.check_output(
        ["git", "show", f"{revision}:backend/src/catalog/repository.py"],
        cwd=root,
        text=True,
    )
    module = types.ModuleType("lychee_catalog_reference")
    sys.modules[module.__name__] = module
    exec(compile(code, f"{revision}:catalog/repository.py", "exec"), module.__dict__)
    return module


def snapshot(result):
    rows, cursor = result
    return [
        (
            row.series.id,
            row.chapter_count,
            row.unread_count,
            row.last_read,
            row.content_updated_at.isoformat(),
            sorted(tag.id for tag in row.series.tags),
            sorted((credit.role, credit.name) for credit in row.series.credits),
        )
        for row in rows
    ], cursor


def enrich(path, catalog):
    engine = create_database_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(
            insert(Library),
            [{"id": "second", "name": "Second", "path": "/second", "kind": "mixed"}],
        )
        connection.execute(
            text(
                "UPDATE series SET favorite=CAST(substr(id,2) AS INTEGER)%3=0, library_id=CASE WHEN CAST(substr(id,2) AS INTEGER)%4=0 THEN 'second' ELSE 'library' END"
            )
        )
        connection.execute(
            text(
                "UPDATE series SET kind=CASE CAST(substr(id,2) AS INTEGER)%10 WHEN 0 THEN 'gallery' WHEN 1 THEN 'comic' ELSE 'manga' END, rating=CASE WHEN CAST(substr(id,2) AS INTEGER)%5=0 THEN NULL ELSE rating END"
            )
        )
        connection.execute(
            text(
                "UPDATE series SET created_at=datetime('2020-01-01','+'||(CAST(substr(id,2) AS INTEGER)%71)||' days')"
            )
        )
        connection.execute(
            text(
                "UPDATE chapter SET created_at=datetime('2023-01-01','+'||(CAST(substr(series_id,2) AS INTEGER)%53)||' days'), source_uploaded_at=CASE WHEN CAST(substr(series_id,2) AS INTEGER)%4=0 THEN datetime('2024-01-01','+'||(CAST(substr(series_id,2) AS INTEGER)%43)||' days') END"
            )
        )
        connection.execute(
            text(
                "UPDATE provider_chapter SET published_at=datetime('2024-01-01','+'||(CAST(substr(series_id,2) AS INTEGER)%37)||' days')"
            )
        )
        connection.execute(
            insert(SeriesCredit),
            [
                {
                    "series_id": f"s{i:011d}",
                    "role": "author",
                    "name": f"Writer {i % 20}",
                    "position": 0,
                }
                for i in range(catalog)
            ],
        )
        connection.execute(
            insert(Tag),
            [{"id": f"test-tag-{i}", "name": f"Test {i}", "group": "genre"} for i in range(4)],
        )
        connection.execute(
            insert(series_tag),
            [{"series_id": f"s{i:011d}", "tag_id": f"test-tag-{i % 4}"} for i in range(catalog)],
        )
        connection.execute(
            insert(ProviderReadingProgress),
            [
                {
                    "series_id": f"s{i:011d}",
                    "provider": "mangadex",
                    "provider_chapter_id": f"{i}-1",
                    "completed": True,
                    "current_page": 20,
                }
                for i in range(1, catalog, 4)
            ],
        )
    engine.dispose()


def allocated_bytes(engine):
    with engine.connect() as connection:
        pages = connection.exec_driver_sql("PRAGMA page_count").scalar_one()
        free = connection.exec_driver_sql("PRAGMA freelist_count").scalar_one()
        size = connection.exec_driver_sql("PRAGMA page_size").scalar_one()
    return (pages - free) * size


def write_cost(engine, iterations):
    result = {}
    for label, sql in {
        "publication_refresh_100_rows": "UPDATE provider_chapter SET published_at='2030-01-01' WHERE series_id IN ('s00000000001','s00000000002','s00000000003','s00000000004','s00000000005')",
        "progress_toggle": "UPDATE reading_progress SET completed=NOT completed WHERE chapter_id='c00000000000'",
    }.items():

        def attempt(sql=sql):
            with engine.connect() as connection:
                connection.exec_driver_sql(sql)
                connection.rollback()

        result[label] = measure(attempt, iterations)
    return result


def run_operations(args):
    old = reference(args.reference)
    indices = [
        index
        for table in Base.metadata.sorted_tables
        for index in table.indexes
        if index.name in INDEX_NAMES
    ]
    result = {
        "reference": args.reference,
        "catalog": args.catalog,
        "iterations": args.iterations,
        "engines": {},
    }
    with tempfile.TemporaryDirectory(
        prefix="lychee-catalog-operations-", dir=args.temp_root
    ) as directory:
        root = Path(directory)
        source = root / "source.db"
        seed(source, args.catalog)
        clean = create_database_engine(f"sqlite:///{source}")
        with clean.begin() as connection:
            for index in indices:
                index.drop(connection)
        with clean.connect() as connection:
            connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)").all()
        clean.dispose()
        for mode in ("sqlite", "turso"):
            path = root / (mode + ".db")
            shutil.copyfile(source, path)
            url = f"{'sqlite+turso' if mode == 'turso' else 'sqlite'}:///{path}"
            state = {"engine": create_database_engine(url, migrations=True)}

            def query(repo, operation, state=state):
                with Session(state["engine"]) as session:
                    if operation == "batch24":
                        ids = [f"s{i:011d}" for i in range(24)]
                        rows = repo.get_series_rows(session, ids)
                        return snapshot(([rows[sid] for sid in ids], None))
                    return snapshot((getattr(repo, operation)(session), None))

            records, expected = {}, {}
            for operation in ("batch24", "continue_reading", "recently_added"):
                expected[operation] = query(old, operation)
                records[operation] = {
                    "baseline": measure(
                        lambda operation=operation: query(old, operation), args.iterations
                    )
                }
            with state["engine"].begin() as connection:
                for index in indices:
                    index.create(connection)
            with state["engine"].connect() as connection:
                connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)").all()
            state["engine"].dispose()
            state["engine"] = create_database_engine(url)
            for operation in records:
                assert query(repository, operation) == expected[operation], (mode, operation)
                records[operation]["optimized"] = measure(
                    lambda operation=operation: query(repository, operation), args.iterations
                )
            state["engine"].dispose()
            result["engines"][mode] = records
    return result


def run(args):
    old = reference(args.reference)
    report = {
        "reference": args.reference,
        "config": vars(args)
        | {
            "output": str(args.output),
            "temp_root": str(args.temp_root) if args.temp_root else None,
        },
        "engines": {},
    }
    indices = sorted(
        [
            index
            for table in Base.metadata.sorted_tables
            for index in table.indexes
            if index.name in INDEX_NAMES
        ],
        key=lambda index: str(index.name),
    )
    assert len(indices) == len(INDEX_NAMES)
    with tempfile.TemporaryDirectory(
        prefix="lychee-catalog-bench-", dir=args.temp_root
    ) as directory:
        root = Path(directory)
        source = root / "source.db"
        seed(source, args.catalog)
        enrich(source, args.catalog)
        clean = create_database_engine(f"sqlite:///{source}")
        with clean.begin() as connection:
            for index in indices:
                index.drop(connection)
        with clean.connect() as connection:
            connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)").all()
        clean.dispose()
        modes = ["sqlite", "turso"]
        if args.reverse:
            modes.reverse()
        golden_engine = create_database_engine(f"sqlite:///{source}")
        golden = {}
        for mode in modes:
            path = root / (mode + ".db")
            shutil.copyfile(source, path)
            scheme = "sqlite+turso" if mode == "turso" else "sqlite"
            engine = create_database_engine(f"{scheme}:///{path}", migrations=True)
            cases = [
                (sort, repository.SeriesFilters(kind="manga", sort=sort))
                for sort in ("recentlyAdded", "recentlyUpdated", "unread", "title", "rating")
            ]
            cases += [
                ("added-reading", repository.SeriesFilters(kind="manga", read_state="in_progress")),
                (
                    "updated-unread",
                    repository.SeriesFilters(
                        kind="manga", sort="recentlyUpdated", read_state="unread"
                    ),
                ),
                (
                    "unread-read",
                    repository.SeriesFilters(kind="manga", sort="unread", read_state="read"),
                ),
                (
                    "library-favorites",
                    repository.SeriesFilters(kind="manga", library_id="library", favorite=True),
                ),
                (
                    "author-tags",
                    repository.SeriesFilters(
                        kind="manga",
                        author="Writer 2",
                        tags_exclude=["test-tag-0"],
                        sort="recentlyUpdated",
                    ),
                ),
                ("gallery", repository.SeriesFilters(kind="gallery", sort="title")),
                ("all-kinds", repository.SeriesFilters(sort="recentlyUpdated")),
            ]

            state = {"engine": engine}

            def query(repo, filters, cursor=None, state=state):
                with Session(state["engine"]) as session:
                    return snapshot(repo.list_series(session, filters, cursor=cursor))

            records = {}
            for label, filters in cases:
                if label not in golden:
                    state["engine"] = golden_engine
                    first = query(old, filters)
                    golden[label] = (first, query(old, filters, first[1]) if first[1] else None)
                    state["engine"] = engine
                first = golden[label][0]
                records[label] = {
                    "filters": asdict(filters),
                    "first": first,
                }
                try:
                    assert query(old, filters) == first
                    records[label]["baseline"] = measure(
                        lambda filters=filters: query(old, filters), args.iterations
                    )
                except Exception as error:
                    records[label]["baseline"] = {"error": str(error).split("[SQL:")[0][:300]}
                if first[1]:
                    records[label]["next"] = golden[label][1]
            before_bytes = path.stat().st_size
            before_allocated = allocated_bytes(engine)
            before_writes = write_cost(engine, args.iterations)
            with engine.begin() as connection:
                for index in indices:
                    index.create(connection)
            with engine.connect() as connection:
                checkpoint = connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)").first()
                assert checkpoint is not None and checkpoint[0] == 0
            engine.dispose()
            engine = create_database_engine(f"{scheme}:///{path}")
            state["engine"] = engine
            for label, filters in cases:
                entry = records[label]
                assert query(repository, filters) == entry["first"], (
                    mode,
                    label,
                    "first page changed",
                )
                entry["optimized"] = measure(
                    lambda filters=filters: query(repository, filters), args.iterations
                )
                entry["rows"] = len(entry["first"][0])
                if "next" in entry:
                    assert query(repository, filters, entry["first"][1]) == entry["next"], (
                        mode,
                        label,
                        "continuation changed",
                    )
                entry["equivalence_sha256"] = hashlib.sha256(
                    json.dumps(entry.pop("first")).encode()
                ).hexdigest()
                entry.pop("next", None)
            after_allocated = allocated_bytes(engine)
            after_writes = write_cost(engine, args.iterations)
            engine.dispose()
            report["engines"][mode] = records
            report.setdefault("index_cost", {})[mode] = {
                "file_bytes_before": before_bytes,
                "file_bytes_after": path.stat().st_size,
                "allocated_bytes_before": before_allocated,
                "allocated_bytes_after": after_allocated,
                "write_before": before_writes,
                "write_after": after_writes,
            }
            print(f"finished {mode}", flush=True)
        golden_engine.dispose()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=int, default=2000)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--reference", default="9e35c2f")
    parser.add_argument("--temp-root", type=Path)
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument(
        "--operations-only",
        action="store_true",
        help="Measure dashboard rails and batched hydration on the basic fixture",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_operations(args) if args.operations_only else run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
