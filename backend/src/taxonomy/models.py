"""Taxonomy models.

One unified ``Tag`` table backs the whole Settings → Content table. ``group``
spans the four series-linked groups (``genre|theme|content|format``, joined to
series via ``series_tag``) **and** the two fixed enum groups
(``content_rating|demographic``, whose rows are ``system`` — name read-only, not
deletable, only ``enabled`` toggles). ``Series.content_rating`` /
``Series.demographic`` reference those system tag ids by value.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column

from src.core.persistence.base_model import Base, TimestampMixin

# Series ↔ genre/theme/content/format tags (m2m). The reverse (``Series.tags``)
# is the navigable side; tag "uses" counts come from queries, not a backref, so
# this side stays import-free (no catalog → taxonomy → catalog cycle).
series_tag = Table(
    "series_tag",
    Base.metadata,
    Column("series_id", ForeignKey("series.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base, TimestampMixin):
    """A taxonomy row. Id is a stable slug (matches the frontend's tag ids)."""

    __tablename__ = "tag"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # slug, no auto-gen
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # genre | theme | content | format | content_rating | demographic
    group: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
