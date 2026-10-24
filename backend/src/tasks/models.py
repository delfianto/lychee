"""Persisted worker preferences; operation/task history remains in memory."""

from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.persistence.base_model import Base, TimestampMixin


class TaskQueueConfig(Base, TimestampMixin):
    __tablename__ = "task_queue_config"
    __table_args__ = (
        CheckConstraint("download_workers BETWEEN 1 AND 10", name="ck_task_download_workers"),
        CheckConstraint("sync_workers BETWEEN 1 AND 10", name="ck_task_sync_workers"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    download_workers: Mapped[int] = mapped_column(Integer, nullable=False)
    sync_workers: Mapped[int] = mapped_column(Integer, nullable=False)
