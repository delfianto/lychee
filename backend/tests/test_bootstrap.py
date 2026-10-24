"""Test that startup migrations bring a fresh database to head."""

import sqlite3
from pathlib import Path

import pytest
from src.bootstrap import run_migrations
from src.core.config import settings


def test_run_migrations_creates_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "boot.db"
    # Alembic reads settings.database_url fresh when env.py runs.
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")

    run_migrations()

    con = sqlite3.connect(db_path)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    assert {"series", "tag", "chapter", "alembic_version"} <= tables


def test_list_type_migration_preserves_memberships_and_classifies_legacy_lists() -> None:
    import runpy

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, text

    migration = runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "alembic/versions/a5c731d9e204_typed_collections.py"
        )
    )
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE collection (id TEXT PRIMARY KEY, provider TEXT)"))
        connection.execute(text("CREATE TABLE series (id TEXT PRIMARY KEY, kind TEXT)"))
        connection.execute(
            text("CREATE TABLE collection_series (collection_id TEXT, series_id TEXT)")
        )
        connection.execute(
            text(
                "INSERT INTO collection VALUES ('gallery',NULL),('empty',NULL),('mixed',NULL),('remote','mangadex')"
            )
        )
        connection.execute(text("INSERT INTO series VALUES ('g','gallery'),('m','manga')"))
        connection.execute(
            text("INSERT INTO collection_series VALUES ('gallery','g'),('mixed','g'),('mixed','m')")
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration["upgrade"]()
        assert dict(connection.execute(text("SELECT id,kind FROM collection")).all()) == {
            "gallery": "gallery",
            "empty": "manga",
            "mixed": "mixed",
            "remote": "manga",
        }
        assert connection.scalar(text("SELECT COUNT(*) FROM collection_series")) == 3
    engine.dispose()
