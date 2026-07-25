"""Catalog domain models.

Physical / logical split:

- **Book** — a physical container the scanner discovers (archive, image dir, or a
  downloaded AVIF set). Carries the on-disk identity: path, size, partial hash,
  page count. Move-tracking happens at this level via ``partial_hash`` +
  ``file_size`` and a soft ``deleted_at``.
- **Chapter** — the logical reading unit the API serves (``/api/chapters/{id}``):
  a book plus a page range, with the display metadata (volume, number, group,
  language). Manga/comics have chapters; a **gallery** ``Series`` has a single
  Book of images and *no* chapters (served via ``/api/series/{id}/images``).

Per-user state (``favorite``, ``library_status``, ``rating``) lives inline on
``Series`` — v1 is single-user. Derived values (``chapterCount``,
``unreadCount``, ``lastReadChapter``) are computed in queries, never stored.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.persistence.base_model import BaseModel

if TYPE_CHECKING:
    from src.taxonomy.models import Tag


class Library(BaseModel):
    """A registered root folder scanned for content (or a virtual download home)."""

    __tablename__ = "library"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    # manga | comic | gallery | mixed
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    options_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)

    series: Mapped[list[Series]] = relationship(
        back_populates="library", cascade="all, delete-orphan"
    )


class Series(BaseModel):
    """A title: manga/comic (has chapters) or gallery (has images)."""

    __tablename__ = "series"

    library_id: Mapped[str] = mapped_column(
        ForeignKey("library.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # manga | comic | gallery
    kind: Mapped[str] = mapped_column(String(16), index=True, nullable=False)

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    sort_title: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ongoing | completed | hiatus | cancelled
    status: Mapped[str] = mapped_column(String(16), default="ongoing", nullable=False)
    # safe | suggestive | erotica | mature (system Tag ids)
    content_rating: Mapped[str] = mapped_column(
        String(16), default="safe", index=True, nullable=False
    )
    # shonen | shojo | seinen | josei | none (system Tag ids)
    demographic: Mapped[str] = mapped_column(
        String(16), default="none", index=True, nullable=False
    )

    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origin_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)  # community 0–10
    user_rating: Mapped[float | None] = mapped_column(Float, nullable=True)  # this user's 1–10

    # Per-user state (single-user v1).
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    # none | reading | on_hold | dropped | plan_to_read | completed | re_reading
    library_status: Mapped[str] = mapped_column(
        String(16), default="none", index=True, nullable=False
    )

    total_chapters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Remote chapters not yet present locally, from the last sync.
    available_chapters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Physical binding — relative to the library root; null for download-only.
    path_rel: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cover_source: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Provider linkage for refresh/sync.
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_series_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # External site ids from the provider (al, mal, mu, …) for tracker matching.
    external_ids_json: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)

    # Gallery-only extras.
    image_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    characters_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    locked_fields_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    file_last_modified: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    library: Mapped[Library] = relationship(back_populates="series")
    credits: Mapped[list[SeriesCredit]] = relationship(
        back_populates="series",
        cascade="all, delete-orphan",
        order_by="SeriesCredit.position",
    )
    title_variants: Mapped[list[TitleVariant]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )
    books: Mapped[list[Book]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )
    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="series",
        cascade="all, delete-orphan",
        order_by="Chapter.number_sort",
    )
    tags: Mapped[list[Tag]] = relationship(secondary="series_tag")


class SeriesCredit(BaseModel):
    """An author or artist credited on a series (queryable — gallery artist filter)."""

    __tablename__ = "series_credit"
    __table_args__ = (UniqueConstraint("series_id", "name", "role", name="uq_series_credit"),)

    series_id: Mapped[str] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # author | artist
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    series: Mapped[Series] = relationship(back_populates="credits")


class TitleVariant(BaseModel):
    """A language-tagged title; ``Series.title`` is the denormalized display one."""

    __tablename__ = "title_variant"

    series_id: Mapped[str] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    # native | romanized | english | alt
    variant_type: Mapped[str] = mapped_column(String(16), default="alt", nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    series: Mapped[Series] = relationship(back_populates="title_variants")


class Book(BaseModel):
    """A physical container of pages (scanned file/dir or downloaded AVIF set)."""

    __tablename__ = "book"

    series_id: Mapped[str] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), index=True, nullable=False
    )
    library_id: Mapped[str] = mapped_column(
        ForeignKey("library.id", ondelete="CASCADE"), index=True, nullable=False
    )
    path_rel: Mapped[str] = mapped_column(String(1024), nullable=False)
    # cbz | zip | image_dir | avif_dir  (the reader's supported container kinds)
    content_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    partial_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_last_modified: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    series: Mapped[Series] = relationship(back_populates="books")
    chapters: Mapped[list[Chapter]] = relationship(back_populates="book")


class Chapter(BaseModel):
    """A logical reading unit: a page range within a Book, with display metadata."""

    __tablename__ = "chapter"

    series_id: Mapped[str] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), index=True, nullable=False
    )
    book_id: Mapped[str] = mapped_column(
        ForeignKey("book.id", ondelete="CASCADE"), index=True, nullable=False
    )
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    number: Mapped[str | None] = mapped_column(String(32), nullable=True)  # display, e.g. "45.5"
    number_sort: Mapped[float | None] = mapped_column(Float, index=True, nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    page_start: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_uploaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_chapter_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    series: Mapped[Series] = relationship(back_populates="chapters")
    book: Mapped[Book] = relationship(back_populates="chapters")
