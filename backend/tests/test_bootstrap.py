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


def test_provider_progress_migration_backfills_existing_reads(db_session) -> None:
    import runpy

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import select, text
    from src.catalog.models import Chapter

    from tests.support import make_series

    series = make_series(db_session, title="Migrated", chapter_count=2, unread=1)
    series.provider = "mangadex"
    chapters = list(
        db_session.scalars(
            select(Chapter).where(Chapter.series_id == series.id).order_by(Chapter.number_sort)
        )
    )
    chapters[0].provider_chapter_id = "remote-read"
    db_session.commit()  # historical DDL starts outside a runtime MVCC transaction
    db_session.execute(text("DROP TABLE provider_reading_progress"))
    migration = runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "alembic/versions/b7e819d4c602_provider_reading_progress.py"
        )
    )
    with Operations.context(MigrationContext.configure(db_session.connection())):
        migration["upgrade"]()
    rows = db_session.execute(
        text(
            "SELECT series_id,provider,provider_chapter_id,current_page,completed FROM provider_reading_progress"
        )
    ).all()
    assert rows == [(series.id, "mangadex", "remote-read", 1, 1)]
    assert db_session.scalar(text("SELECT COUNT(*) FROM reading_progress")) == 1
