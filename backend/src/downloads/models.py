"""Download-task model — one queued/active/finished chapter download."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.persistence.base_model import BaseModel


class DownloadTask(BaseModel):
    """A chapter (or whole-series) download tracked in the Downloads tab."""

    __tablename__ = "download_task"

    series_id: Mapped[str | None] = mapped_column(
        ForeignKey("series.id", ondelete="SET NULL"), index=True, nullable=True
    )
    chapter_id: Mapped[str | None] = mapped_column(
        ForeignKey("chapter.id", ondelete="SET NULL"), nullable=True
    )
    chapter_label: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. "Ch. 151"
    # downloading | queued | paused | done | failed
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0–100
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
