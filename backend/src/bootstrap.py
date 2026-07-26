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
    # Workers die with the process — any mid-flight download_task rows are orphans.
    from pathlib import Path

    from sqlalchemy import select

    from src.catalog.models import Series
    from src.core.config import settings
    from src.core.persistence.database import SessionLocal
    from src.downloads.downloader import reclaim_orphaned_downloads
    from src.downloads.models import DownloadTask
    from src.downloads.service import _resume_work
    from src.tasks.queue import queue

    with SessionLocal() as session:
        reclaimed = reclaim_orphaned_downloads(session)
        # Kick a drain for every series that still has queued chapters so a restart
        # actually continues the queue (reclaim alone only flips status).
        series_ids = list(
            session.scalars(
                select(DownloadTask.series_id)
                .where(DownloadTask.status == "queued", DownloadTask.series_id.is_not(None))
                .distinct()
            )
        )
        storage = Path(settings.storage_path)
        for sid in series_ids:
            if not sid:
                continue
            series = session.get(Series, sid)
            label = f"Resuming {series.title}" if series else f"Resuming {sid}"
            _ = queue.submit("download", label, _resume_work(sid, storage))
        if reclaimed or series_ids:
            logger.info(
                "download_queue_resumed",
                reclaimed=reclaimed,
                series=len(series_ids),
            )
    logger.info("bootstrap_complete")
