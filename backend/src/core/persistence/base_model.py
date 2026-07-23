"""Declarative base and the shared model mixin (id + timestamps)."""

from datetime import UTC, datetime

from nanoid import generate
from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def gen_id() -> str:
    """Compact, URL-safe 12-char id (nanoid)."""
    return generate(size=12)


def utc_now() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class BaseModel(Base):
    """Abstract base: short id + created/updated timestamps."""

    __abstract__ = True

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
