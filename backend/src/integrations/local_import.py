"""Local-import action — validate the request, then run the import on the task queue.

The request names a path on the server's disk (a container file or a folder); the
same trust model as adding a library. Gated by the import-enabled toggle. The job
itself lives in ``src/ingest/importer.py`` (PART G / G3).
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from src.core.exceptions import BadRequestError
from src.ingest.importer import import_path
from src.integrations.import_config import get_config_row
from src.integrations.schema import ImportRequest
from src.tasks.queue import Work, queue
from src.tasks.schema import TaskOut

_KINDS = {"manga", "comic", "gallery"}
_UPLOAD_EXTS = {".cbz", ".zip"}
_MAX_UPLOAD_BYTES = 1024 * 1024 * 1024  # 1 GiB
_UPLOAD_CHUNK = 1024 * 1024


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


async def _stage_upload(file: UploadFile, storage_root: Path) -> tuple[Path, Path]:
    """Stream an upload to a fresh staging dir, enforcing the size cap; clean up on error.
    Returns ``(staging_dir, staged_file)``."""
    staged_dir = storage_root / "uploads" / uuid.uuid4().hex
    staged_dir.mkdir(parents=True, exist_ok=True)
    staged_file = staged_dir / Path(file.filename or "upload").name  # .name strips any path
    size = 0
    try:
        with staged_file.open("wb") as out:
            while chunk := await file.read(_UPLOAD_CHUNK):
                size += len(chunk)
                if size > _MAX_UPLOAD_BYTES:
                    raise BadRequestError("upload exceeds the maximum size")
                _ = out.write(chunk)
    except BaseException:
        shutil.rmtree(staged_dir, ignore_errors=True)
        raise
    return staged_dir, staged_file


def _staged_import_work(staged_dir: str, staged_file: str, kind: str, storage_root: Path) -> Work:
    def work(session: Session, on_progress: Callable[[int, str], None]) -> dict[str, int]:
        cfg = get_config_row(session)
        try:
            return import_path(
                session,
                Path(staged_file),
                kind=kind,
                storage_root=storage_root,
                quality=cfg.quality,
                filename_pattern=cfg.filename_pattern,
                on_progress=on_progress,
            )
        finally:
            shutil.rmtree(staged_dir, ignore_errors=True)  # drop the staged upload

    return work


async def start_upload_import(
    session: Session, file: UploadFile, kind: str, storage_root: Path
) -> TaskOut:
    """Validate + stage a browser upload, then run the import on the task queue."""
    if not get_config_row(session).enabled:
        raise BadRequestError("local import is disabled")
    if kind not in _KINDS:
        raise BadRequestError(f"invalid kind: {kind!r}")
    name = Path(file.filename or "").name
    if Path(name).suffix.lower() not in _UPLOAD_EXTS:
        raise BadRequestError("only .cbz / .zip uploads are supported")
    staged_dir, staged_file = await _stage_upload(file, storage_root)
    return queue.submit_task(
        "localimport",
        f"Importing {name}",
        _staged_import_work(str(staged_dir), str(staged_file), kind, storage_root),
    )
