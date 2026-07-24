"""Startup bootstrap — bring the configured database up to head and seed defaults.

Both steps are idempotent, so this is safe to run on every boot. Disabled in tests
(``settings.auto_bootstrap = False``) which manage their own schema.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from src.core.logging import get_logger
from src.seed import run_seed

logger = get_logger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def run_migrations() -> None:
    """Upgrade the configured database to the latest Alembic revision."""
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    command.upgrade(config, "head")


def bootstrap() -> None:
    """Run migrations, then seed default taxonomy/integration rows."""
    run_migrations()
    run_seed()
    logger.info("bootstrap_complete")
