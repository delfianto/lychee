"""Chapter downloader → AVIF pipeline.

A download runs in two phases so it can be paused and resumed:

* :func:`plan_downloads` lists the series' remote chapters and inserts one
  ``queued`` :class:`DownloadTask` per pending chapter, stashing the remote
  chapter in ``remote_json`` so it can be fetched later.
* :func:`run_download_queue` drains those rows one at a time — for each, fetch
  page bytes from the provider, encode each to AVIF (discarding the original),
  pack them into the **manga library** as
  ``{Series Title}/Vol.XX/Ch.YY.cbz``, and create the Chapter.

Downloads require an enabled ``kind=manga`` library with a real filesystem path.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from src.catalog.media import generate_series_cover, write_series_cover
from src.catalog.models import Book, Chapter, Library, Series
from src.core.exceptions import BadRequestError
from src.core.logging import get_logger
from src.downloads.cancel import DownloadCancelled, check_cancelled, clear_cancel, is_cancelled
from src.downloads.models import DownloadTask
from src.downloads.provider import Provider, RemoteChapter, get_provider
from src.media.containers import write_cbz
from src.media.encode_pool import encode_pages
from src.media.thumbnails import ThumbnailStore

logger = get_logger(__name__)

# Characters illegal on common filesystems (Windows + POSIX reserved).
_UNSAFE_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def reclaim_orphaned_downloads(session: Session) -> int:
    """Re-queue any ``downloading`` rows left behind by a killed worker. Returns count."""
    result = cast(
        CursorResult[Any],
        session.execute(
            update(DownloadTask)
            .where(DownloadTask.status == "downloading")
            .values(status="queued", progress=0, error=None, phase=None, detail=None)
        ),
    )
    session.commit()
    count = int(result.rowcount or 0)
    if count:
        logger.info("reclaimed_orphaned_downloads", count=count)
    return count


def resolve_manga_library(session: Session) -> Library:
    """Return the first enabled manga library with a real on-disk root.

    Raises :class:`BadRequestError` when none is configured — downloads must not
    fall back to a hidden ``storage/downloads`` folder.
    """
    libraries = list(
        session.scalars(
            select(Library)
            .where(Library.enabled.is_(True), Library.kind == "manga")
            .order_by(Library.created_at, Library.id)
        )
    )
    for library in libraries:
        path = library.path or ""
        if path.startswith(("mangadex://", "http://", "https://")):
            continue
        root = Path(path)
        if root.is_dir():
            return library
        # Path configured but missing — create it so a fresh library works immediately.
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("manga_library_mkdir_failed", path=path, error=str(exc))
            continue
        if root.is_dir():
            return library
    raise BadRequestError(
        "No manga library configured. Add an enabled manga library in Settings before downloading."
    )


def _safe_fs_name(name: str, *, fallback: str = "Untitled") -> str:
    cleaned = _UNSAFE_FS.sub("", name).strip(" .")
    # Collapse runs of whitespace.
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:200] if cleaned else fallback


def _series_dir_name(series: Series) -> str:
    """Human-readable series folder name (not the nanoid id)."""
    # Reuse an existing single-segment human path_rel when it isn't just the bare id.
    if series.path_rel and "/" not in series.path_rel.strip("/"):
        candidate = series.path_rel.strip("/")
        if candidate and candidate != series.id:
            return _safe_fs_name(candidate, fallback=_safe_fs_name(series.title))
    return _safe_fs_name(series.title, fallback=series.id)


def _volume_dir_name(volume: int | None) -> str:
    if volume is None:
        return "No Volume"
    return f"Vol.{volume:02d}"


def _chapter_file_name(number: str, title: str | None = None) -> str:
    base = f"Ch.{number}"
    if title:
        base = f"{base} - {_safe_fs_name(title)}"
    return f"{base}.cbz"


def chapter_path_rel(series: Series, remote: RemoteChapter) -> str:
    """Relative path under the manga library: ``Series Name/Vol.XX/Ch.YY.cbz``."""
    return "/".join(
        [
            _series_dir_name(series),
            _volume_dir_name(remote.volume),
            _chapter_file_name(remote.number, remote.title),
        ]
    )


def bind_series_to_manga_library(session: Session, series: Series, library: Library) -> None:
    """Point the series at the manga library with a human-readable folder name."""
    folder = _series_dir_name(series)
    if series.library_id != library.id:
        series.library_id = library.id
    series.path_rel = folder
    session.flush()


def _number_sort(number: str) -> float | None:
    try:
        return float(number)
    except ValueError:
        return None


def _parse_published(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)  # handles the trailing 'Z' on 3.11+
    except ValueError:
        return None


def _download_chapter(
    session: Session,
    *,
    series: Series,
    library: Library,
    remote: RemoteChapter,
    provider: Provider,
    task: DownloadTask,
    data_saver: bool = False,
    on_progress: Callable[[int, str], None] | None = None,
) -> Chapter:
    label = task.chapter_label

    def _on_fetch(done: int, total: int) -> None:
        check_cancelled(series.id)
        task.phase = "fetching"
        task.detail = f"{done}/{total}"
        task.progress = int(done / max(total, 1) * 50)
        if on_progress is not None:
            on_progress(task.progress, f"Fetching {label} ({done}/{total})")
        session.commit()

    task.phase = "fetching"
    task.detail = None
    task.progress = 0
    session.commit()

    pages = provider.fetch_pages(remote, data_saver=data_saver, on_page=_on_fetch)
    check_cancelled(series.id)

    rel = chapter_path_rel(series, remote)
    dest = Path(library.path) / rel
    total = len(pages) or 1

    def _on_encode(done: int) -> None:
        check_cancelled(series.id)
        task.phase = "encoding"
        task.detail = f"{done}/{total}"
        task.progress = 50 + int(done / total * 50)
        if on_progress is not None:
            on_progress(task.progress, f"Encoding {label} ({done}/{total})")
        session.commit()

    task.phase = "encoding"
    task.detail = f"0/{total}"
    session.commit()

    # content-aware AVIF (discard original), possibly fanned across the encode pool,
    # packed into a stored CBZ
    page_count, size = write_cbz(dest, encode_pages(pages), on_page=_on_encode)

    book = Book(
        series_id=series.id,
        library_id=library.id,
        path_rel=rel,
        content_kind="cbz",
        file_size=size,
        page_count=page_count,
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        series_id=series.id,
        book_id=book.id,
        volume=remote.volume,
        number=remote.number,
        number_sort=_number_sort(remote.number),
        title=remote.title,
        language=remote.language,
        group_name=remote.group_name,
        source_uploaded_at=_parse_published(remote.published_at),
        page_count=len(pages),
        provider=provider.id,
        provider_chapter_id=remote.provider_chapter_id,
    )
    session.add(chapter)
    session.flush()
    task.chapter_id = chapter.id
    task.size_bytes = size
    task.phase = None
    task.detail = None
    return chapter


def plan_downloads(
    session: Session,
    series: Series,
    provider: Provider,
    *,
    language: str = "en",
    limit: int | None = None,
    provider_chapter_ids: list[str] | None = None,
) -> int:
    """Insert one ``queued`` DownloadTask per pending remote chapter and return the
    count added. A chapter is pending when it is neither already in the library nor
    already carried by a live (queued/downloading/paused) row, so re-planning a
    partially-finished or paused series is a safe no-op for what's in flight.

    When ``provider_chapter_ids`` is set, only those remote chapters are considered.
    """
    remotes = provider.list_chapters(series.provider_series_id or "", language=language)
    # Keep the remote index warm whenever we plan downloads.
    try:
        from src.catalog.remote_chapters import upsert_provider_chapters

        _ = upsert_provider_chapters(session, series, remotes, provider=provider.id)
    except Exception:  # noqa: BLE001 - planning must not fail on index write
        pass
    local = set(session.scalars(select(Chapter.number).where(Chapter.series_id == series.id)))
    local_pids = set(
        session.scalars(
            select(Chapter.provider_chapter_id).where(
                Chapter.series_id == series.id, Chapter.provider_chapter_id.is_not(None)
            )
        )
    )
    in_flight = {
        row.chapter_label
        for row in session.scalars(
            select(DownloadTask).where(
                DownloadTask.series_id == series.id,
                DownloadTask.status.in_(("queued", "downloading", "paused")),
            )
        )
    }
    in_flight_pids: set[str] = set()
    for row in session.scalars(
        select(DownloadTask).where(
            DownloadTask.series_id == series.id,
            DownloadTask.status.in_(("queued", "downloading", "paused")),
        )
    ):
        remote_json = row.remote_json or {}
        pid = remote_json.get("provider_chapter_id")
        if isinstance(pid, str):
            in_flight_pids.add(pid)

    want = set(provider_chapter_ids) if provider_chapter_ids is not None else None
    pending = [
        remote
        for remote in remotes
        if remote.number not in local
        and remote.provider_chapter_id not in local_pids
        and (want is None or remote.provider_chapter_id in want)
    ]
    if limit is not None:
        pending = pending[:limit]

    queued = 0
    for remote in pending:
        label = f"Ch. {remote.number}"
        if label in in_flight or remote.provider_chapter_id in in_flight_pids:
            continue
        session.add(
            DownloadTask(
                series_id=series.id,
                chapter_label=label,
                status="queued",
                provider=provider.id,
                remote_json=cast("dict[str, object]", asdict(remote)),
            )
        )
        queued += 1
    session.commit()
    return queued


def run_download_queue(
    session: Session,
    series_id: str,
    storage_root: Path,
    *,
    data_saver: bool = False,
    on_progress: Callable[[int, str], None] | None = None,
) -> int:
    """Drain the series' ``queued`` rows one at a time into the manga library."""
    clear_cancel(series_id)  # fresh run isn't cancelled unless cancel-all fires mid-flight
    series = session.get(Series, series_id)
    if series is None:
        return 0
    provider = get_provider(series.provider or "")
    if provider is None:
        return 0
    library = resolve_manga_library(session)
    bind_series_to_manga_library(session, series, library)
    session.commit()
    store = ThumbnailStore(storage_root / "thumbnails")
    series_dir = Path(library.path) / _series_dir_name(series)

    processed = 0
    while True:
        if is_cancelled(series_id):
            break
        row = session.scalar(
            select(DownloadTask)
            .where(DownloadTask.series_id == series_id, DownloadTask.status == "queued")
            .order_by(DownloadTask.created_at)
        )
        if row is None:
            break
        row.status = "downloading"
        row.progress = 0
        row.phase = "fetching"
        row.detail = None
        row.error = None
        session.commit()  # claim the row — it shows as "downloading" in /api/downloads at once
        try:
            if not row.remote_json:
                raise ValueError("queued download is missing chapter data")
            remote = RemoteChapter(**cast("dict[str, Any]", row.remote_json))
            _download_chapter(
                session,
                series=series,
                library=library,
                remote=remote,
                provider=provider,
                task=row,
                data_saver=data_saver,
                on_progress=on_progress,
            )
            row.status = "done"
            row.progress = 100
            row.phase = None
            row.detail = None
        except DownloadCancelled:
            row.status = "failed"
            row.error = "cancelled"
            row.phase = None
            row.detail = None
            session.commit()
            break
        except Exception as exc:  # noqa: BLE001 - record failure on the row, keep draining
            row.status = "failed"
            row.error = str(exc)
            row.phase = None
            row.detail = None
        session.commit()  # persist the row's final status so the table settles
        if row.status == "done":
            # portable Cover.avif beside the series folder, then the derived grid thumbnail
            _ = write_series_cover(session, series_id, series_dir)
            _ = generate_series_cover(session, store, series_id)
            processed += 1
            if on_progress is not None:
                on_progress(100, row.chapter_label)
        if is_cancelled(series_id):
            break
    clear_cancel(series_id)
    return processed
