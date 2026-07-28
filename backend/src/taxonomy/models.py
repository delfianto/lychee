"""Taxonomy models.

One unified ``Tag`` table backs the whole Settings → Content table. ``group``
spans the four series-linked groups (``genre|theme|content|format``, joined to
series via ``series_tag``) **and** the two fixed enum groups
(``content_rating|demographic``, whose rows are ``system`` — not deletable,
``id``/``group`` never editable, only ``name``/``enabled`` can change).
``Series.content_rating`` / ``Series.demographic`` reference those system tag
ids by value.

``TagAlias`` rows are a pure ingestion/sync-key resolution aid (see
``notes/09-tag-aliases.md``) — free text (a provider's own naming, slang,
abbreviations) that should resolve to an existing ``Tag`` instead of minting a
duplicate. They're never displayed against a series; only the resolved
``Tag.name`` is.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    aliases: Mapped[list[TagAlias]] = relationship(
        back_populates="tag", cascade="all, delete-orphan"
    )


class TagAlias(Base, TimestampMixin):
    """An alternate name (slang, abbreviation, a provider's own naming) that
    resolves to a canonical Tag. Mirrors Tag's own id=slug / name=display split.
    """

    __tablename__ = "tag_alias"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # slug of the alias itself
    name: Mapped[str] = mapped_column(String(128), nullable=False)  # display form, e.g. "Hentai"
    tag_id: Mapped[str] = mapped_column(
        ForeignKey("tag.id", ondelete="CASCADE"), index=True, nullable=False
    )

    tag: Mapped[Tag] = relationship(back_populates="aliases")
