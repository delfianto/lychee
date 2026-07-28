"""Library services — CRUD and scan orchestration (writes commit here)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.catalog import matching as catalog_matching
from src.catalog.media import warm_gallery_item_thumbs, warm_library_covers
from src.catalog.models import Library, Series
from src.core.exceptions import BadRequestError, NotFoundError
from src.core.logging import get_logger
from src.ingest.scanner import ScanSummary, scan_library
from src.library.schema import LibraryCreate, LibraryOut, LibraryUpdate
from src.media.thumbnails import ThumbnailStore
from src.tasks.queue import Work, queue
from src.tasks.schema import TaskOut

logger = get_logger(__name__)

_KINDS = {"manga", "comic", "gallery", "mixed"}


def _to_out(session: Session, library: Library) -> LibraryOut:
    count = (
        session.scalar(select(func.count(Series.id)).where(Series.library_id == library.id)) or 0
    )
    return LibraryOut(
        id=library.id,
        name=library.name,
        path=library.path,
        kind=library.kind,
        enabled=library.enabled,
        series_count=count,
        last_scan=library.last_scan_at,
    )


def _get(session: Session, library_id: str) -> Library:
    library = session.get(Library, library_id)
    if library is None:
        raise NotFoundError(f"library {library_id!r} not found")
    return library


def list_libraries(session: Session) -> list[LibraryOut]:
    libraries = session.scalars(select(Library).order_by(Library.created_at)).all()
    return [_to_out(session, lib) for lib in libraries]


def create_library(session: Session, data: LibraryCreate) -> LibraryOut:
    if data.kind not in _KINDS:
        raise BadRequestError(f"invalid kind: {data.kind!r}")
    library = Library(name=data.name, path=data.path, kind=data.kind)
    session.add(library)
    session.commit()
    session.refresh(library)
    return _to_out(session, library)


def update_library(session: Session, library_id: str, data: LibraryUpdate) -> LibraryOut:
    library = _get(session, library_id)
    if data.name is not None:
        library.name = data.name
    if data.path is not None:
        library.path = data.path
    if data.enabled is not None:
        library.enabled = data.enabled
    session.commit()
    return _to_out(session, library)


def delete_library(session: Session, library_id: str) -> None:
    session.delete(_get(session, library_id))
    session.commit()


def _summary_dict(summary: ScanSummary) -> dict[str, Any]:
    return {
        "seriesAdded": summary.series_added,
        "booksAdded": summary.books_added,
        "booksUpdated": summary.books_updated,
        "booksRemoved": summary.books_removed,
        "lycheeInfoApplied": summary.lychee_info_applied,
        "lycheeInfoWarnings": summary.lychee_info_warnings,
    }


def _thumbs_work(library_id: str, storage_root: Path) -> Work:
    """Background task: warm per-item gallery thumbs with its own 0–100% progress."""

    def work(session: Session, on_progress: Callable[[int, str], None]) -> dict[str, int]:
        library = _get(session, library_id)
        store = ThumbnailStore(storage_root / "thumbnails")
        on_progress(0, "Starting")
        # Series covers first (fast), then item thumbs.
        _ = warm_library_covers(session, store, library.id)
        on_progress(5, "Series covers done")
        n = warm_gallery_item_thumbs(session, store, library.id, on_progress=on_progress)
        return {"thumbsGenerated": n}

    return work


def _finish_scan_phases(
    session: Session,
    library: Library,
    storage_root: Path,
    on_progress: Callable[[int, str], None] | None = None,
) -> None:
    """Post-index: commit early, optional manga auto-match, cover warm, gallery thumbs task.

    Gallery item thumbs run as a **separate** ``thumbs`` task so the scan task can finish
    (catalog usable + UI refresh) while encodes show their own progress bar.
    """
    session.commit()

    if library.kind != "gallery":
        if on_progress is not None:
            on_progress(100, "Matching metadata")
        catalog_matching.auto_match_library(session, library.id)
        session.commit()

        if on_progress is not None:
            on_progress(100, "Warming covers")
        try:
            store = ThumbnailStore(storage_root / "thumbnails")
            _ = warm_library_covers(session, store, library.id)
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
            logger.exception("cover_warm_failed", library_id=library.id)
        return

    # Gallery: covers + item thumbs on a dedicated task with real 0–100 progress.
    _ = queue.submit(
        "thumbs",
        f"Thumbnails · {library.name}",
        _thumbs_work(library.id, storage_root),
    )


def _scan_one_work(library_id: str, storage_root: Path) -> Work:
    def work(session: Session, on_progress: Callable[[int, str], None]) -> dict[str, Any]:
        library = _get(session, library_id)
        summary = scan_library(session, library, on_progress=on_progress)
        _finish_scan_phases(session, library, storage_root, on_progress)
        return _summary_dict(summary)

    return work


def _scan_all_work(storage_root: Path) -> Work:
    def work(session: Session, on_progress: Callable[[int, str], None]) -> dict[str, Any]:
        total = ScanSummary()
        libraries = list(session.scalars(select(Library).where(Library.enabled.is_(True))))
        for index, library in enumerate(libraries, start=1):
            summary = scan_library(session, library)
            total.series_added += summary.series_added
            total.books_added += summary.books_added
            total.books_updated += summary.books_updated
            total.books_removed += summary.books_removed
            total.lychee_info_applied += summary.lychee_info_applied
            total.lychee_info_warnings.extend(summary.lychee_info_warnings)
            _finish_scan_phases(session, library, storage_root)
            on_progress(round(index / len(libraries) * 100) if libraries else 100, library.name)
        return _summary_dict(total)

    return work


def enqueue_scan_one(session: Session, library_id: str, storage_root: Path) -> TaskOut:
    """Validate the library exists (404 here), then run its scan on the task queue."""
    library = _get(session, library_id)
    return queue.submit_task(
        "scan", f"Scanning {library.name}", _scan_one_work(library_id, storage_root)
    )


def enqueue_scan_all(session: Session, storage_root: Path) -> TaskOut:
    return queue.submit_task("scan", "Scanning all libraries", _scan_all_work(storage_root))
