"""Shared test fixtures — an isolated temp-DB app bound per test."""

from collections.abc import Iterator
from pathlib import Path

import pytest
import src.models  # noqa: F401  (register every model on Base.metadata)
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from src.catalog.deps import get_thumbnail_store
from src.core.persistence.base_model import Base
from src.core.persistence.database import get_db
from src.main import app
from src.media.thumbnails import ThumbnailStore
from src.seed import seed_all


@pytest.fixture
def db_engine(tmp_path: Path) -> Iterator[Engine]:
    """A fresh SQLite database with the full schema, seeded with default data."""
    engine = create_engine(
        f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False}
    )
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
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
