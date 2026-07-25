"""Shared test fixtures — an isolated temp-DB app bound per test."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import src.models  # noqa: F401  (register every model on Base.metadata)
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from src.catalog.deps import get_thumbnail_store
from src.core.config import settings
from src.core.persistence.base_model import Base
from src.core.persistence.database import SessionLocal, get_db
from src.downloads.deps import get_storage_root
from src.downloads.provider import MangaMatch, RemoteChapter, SeriesMetadata, register_provider
from src.main import app
from src.media.thumbnails import ThumbnailStore
from src.seed import seed_all
from src.tasks.queue import queue


class _OfflineProvider:
    """Neutralises the network MangaDex provider in tests (e.g. scan auto-match)."""

    id = "mangadex"

    def list_chapters(self, provider_series_id: str, *, language: str = "en") -> list[RemoteChapter]:
        return []

    def fetch_pages(self, chapter: RemoteChapter, *, data_saver: bool = False) -> list[bytes]:
        return []

    def search(self, title: str, *, limit: int = 5) -> list[MangaMatch]:
        return []

    def get_metadata(self, provider_series_id: str, *, language: str = "en") -> SeriesMetadata:
        raise NotImplementedError

    def list_new_chapters(
        self, provider_series_id: str, *, known: set[str], language: str = "en"
    ) -> list[RemoteChapter]:
        return []

# Tests manage their own schema per fixture; never migrate/seed the real database.
settings.auto_bootstrap = False


@pytest.fixture
def db_engine(tmp_path: Path) -> Iterator[Engine]:
    """A fresh SQLite database with the full schema, seeded with default data."""
    engine = create_engine(
        f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection: Any, _record: Any) -> None:
        # WAL lets the background task worker write while the request thread reads,
        # matching production and avoiding cross-thread "database is locked".
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_all(session)
        session.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """A session on the seeded temp database, for repository-level tests."""
    with Session(db_engine) as session:
        yield session


@pytest.fixture
def client(db_engine: Engine, tmp_path: Path) -> Iterator[TestClient]:
    """A TestClient bound to the temp database and a temp thumbnail store."""
    test_session = sessionmaker(bind=db_engine)

    def _get_db() -> Iterator[Session]:
        session = test_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_thumbnail_store] = lambda: ThumbnailStore(tmp_path / "thumbnails")
    app.dependency_overrides[get_storage_root] = lambda: tmp_path / "storage"
    queue.configure(test_session)  # background workers use this test's temp DB
    with TestClient(app) as test_client:
        register_provider(_OfflineProvider())  # startup registers the real one; neutralise it
        yield test_client
    app.dependency_overrides.clear()
    queue.configure(SessionLocal)
