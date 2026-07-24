"""Tests for the default-data seed (idempotency + expected fixed rows)."""

from pathlib import Path

import src.models  # noqa: F401  (register all models on Base.metadata)
from sqlalchemy import ColumnElement, create_engine, func, select
from sqlalchemy.orm import Session
from src.core.persistence.base_model import Base
from src.integrations.models import Provider, SyncState, Tracker
from src.seed import seed_all
from src.taxonomy.models import Tag


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'seed.db'}")
    Base.metadata.create_all(engine)
    return Session(engine)


def _count(session: Session, model: type, *where: ColumnElement[bool]) -> int:
    stmt = select(func.count()).select_from(model)
    for clause in where:
        stmt = stmt.where(clause)
    return session.scalar(stmt) or 0


def test_seed_populates_expected_rows(tmp_path: Path) -> None:
    with _session(tmp_path) as session:
        seed_all(session)
        session.commit()

        # Fixed enum groups are exact and flagged system.
        assert _count(session, Tag, Tag.group == "content_rating") == 4
        assert _count(session, Tag, Tag.group == "demographic") == 4
        assert _count(session, Tag, Tag.system.is_(True)) == 8
        # The four series-linked groups are all seeded.
        for group in ("genre", "theme", "format", "content"):
            assert _count(session, Tag, Tag.group == group) > 0

        assert _count(session, Provider) == 1
        assert _count(session, Tracker) == 4
        assert _count(session, SyncState) == 1

        # A known system row.
        safe = session.get(Tag, "safe")
        assert safe is not None
        assert safe.group == "content_rating" and safe.system and safe.enabled


def test_seed_is_idempotent(tmp_path: Path) -> None:
    with _session(tmp_path) as session:
        seed_all(session)
        session.commit()
        total_after_first = _count(session, Tag)

        seed_all(session)  # second run must add nothing
        session.commit()
        assert _count(session, Tag) == total_after_first
        assert _count(session, Tracker) == 4
