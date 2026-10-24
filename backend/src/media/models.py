"""Persisted media storage preferences."""

from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.persistence.base_model import Base, TimestampMixin


class ThumbnailConfig(Base, TimestampMixin):
    __tablename__ = "thumbnail_config"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    path: Mapped[str | None] = mapped_column(String(4096), nullable=True)


class ImageProcessingConfig(Base, TimestampMixin):
    __tablename__ = "image_processing_config"
    __table_args__ = (
        CheckConstraint("conversion_workers BETWEEN 1 AND 64", name="ck_image_conversion_workers"),
        CheckConstraint("thumbnail_workers BETWEEN 1 AND 64", name="ck_image_thumbnail_workers"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    conversion_workers: Mapped[int] = mapped_column(Integer, nullable=False)
    thumbnail_workers: Mapped[int] = mapped_column(Integer, nullable=False)
