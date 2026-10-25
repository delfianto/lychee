"""Shared catalog response mapping for library, list, download, and Home reads."""

from src.catalog.links import source_url
from src.catalog.repository import SeriesRow
from src.catalog.schema import SeriesOut, TagOut
from src.media.thumbnails import PREVIEW_VERSION


def cover_url(series_id: str) -> str:
    # Covers — provider art or local page — are downloaded once and served by our own
    # endpoint as cached AVIF thumbnails (never hotlinked).
    return f"/api/series/{series_id}/cover?v={PREVIEW_VERSION}"


def to_series_out(row: SeriesRow) -> SeriesOut:
    s = row.series
    return SeriesOut(
        id=s.id,
        title=s.title,
        cover_url=cover_url(s.id),
        authors=[c.name for c in s.credits if c.role == "author"],
        artists=[c.name for c in s.credits if c.role == "artist"],
        status=s.status,
        content_rating=s.content_rating,
        demographic=s.demographic,
        tags=[TagOut(id=t.id, name=t.name, group=t.group) for t in s.tags],
        chapter_count=row.chapter_count,
        unread_count=row.unread_count,
        year=s.year,
        description=s.description,
        last_read_chapter=row.last_read,
        total_chapters=s.total_chapters,
        origin_country=s.origin_country,
        rating=s.rating,
        user_rating=s.user_rating,
        favorite=s.favorite,
        kind=s.kind,
        image_count=s.image_count,
        source=s.source,
        characters=s.characters_json,
        library_status=s.library_status,
        provider=s.provider,
        source_url=source_url(s.provider, s.provider_series_id),
        available_chapters=s.available_chapters,
        chapters_synced_at=s.chapter_index_at,
    )
