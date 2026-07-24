"""Test data factory — insert catalog rows for API/repository tests."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session
from src.catalog.models import Book, Chapter, Library, Series, SeriesCredit
from src.progress.models import ReadingProgress
from src.taxonomy.models import series_tag


def ensure_library(session: Session, *, kind: str = "mixed") -> Library:
    library = session.scalar(select(Library).where(Library.name == "Test Library"))
    if library is None:
        library = Library(name="Test Library", path="/tmp/test", kind=kind)
        session.add(library)
        session.flush()
    return library


def make_series(
    session: Session,
    *,
    title: str,
    kind: str = "manga",
    favorite: bool = False,
    library_status: str = "none",
    status: str = "ongoing",
    content_rating: str = "safe",
    demographic: str = "none",
    rating: float | None = None,
    year: int | None = None,
    tag_ids: Sequence[str] = (),
    authors: Sequence[str] = ("Author Name",),
    artists: Sequence[str] = ("Artist Name",),
    chapter_count: int = 0,
    unread: int = 0,
    source: str | None = None,
    characters: list[str] | None = None,
    image_count: int | None = None,
) -> Series:
    """Insert a Series (+ credits, tags, chapters, and read-progress) and return it."""
    library = ensure_library(session)
    series = Series(
        library_id=library.id,
        kind=kind,
        title=title,
        sort_title=title.lower(),
        favorite=favorite,
        library_status=library_status,
        status=status,
        content_rating=content_rating,
        demographic=demographic,
        rating=rating,
        year=year,
        source=source,
        characters_json=characters,
        image_count=image_count,
    )
    session.add(series)
    session.flush()

    for i, name in enumerate(authors):
        session.add(SeriesCredit(series_id=series.id, name=name, role="author", position=i))
    for i, name in enumerate(artists):
        session.add(SeriesCredit(series_id=series.id, name=name, role="artist", position=i))
    for tag_id in tag_ids:
        _ = session.execute(series_tag.insert().values(series_id=series.id, tag_id=tag_id))

    if chapter_count:
        book = Book(
            series_id=series.id,
            library_id=library.id,
            path_rel=f"{title}/",
            content_kind="image_dir",
            page_count=1,
        )
        session.add(book)
        session.flush()
        read_through = chapter_count - unread
        for n in range(1, chapter_count + 1):
            chapter = Chapter(
                series_id=series.id,
                book_id=book.id,
                number=str(n),
                number_sort=float(n),
                language="en",
                page_count=1,
            )
            session.add(chapter)
            session.flush()
            if n <= read_through:
                session.add(
                    ReadingProgress(
                        chapter_id=chapter.id,
                        series_id=series.id,
                        completed=True,
                        current_page=1,
                    )
                )
    session.flush()
    return series
