"""Native Turso transaction, search, migration and safe-conversion coverage."""

from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from src.bootstrap import run_migrations
from src.catalog.models import SeriesCredit
from src.catalog.search_index import create_search_index, search_ids
from src.core.persistence.convert import convert_sqlite_to_turso
from src.core.persistence.database import create_database_engine

from tests.support import make_series


def test_native_mvcc_can_commit_disjoint_overlapping_writes(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+turso:///{tmp_path / 'mvcc.db'}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE probe (id INTEGER PRIMARY KEY, value TEXT)"))
        with engine.connect() as first, engine.connect() as second:
            first.execute(text("INSERT INTO probe VALUES (1,'first')"))
            second.execute(text("INSERT INTO probe VALUES (2,'second')"))
            first.commit()
            second.commit()
            assert first.scalar(text("SELECT count(*) FROM probe")) == 2
            assert first.scalar(text("PRAGMA journal_mode")) == "mvcc"
    finally:
        engine.dispose()


def test_native_migrations_are_idempotent_and_search_reopens(tmp_path: Path) -> None:
    url = f"sqlite+turso:///{tmp_path / 'migrations.db'}"
    run_migrations(url)
    run_migrations(url)
    engine = create_database_engine(url)
    try:
        with Session(engine) as session:
            series = make_series(session, title="東京喰種 Extra", authors=("Writer Demo",))
            session.commit()
            sid = series.id
            assert search_ids(session, "京喰種") == [sid]
            credit = session.scalar(
                select(SeriesCredit).where(
                    SeriesCredit.series_id == sid, SeriesCredit.role == "author"
                )
            )
            assert credit is not None
            credit.name = "Changed Writer"
            session.rollback()
            assert search_ids(session, "Writer Demo") == [sid]
        with engine.begin() as connection:
            create_search_index(connection)
        with Session(engine) as session:
            assert search_ids(session, "京喰種") == [sid]
            assert session.scalar(text("SELECT count(*) FROM series_fts")) == 1
    finally:
        engine.dispose()


def test_conversion_preserves_all_rows_and_original_sqlite(tmp_path: Path) -> None:
    source_url = f"sqlite:///{tmp_path / 'sqlite-source.db'}"
    run_migrations(source_url)
    source_engine = create_database_engine(source_url)
    source_session = Session(source_engine)
    try:
        series = make_series(source_session, title="Preserved", chapter_count=2, unread=1)
        source_session.commit()
        sid = series.id
        source_session.commit()
        source = tmp_path / "sqlite-source.db"
        destination = tmp_path / "turso-copy.db"
        result = convert_sqlite_to_turso(source, destination)
        assert result["rows"]["series"] == 1
        assert result["rows"]["reading_progress"] == 1
        assert (
            source_session.scalar(text("SELECT title FROM series WHERE id=:id"), {"id": sid})
            == "Preserved"
        )
        target = create_database_engine(f"sqlite+turso:///{destination}")
        try:
            with Session(target) as session:
                assert search_ids(session, "Preserved") == [sid]
                assert session.scalar(text("SELECT count(*) FROM chapter")) == 2
                assert session.scalar(text("SELECT count(*) FROM reading_progress")) == 1
        finally:
            target.dispose()
        with pytest.raises(ValueError, match="new destination"):
            convert_sqlite_to_turso(source, destination)
        with pytest.raises(ValueError, match="in-place"):
            convert_sqlite_to_turso(source, source)
    finally:
        source_session.close()
        source_engine.dispose()


def test_conversion_rejects_missing_sources(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        convert_sqlite_to_turso(tmp_path / "missing.db", tmp_path / "destination.db")


def test_native_search_uses_weighted_scores_not_id_order(tmp_path: Path) -> None:
    url = f"sqlite+turso:///{tmp_path / 'ranking.db'}"
    run_migrations(url)
    engine = create_database_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO series_fts(series_id,title,alt_titles,authors) VALUES "
                    "('aaa','Other','','Berserk Admirer'),('zzz','Berserk','','Kentaro Miura')"
                )
            )
        with Session(engine) as session:
            assert search_ids(session, "Berserk") == ["zzz", "aaa"]
    finally:
        engine.dispose()


def test_about_reports_native_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import settings
    from src.integrations.about import info

    monkeypatch.setattr(settings, "database_url", "sqlite+turso:///./unused.db")
    assert info().database == "Turso (local MVCC)"
