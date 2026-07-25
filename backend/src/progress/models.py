"""Reading progress.

One row per chapter (single-user v1). ``unreadCount`` / ``lastReadChapter`` and
continue-reading are derived from these rows in queries; ``series_id`` is
denormalized so those rollups don't need a chapter join.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer
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
