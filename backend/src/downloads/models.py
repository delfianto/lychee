"""Download-task model — one queued/active/finished chapter download."""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.persistence.base_model import BaseModel


class DownloadTask(BaseModel):
    """One chapter download tracked in the Downloads tab.

    A download is planned as one row per pending chapter (``status="queued"``,
    carrying the remote chapter in ``remote_json`` so it can be fetched later); a
    background runner processes queued rows one at a time. Pause/resume flip a row
    between ``queued`` and ``paused`` — checked cooperatively at chapter boundaries.
    """

    __tablename__ = "download_task"

    series_id: Mapped[str | None] = mapped_column(
        ForeignKey("series.id", ondelete="SET NULL"), index=True, nullable=True
    )
    chapter_id: Mapped[str | None] = mapped_column(
        ForeignKey("chapter.id", ondelete="SET NULL"), nullable=True
    )
    chapter_label: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. "Ch. 151"
    # queued | downloading | paused | done | failed
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0–100
    # fetching | encoding while status=downloading; null otherwise
    phase: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # e.g. "12/40" pages within the current phase
    detail: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # What to download, so a queued/paused row survives to be fetched later.
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    remote_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
