"""Collection models — user-curated, ordered groupings of series (the "Lists" UI)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.persistence.base_model import Base, BaseModel

if TYPE_CHECKING:
    from src.catalog.models import Series


class Collection(BaseModel):
    """A named list of series."""

    __tablename__ = "collection"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

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
