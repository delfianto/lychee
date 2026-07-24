"""Seed default data (idempotent) — taxonomy + integration rows.

Run at app startup and available as a one-shot: ``uv run python -m src.seed``.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.integrations.seed import seed_integrations
from src.taxonomy.seed import seed_taxonomy


def seed_all(session: Session) -> None:
    """Populate all default rows on the given session (caller commits)."""
    seed_taxonomy(session)
    seed_integrations(session)


def run_seed() -> None:
    """Open a session, seed, and commit — for startup and the CLI entrypoint."""
    from src.core.persistence.database import SessionLocal

    with SessionLocal() as session:
        seed_all(session)
        session.commit()


if __name__ == "__main__":
    run_seed()
