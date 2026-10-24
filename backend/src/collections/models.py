"""Collection models — user-curated, ordered groupings of series (the "Lists" UI)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.persistence.base_model import Base, BaseModel

if TYPE_CHECKING:
    from src.catalog.models import Series


class Collection(BaseModel):
    """A named list of series."""

    __tablename__ = "collection"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Persist the list type even when its last work is removed.
    kind: Mapped[str] = mapped_column(
        String(16), default="manga", server_default="manga", nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Provider linkage for synced lists (e.g. a MangaDex custom list); null = a local list.
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_list_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    provider_owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    visibility: Mapped[str | None] = mapped_column(String(16), nullable=True)
    provider_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owned: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    followed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    entries: Mapped[list[CollectionSeries]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
        order_by="CollectionSeries.position",
    )


class CollectionSeries(Base):
    """Ordered membership of a series in a collection (association object)."""

    __tablename__ = "collection_series"

    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collection.id", ondelete="CASCADE"), primary_key=True
    )
    series_id: Mapped[str] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    collection: Mapped[Collection] = relationship(back_populates="entries")
    series: Mapped[Series] = relationship()
