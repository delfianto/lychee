"""Resolve thumbnail storage for requests and background jobs."""

from pathlib import Path
from tempfile import TemporaryFile

from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.exceptions import BadRequestError
from src.media.models import ThumbnailConfig
from src.media.schema import ThumbnailStorageOut, ThumbnailStorageUpdate


def thumbnail_root(session: Session, storage_root: Path | None = None) -> Path:
    config = session.get(ThumbnailConfig, "default", populate_existing=True)
    if config is not None and config.path:
        return Path(config.path)
    return (storage_root or Path(settings.storage_path)) / "thumbnails"


def get_thumbnail_storage(session: Session) -> ThumbnailStorageOut:
    config = session.get(ThumbnailConfig, "default", populate_existing=True)
    default = str((Path(settings.storage_path) / "thumbnails").resolve())
    path = config.path if config else None
    return ThumbnailStorageOut(path=path, default_path=default, effective_path=path or default)


def update_thumbnail_storage(session: Session, data: ThumbnailStorageUpdate) -> ThumbnailStorageOut:
    path = None
    if data.path is not None:
        raw = data.path.strip()
        if not raw or "\0" in raw or not Path(raw).is_absolute():
            raise BadRequestError("Choose an absolute folder path on the server")
        path = raw
    try:
        if path is not None:
            path = str(Path(path).resolve())
        target = Path(path) if path else Path(settings.storage_path) / "thumbnails"
        target.mkdir(parents=True, exist_ok=True)
        with TemporaryFile(dir=target) as probe:
            _ = probe.write(b"thumbnail storage check")
            probe.flush()
    except OSError as exc:
        raise BadRequestError(
            "The thumbnail folder could not be created or is not writable"
        ) from exc
    config = session.get(ThumbnailConfig, "default")
    if config is None:
        config = ThumbnailConfig(id="default")
        session.add(config)
    config.path = path
    session.commit()
    return get_thumbnail_storage(session)
