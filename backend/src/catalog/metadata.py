"""Map provider metadata onto the Series model.

Overwrites catalog fields from a provider's ``SeriesMetadata``, except any listed
in ``series.locked_fields_json`` (user edits win). Reconciles authors/artists into
``SeriesCredit``, alt titles into ``TitleVariant`` (both delete-orphan, so the
collections are just reassigned), and tags into the ``Tag`` taxonomy.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.models import Series, SeriesCredit, TitleVariant
from src.downloads.provider import SeriesMetadata
from src.taxonomy.models import Tag

# MangaDex originalLanguage → ISO-3166 origin country (best-effort).
_LANG_COUNTRY = {"ja": "jp", "ko": "kr", "zh": "cn", "zh-hk": "hk", "en": "us"}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "tag"


def apply_metadata(
    session: Session, series: Series, meta: SeriesMetadata, *, fetch_covers: bool = True
) -> None:
    locked = set(series.locked_fields_json or [])

    def unlocked(field: str) -> bool:
        return field not in locked

    if unlocked("title"):
        series.title = meta.title
        series.sort_title = meta.title.lower()
        series.title_variants = _build_variants(series.id, meta)
    if unlocked("description") and meta.description is not None:
        series.description = meta.description
    if unlocked("status") and meta.status:
        series.status = meta.status
    if unlocked("year"):
        series.year = meta.year
    if unlocked("content_rating") and meta.content_rating:
        series.content_rating = meta.content_rating
    if unlocked("demographic") and meta.demographic:
        series.demographic = meta.demographic
    if unlocked("origin_country") and meta.original_language:
        series.origin_country = _LANG_COUNTRY.get(meta.original_language.lower())
    if unlocked("rating"):
        series.rating = meta.community_rating
    if unlocked("total_chapters"):
        series.total_chapters = meta.total_chapters
    if unlocked("cover") and fetch_covers and meta.cover_url:
        series.cover_source = meta.cover_url
    if unlocked("credits"):
        series.credits = _build_credits(series.id, meta)
    if unlocked("tags"):
        series.tags = _reconcile_tags(session, meta.tags)
    series.external_ids_json = meta.external_ids or None
    session.flush()


def _build_variants(series_id: str, meta: SeriesMetadata) -> list[TitleVariant]:
    variants = [
        TitleVariant(
            series_id=series_id,
            title=meta.title,
            language=meta.original_language or "",
            is_primary=True,
        )
    ]
    variants += [
        TitleVariant(series_id=series_id, title=title, language=language, is_primary=False)
        for language, title in meta.alt_titles
    ]
    return variants


def _build_credits(series_id: str, meta: SeriesMetadata) -> list[SeriesCredit]:
    credits = [
        SeriesCredit(series_id=series_id, name=name, role="author", position=position)
        for position, name in enumerate(meta.authors)
    ]
    credits += [
        SeriesCredit(series_id=series_id, name=name, role="artist", position=position)
        for position, name in enumerate(meta.artists)
    ]
    return credits


def _reconcile_tags(session: Session, tags: list[tuple[str, str]]) -> list[Tag]:
    """Match each (name, group) to an existing Tag (by slug or name); create if missing."""
    known = list(session.scalars(select(Tag)))
    by_slug = {tag.id: tag for tag in known}
    by_name = {tag.name.lower(): tag for tag in known}
    result: list[Tag] = []
    seen: set[str] = set()
    for name, group in tags:
        slug = _slug(name)
        tag = by_slug.get(slug) or by_name.get(name.lower())
        if tag is None:
            tag = Tag(id=slug, name=name, group=group or "genre")
            session.add(tag)
            by_slug[slug] = tag
            by_name[name.lower()] = tag
        if tag.id not in seen:
            seen.add(tag.id)
            result.append(tag)
    return result
