"""Copy and verify an existing SQLite library into a separate local Turso database."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Callable, Sequence
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import src.models  # noqa: F401
from src.bootstrap import run_migrations
from src.catalog.search_index import (
    SEARCH_INDEX_DROP_STATEMENTS,
    create_search_index,
)
from src.core.persistence.base_model import Base
from src.core.persistence.database import create_database_engine


def _fingerprints(fetch: Callable[[str], Sequence[Sequence[Any]]]) -> dict[str, dict[str, Any]]:
    result = {}
    for table in Base.metadata.sorted_tables:
        columns = ",".join(f'"{column.name}"' for column in table.columns)
        order = ",".join(f'"{column.name}"' for column in table.primary_key.columns)
        rows = [
            tuple(row) for row in fetch(f'SELECT {columns} FROM "{table.name}" ORDER BY {order}')
        ]
        payload = json.dumps(
            rows,
            ensure_ascii=False,
            separators=(",", ":"),
            default=lambda value: {"bytes": bytes(value).hex()},
        )
        result[table.name] = {
            "rows": len(rows),
            "sha256": hashlib.sha256(payload.encode()).hexdigest(),
        }
    return result


def convert_sqlite_to_turso(source: Path, destination: Path) -> dict[str, Any]:
    """Never modify the source or overwrite an existing destination.

    Upgrade a disposable SQLite backup, replace its engine-specific search index,
    verify every ORM table's row values, checkpoint MVCC, then publish the new file.
    """
    source = source.resolve()
    destination = destination.resolve()
    if source == destination or destination.exists():
        raise ValueError("Choose a new destination file; in-place conversion is not supported")
    if not source.is_file():
        raise ValueError("Source SQLite database does not exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".lychee-convert-", dir=destination.parent) as directory:
        staging = Path(directory) / "converted.db"
        with (
            closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as reader,
            closing(sqlite3.connect(staging)) as copy,
        ):
            reader.backup(copy)
            if (
                copy.execute("SELECT 1 FROM sqlite_master WHERE name='alembic_version'").fetchone()
                is None
            ):
                raise ValueError("Source is not a migrated Lychee database")
        run_migrations(f"sqlite:///{staging}")
        with closing(sqlite3.connect(staging)) as copy:
            before = _fingerprints(lambda query: copy.execute(query).fetchall())
            for statement in SEARCH_INDEX_DROP_STATEMENTS:
                copy.execute(statement)
            copy.commit()
            copy.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        engine = create_database_engine(f"sqlite+turso:///{staging}", migrations=True)
        try:
            with engine.begin() as connection:
                create_search_index(connection)
            with engine.connect() as connection:
                after = _fingerprints(lambda query: connection.exec_driver_sql(query).all())
                if after != before:
                    raise ValueError("Converted table contents differ from the SQLite snapshot")
                integrity = connection.exec_driver_sql("PRAGMA integrity_check").scalars().all()
                if integrity != ["ok"]:
                    raise ValueError(f"Converted database integrity check failed: {integrity}")
                checkpoint = connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)").first()
                if checkpoint is None or checkpoint[0] != 0:
                    raise ValueError("Could not checkpoint the converted database")
        finally:
            engine.dispose()
        # MVCC's -log must be checkpointed too, not just the SQLite-style -wal.
        for suffix in ("-log", "-wal"):
            sidecar = staging.with_name(staging.name + suffix)
            if sidecar.exists() and sidecar.stat().st_size:
                raise ValueError("Conversion still has uncheckpointed transaction data")
        staging.chmod(0o600)
        os.link(staging, destination)  # same filesystem; atomically refuses concurrent overwrite
        return {
            "destination": str(destination),
            "tables_verified": len(after),
            "rows": {table: value["rows"] for table, value in after.items()},
        }
