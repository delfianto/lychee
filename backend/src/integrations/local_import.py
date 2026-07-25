"""Local-import action — validate the request, then run the import on the task queue.

The request names a path on the server's disk (a container file or a folder); the
same trust model as adding a library. Gated by the import-enabled toggle. The job
itself lives in ``src/ingest/importer.py`` (PART G / G3).
"""

from __future__ import annotations

import re
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


async def _stage_uploads(files: list[UploadFile], storage_root: Path) -> Path:
    """Stream uploads into one fresh staging dir, enforcing the per-file size cap; clean
    up the whole dir on any error. Returns the staging dir."""
    staged_dir = storage_root / "uploads" / uuid.uuid4().hex
    staged_dir.mkdir(parents=True, exist_ok=True)
    try:
        for file in files:
            staged_file = staged_dir / Path(file.filename or "upload").name  # .name strips paths
            size = 0
            with staged_file.open("wb") as out:
                while chunk := await file.read(_UPLOAD_CHUNK):
                    size += len(chunk)
                    if size > _MAX_UPLOAD_BYTES:
                        raise BadRequestError("upload exceeds the maximum size")
                    _ = out.write(chunk)
    except BaseException:
        shutil.rmtree(staged_dir, ignore_errors=True)
        raise
    return staged_dir


def _batch_title(names: list[str]) -> str:
    """A series title for an upload batch: the filenames' shared leading tokens (so
    ``Berserk c001.cbz`` + ``Berserk c002.cbz`` → ``Berserk``), else the first stem."""
    stems = [Path(n).stem for n in names]
    if len(stems) == 1:
        return stems[0]
    common: list[str] = []
    for tokens in zip(*(re.split(r"[\s._-]+", stem) for stem in stems), strict=False):
        if len(set(tokens)) != 1:
            break
        common.append(tokens[0])
    return " ".join(common).strip() or stems[0]


def _staged_import_work(staged_dir: str, kind: str, storage_root: Path, *, title: str) -> Work:
    def work(session: Session, on_progress: Callable[[int, str], None]) -> dict[str, int]:
        cfg = get_config_row(session)
        try:
            return import_path(
                session,
                Path(staged_dir),  # the whole batch → one series (each file a book)
                kind=kind,
                storage_root=storage_root,
                quality=cfg.quality,
                filename_pattern=cfg.filename_pattern,
                title=title,
                on_progress=on_progress,
            )
        finally:
            shutil.rmtree(staged_dir, ignore_errors=True)  # drop the staged uploads

    return work


async def start_upload_import(
    session: Session, files: list[UploadFile], kind: str, storage_root: Path
) -> TaskOut:
    """Validate + stage browser uploads into one temp dir, then import them as one series."""
    if not get_config_row(session).enabled:
        raise BadRequestError("local import is disabled")
    if kind not in _KINDS:
        raise BadRequestError(f"invalid kind: {kind!r}")
    if not files:
        raise BadRequestError("no files uploaded")
    names = [Path(file.filename or "").name for file in files]
    for name in names:
        if Path(name).suffix.lower() not in _UPLOAD_EXTS:
            raise BadRequestError("only .cbz / .zip uploads are supported")
    staged_dir = await _stage_uploads(files, storage_root)
    label = names[0] if len(names) == 1 else f"{len(names)} files"
    return queue.submit_task(
        "localimport",
        f"Importing {label}",
        _staged_import_work(str(staged_dir), kind, storage_root, title=_batch_title(names)),
    )
