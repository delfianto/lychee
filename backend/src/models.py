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
    ProviderChapter,
    Series,
    SeriesCredit,
    TitleVariant,
)
from src.collections.models import Collection, CollectionSeries
from src.downloads.models import DownloadTask
from src.integrations.models import ImportConfig, Provider, SyncState, Tracker
from src.media.models import ImageProcessingConfig, ThumbnailConfig
from src.progress.models import ProviderReadingProgress, ReadingProgress
from src.tasks.models import TaskQueueConfig
from src.taxonomy.models import Tag, series_tag

__all__ = [
    "Book",
    "Chapter",
    "Collection",
    "CollectionSeries",
    "DownloadTask",
    "ImportConfig",
    "ImageProcessingConfig",
    "Library",
    "Provider",
    "ProviderChapter",
    "ReadingProgress",
    "ProviderReadingProgress",
    "Series",
    "SeriesCredit",
    "SyncState",
    "TaskQueueConfig",
    "Tag",
    "TitleVariant",
    "ThumbnailConfig",
    "Tracker",
    "series_tag",
]
