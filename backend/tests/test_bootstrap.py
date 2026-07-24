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
