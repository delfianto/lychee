"""Reading progress.

One row per chapter (single-user v1). ``unreadCount`` / ``lastReadChapter`` and
continue-reading are derived from these rows in queries; ``series_id`` is
denormalized so those rollups don't need a chapter join.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.persistence.base_model import BaseModel


class ReadingProgress(BaseModel):
    """This user's position in a chapter."""

    __tablename__ = "reading_progress"

    chapter_id: Mapped[str] = mapped_column(
        ForeignKey("chapter.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    series_id: Mapped[str] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), index=True, nullable=False
    )
    current_page: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # `updated_at` (from BaseModel) doubles as last-read time.


class ProviderReadingProgress(BaseModel):
    """Stable progress for a provider chapter, including ad-hoc reads with no local files."""

    __tablename__ = "provider_reading_progress"
    __table_args__ = (UniqueConstraint("series_id", "provider", "provider_chapter_id"),)

    series_id: Mapped[str] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_chapter_id: Mapped[str] = mapped_column(String(64), nullable=False)
    current_page: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
