"""Database engine and session.

SQLite/WAL by default; sqlite+turso URLs select optional local Turso/MVCC.
See notes/decisions/04-database-sqlite.md and 23-local-turso.md. CRUD uses
synchronous SQLAlchemy sessions; slow media work must release connections.
"""

from collections.abc import Generator
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.dialects import registry
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import settings

registry.register("sqlite.turso", "src.core.persistence.turso", "TursoDialect")


def create_database_engine(url: str, *, migrations: bool = False, **options: Any) -> Engine:
    """One engine factory for app, migrations, test harnesses and benchmarks."""
    driver = make_url(url).drivername
    is_turso = driver == "sqlite+turso"
    if is_turso:
        options.setdefault("connect_args", {})["isolation_level"] = (
            "DEFERRED" if migrations else "CONCURRENT"
        )
    elif driver.startswith("sqlite"):
        options.setdefault("connect_args", {}).setdefault("check_same_thread", False)
    instance = create_engine(url, **options)
    if driver.startswith("sqlite") and not is_turso:

        @event.listens_for(instance, "connect")
        def pragmas(connection: Any, _record: Any) -> None:
            cursor = connection.cursor()
            for pragma in [
                "journal_mode=WAL",
                "foreign_keys=ON",
                "busy_timeout=30000",
                "synchronous=NORMAL",
            ]:
                cursor.execute("PRAGMA " + pragma)
                cursor.fetchall()  # pyturso PRAGMAs are lazy until their result is stepped
            cursor.close()

    if is_turso:
        from src.catalog.search_index import (
            mark_turso_search,
            reset_turso_search,
            sync_turso_search,
        )

        event.listen(instance, "after_cursor_execute", mark_turso_search)
        event.listen(instance, "commit", sync_turso_search)
        event.listen(instance, "rollback", reset_turso_search)
    return instance


engine = create_database_engine(settings.database_url)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session]:
    """FastAPI dependency: a request-scoped session, closed afterward."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]
