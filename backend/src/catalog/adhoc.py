"""Ad-hoc chapter reading (MangaDex / Neko style) backed by loose files in ``temp/``.

Allows reading any undownloaded remote chapter directly without adding a ``Book`` or
``Chapter`` row to the library. Pages are buffered in configurable windows
(``preload_pages``, 1–20) and stored as loose files under ``<library_or_storage>/temp/adhoc/``
which the library scanner explicitly ignores.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.models import Chapter, Library, ProviderChapter, Series
from src.catalog.remote_chapters import ensure_chapter_index
from src.catalog.schema import ChapterBufferOut, ChapterDetailOut
from src.core.config import settings
from src.core.exceptions import BadRequestError, NotFoundError
from src.downloads.provider import AdhocPageProvider, RemoteChapter, get_provider
from src.integrations.models import Provider as ProviderConfig
from src.library.paths import is_provider_path

MIN_PRELOAD_PAGES = 1
MAX_PRELOAD_PAGES = 20
DEFAULT_PRELOAD_PAGES = 4


def clamp_preload_pages(count: int) -> int:
    return max(MIN_PRELOAD_PAGES, min(MAX_PRELOAD_PAGES, int(count)))


def parse_adhoc_id(chapter_id: str) -> tuple[str, str] | None:
    """Parse ``adhoc:<series_id>:<provider_chapter_id>`` into ``(series_id, provider_chapter_id)``."""
    if not chapter_id.startswith("adhoc:"):
        return None
    parts = chapter_id.split(":", 2)
    if len(parts) != 3 or not parts[1] or not parts[2]:
        raise BadRequestError(f"invalid ad-hoc chapter id: {chapter_id!r}")
    return parts[1], parts[2]


def adhoc_temp_root(session: Session, series: Series) -> Path:
    """Resolve the ``temp`` root for ad-hoc loose files (never the main library tree)."""
    library = session.get(Library, series.library_id)
    if library is not None and library.path and not is_provider_path(library.path):
        lib_root = Path(library.path)
        if lib_root.is_dir():
            return lib_root / "temp"
    manga_libs = list(
        session.scalars(
            select(Library)
            .where(Library.enabled.is_(True), Library.kind == "manga")
            .order_by(Library.created_at, Library.id)
        )
    )
    for candidate in manga_libs:
        if candidate.path and not is_provider_path(candidate.path):
            root = Path(candidate.path)
            if root.is_dir():
                return root / "temp"
    return Path(settings.storage_path) / "temp"


def adhoc_chapter_dir(session: Session, series: Series, provider_chapter_id: str) -> Path:
    directory = adhoc_temp_root(session, series) / "adhoc" / series.id / provider_chapter_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _resolve_remote_chapter(
    session: Session, series_id: str, provider_chapter_id: str
) -> tuple[Series, ProviderChapter]:
    series = session.get(Series, series_id)
    if series is None:
        raise NotFoundError(f"series {series_id!r} not found")
    row = session.scalar(
        select(ProviderChapter).where(
            ProviderChapter.series_id == series_id,
            ProviderChapter.provider_chapter_id == provider_chapter_id,
        )
    )
    if row is None:
        ensure_chapter_index(session, series_id)
        row = session.scalar(
            select(ProviderChapter).where(
                ProviderChapter.series_id == series_id,
                ProviderChapter.provider_chapter_id == provider_chapter_id,
            )
        )
    if row is None:
        raise NotFoundError(f"remote chapter {provider_chapter_id!r} not found")
    return series, row


def _find_loose_page(directory: Path, page_num: int) -> Path | None:
    prefix = f"{page_num:04d}."
    for entry in sorted(directory.iterdir()) if directory.is_dir() else []:
        if entry.is_file() and entry.name.startswith(prefix):
            return entry
    return None


def _read_meta_count(directory: Path) -> int | None:
    meta_file = directory / "meta.json"
    if not meta_file.is_file():
        return None
    try:
        data = json.loads(meta_file.read_text())
        count = data.get("pageCount")
        return int(count) if isinstance(count, int) and count > 0 else None
    except OSError, ValueError, TypeError:
        return None


def _write_meta_count(directory: Path, page_count: int) -> None:
    meta_file = directory / "meta.json"
    meta_file.write_text(json.dumps({"pageCount": page_count}))


def _buffer_remote_window(
    session: Session,
    series: Series,
    remote_row: ProviderChapter,
    *,
    start_page: int = 1,
    preload_pages: int = DEFAULT_PRELOAD_PAGES,
) -> tuple[int, list[int]]:
    provider_id = remote_row.provider or series.provider or "mangadex"
    provider = get_provider(provider_id)
    if provider is None:
        raise BadRequestError(f"provider {provider_id!r} is not available")
    config = session.get(ProviderConfig, provider_id)
    data_saver = config.data_saver if config else False

    directory = adhoc_chapter_dir(session, series, remote_row.provider_chapter_id)
    count = clamp_preload_pages(preload_pages)
    first = max(1, int(start_page))

    remote = RemoteChapter(
        provider_chapter_id=remote_row.provider_chapter_id,
        number=remote_row.number or "1",
        volume=remote_row.volume,
        title=remote_row.title,
        language=remote_row.language,
        group_name=remote_row.group_name,
        published_at=remote_row.published_at.isoformat() if remote_row.published_at else None,
    )

    cached_total = _read_meta_count(directory)
    if cached_total is not None:
        if first > cached_total:
            return cached_total, []
        last = min(cached_total, first + count - 1)
        if all(_find_loose_page(directory, p) is not None for p in range(first, last + 1)):
            return cached_total, list(range(first, last + 1))

    if isinstance(provider, AdhocPageProvider):
        total, buffered = provider.fetch_adhoc_pages(
            remote,
            directory,
            start_page=first,
            count=count,
            data_saver=data_saver,
        )
        if total <= 0:
            raise NotFoundError("provider returned no pages for chapter")
        _write_meta_count(directory, total)
        return total, buffered

    pages = provider.fetch_pages(remote, data_saver=data_saver)
    total = len(pages)
    if total <= 0:
        raise NotFoundError("provider returned no pages for chapter")
    _write_meta_count(directory, total)
    if first > total:
        return total, []
    last = min(total, first + count - 1)
    buffered: list[int] = []
    for page_num in range(first, last + 1):
        target = _find_loose_page(directory, page_num) or (directory / f"{page_num:04d}.jpg")
        if not target.is_file():
            target.write_bytes(pages[page_num - 1])
        buffered.append(page_num)
    return total, buffered


def buffer_chapter(
    session: Session,
    chapter_id: str,
    *,
    start_page: int = 1,
    preload_pages: int = DEFAULT_PRELOAD_PAGES,
) -> ChapterBufferOut:
    """Buffer ``preload_pages`` starting at ``start_page`` into ``temp/adhoc/``."""
    count = clamp_preload_pages(preload_pages)
    first = max(1, int(start_page))
    parsed = parse_adhoc_id(chapter_id)
    if parsed is None:
        local = session.get(Chapter, chapter_id)
        if local is None:
            raise NotFoundError(f"chapter {chapter_id!r} not found")
        last = min(local.page_count, first + count - 1)
        buffered = list(range(first, last + 1)) if first <= local.page_count else []
        return ChapterBufferOut(
            chapter_id=local.id,
            page_count=local.page_count,
            buffered_pages=buffered,
        )

    series_id, provider_chapter_id = parsed
    series, remote_row = _resolve_remote_chapter(session, series_id, provider_chapter_id)
    total, buffered = _buffer_remote_window(
        session,
        series,
        remote_row,
        start_page=first,
        preload_pages=count,
    )
    return ChapterBufferOut(
        chapter_id=f"adhoc:{series.id}:{remote_row.provider_chapter_id}",
        page_count=total,
        buffered_pages=buffered,
    )


def get_adhoc_chapter_detail(
    session: Session,
    chapter_id: str,
    *,
    preload_pages: int = DEFAULT_PRELOAD_PAGES,
) -> ChapterDetailOut:
    parsed = parse_adhoc_id(chapter_id)
    if parsed is None:
        raise NotFoundError(f"chapter {chapter_id!r} not found")
    series_id, provider_chapter_id = parsed
    series, remote_row = _resolve_remote_chapter(session, series_id, provider_chapter_id)
    total, _ = _buffer_remote_window(
        session,
        series,
        remote_row,
        start_page=1,
        preload_pages=clamp_preload_pages(preload_pages),
    )
    return ChapterDetailOut(
        id=f"adhoc:{series.id}:{remote_row.provider_chapter_id}",
        series_id=series.id,
        volume=remote_row.volume,
        number=remote_row.number or "",
        title=remote_row.title,
        group=remote_row.group_name,
        language=remote_row.language,
        page_count=total,
        comments=0,
        read=False,
        uploaded_at=remote_row.published_at or remote_row.created_at,
    )


def read_adhoc_page(
    session: Session,
    chapter_id: str,
    page_num: int,
    *,
    preload_pages: int = DEFAULT_PRELOAD_PAGES,
) -> tuple[bytes, str]:
    parsed = parse_adhoc_id(chapter_id)
    if parsed is None:
        raise NotFoundError(f"chapter {chapter_id!r} not found")
    series_id, provider_chapter_id = parsed
    series, remote_row = _resolve_remote_chapter(session, series_id, provider_chapter_id)
    directory = adhoc_chapter_dir(session, series, provider_chapter_id)
    total = _read_meta_count(directory)
    loose = _find_loose_page(directory, page_num)
    if loose is None or total is None:
        total, _ = _buffer_remote_window(
            session,
            series,
            remote_row,
            start_page=max(1, page_num),
            preload_pages=clamp_preload_pages(preload_pages),
        )
        loose = _find_loose_page(directory, page_num)
    if not 1 <= page_num <= total or loose is None:
        raise NotFoundError(f"page {page_num} out of range (1–{total})")
    return loose.read_bytes(), loose.name
