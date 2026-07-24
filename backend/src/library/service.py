"""Library services — CRUD and scan orchestration (writes commit here)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.catalog.models import Library, Series
from src.core.exceptions import BadRequestError, NotFoundError
from src.ingest.scanner import ScanSummary, scan_library
from src.library.schema import LibraryCreate, LibraryOut, LibraryUpdate, ScanResultOut

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


def _summary_out(summary: ScanSummary) -> ScanResultOut:
    return ScanResultOut(
        series_added=summary.series_added,
        books_added=summary.books_added,
        books_updated=summary.books_updated,
        books_removed=summary.books_removed,
    )


def scan_one(session: Session, library_id: str) -> ScanResultOut:
    summary = scan_library(session, _get(session, library_id))
    session.commit()
    return _summary_out(summary)


def scan_all(session: Session) -> ScanResultOut:
    total = ScanSummary()
    for library in session.scalars(select(Library).where(Library.enabled.is_(True))):
        summary = scan_library(session, library)
        total.series_added += summary.series_added
        total.books_added += summary.books_added
        total.books_updated += summary.books_updated
        total.books_removed += summary.books_removed
    session.commit()
    return _summary_out(total)
