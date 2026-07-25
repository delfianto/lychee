"""Model registry — imports every ORM model so ``Base.metadata`` is complete.

Import this (``import src.models``) wherever the *whole* schema must be
registered up front: Alembic autogenerate and app startup (so relationship
string-references resolve). Feature modules still import their own models
directly; this is only an aggregation point.
"""

from src.catalog.models import (
    Book,
    Chapter,
    Library,
    Series,
    SeriesCredit,
    TitleVariant,
)
from src.collections.models import Collection, CollectionSeries
from src.downloads.models import DownloadTask
from src.integrations.models import ImportConfig, Provider, SyncState, Tracker
from src.progress.models import ReadingProgress
from src.taxonomy.models import Tag, series_tag

__all__ = [
    "Book",
    "Chapter",
    "Collection",
    "CollectionSeries",
    "DownloadTask",
    "ImportConfig",
    "Library",
    "Provider",
    "ReadingProgress",
    "Series",
    "SeriesCredit",
    "SyncState",
    "Tag",
    "TitleVariant",
    "Tracker",
    "series_tag",
]
