"""Persisted media storage preferences."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.persistence.base_model import Base, TimestampMixin


class ThumbnailConfig(Base, TimestampMixin):
    __tablename__ = "thumbnail_config"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    path: Mapped[str | None] = mapped_column(String(4096), nullable=True)
