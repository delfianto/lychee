"""Local-import action — validate the request, then run the import on the task queue.

The request names a path on the server's disk (a container file or a folder); the
same trust model as adding a library. Gated by the import-enabled toggle. The job
itself lives in ``src/ingest/importer.py`` (PART G / G3).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from src.core.exceptions import BadRequestError
from src.ingest.importer import import_path
from src.integrations.import_config import get_config_row
from src.integrations.schema import ImportRequest
from src.tasks.queue import Work, queue
from src.tasks.schema import TaskOut

_KINDS = {"manga", "comic", "gallery"}


def _import_work(source: str, kind: str, storage_root: Path) -> Work:
    def work(session: Session, on_progress: Callable[[int, str], None]) -> dict[str, int]:
        cfg = get_config_row(session)  # read quality + pattern fresh at run time
        return import_path(
            session,
            Path(source),
            kind=kind,
            storage_root=storage_root,
            quality=cfg.quality,
            filename_pattern=cfg.filename_pattern,
            on_progress=on_progress,
        )

    return work


def start_import(session: Session, data: ImportRequest, storage_root: Path) -> TaskOut:
    """Validate (enabled + kind + path) here, then run the import on the task queue."""
    if not get_config_row(session).enabled:
        raise BadRequestError("local import is disabled")
    if data.kind not in _KINDS:
        raise BadRequestError(f"invalid kind: {data.kind!r}")
    source = Path(data.path).expanduser()
    if not (source.is_file() or source.is_dir()):
        raise BadRequestError(f"path not found: {data.path}")
    return queue.submit_task(
        "localimport", f"Importing {source.name}", _import_work(str(source), data.kind, storage_root)
    )
