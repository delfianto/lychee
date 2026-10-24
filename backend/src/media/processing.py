"""Persist and apply independent image processing budgets."""

import os
from threading import Lock

from sqlalchemy.orm import Session

from src.core.config import settings
from src.media.encode_pool import MAX_IMAGE_WORKERS, configure_workers
from src.media.models import ImageProcessingConfig
from src.media.schema import ImageProcessingOut, ImageProcessingUpdate

_configuration_lock = Lock()


def get_processing(session: Session) -> ImageProcessingOut:
    row = session.get(ImageProcessingConfig, "default", populate_existing=True)
    legacy = max(1, min(MAX_IMAGE_WORKERS, settings.encode_workers))
    cpus = os.process_cpu_count() or 1
    return ImageProcessingOut(
        conversion_workers=row.conversion_workers if row else legacy,
        thumbnail_workers=row.thumbnail_workers if row else legacy,
        cpu_threads=cpus,
        recommended_conversion_workers=max(1, min(16, cpus // 2)),
        recommended_thumbnail_workers=max(1, min(4, cpus // 8)),
    )


def configure_processing(session: Session) -> None:
    # Concurrent settings saves must apply in the same order as their fresh
    # reads. Otherwise an older request could overwrite the newer CPU budgets.
    with _configuration_lock:
        config = get_processing(session)
        configure_workers(config.conversion_workers, config.thumbnail_workers)


def update_processing(session: Session, data: ImageProcessingUpdate) -> ImageProcessingOut:
    row = session.get(ImageProcessingConfig, "default")
    if row is None:
        row = ImageProcessingConfig(id="default")
        session.add(row)
    row.conversion_workers = data.conversion_workers
    row.thumbnail_workers = data.thumbnail_workers
    session.commit()
    configure_processing(session)
    return get_processing(session)
