"""Map provider metadata onto the Series model.

Overwrites catalog fields from a provider's ``SeriesMetadata``, except any listed
in ``series.locked_fields_json`` (user edits win). Reconciles authors/artists into
``SeriesCredit``, alt titles into ``TitleVariant`` (both delete-orphan, so the
collections are just reassigned), and tags into the ``Tag`` taxonomy.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.catalog.models import Series, SeriesCredit, TitleVariant
from src.core.logging import get_logger
from src.downloads.provider import SeriesMetadata
from src.taxonomy.models import Tag, TagAlias
from src.taxonomy.slug import slugify

logger = get_logger(__name__)

# MangaDex originalLanguage → ISO-3166 origin country (best-effort).
_LANG_COUNTRY = {"ja": "jp", "ko": "kr", "zh": "cn", "zh-hk": "hk", "en": "us"}


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
        resolved = resolve_tag_id(session, meta.content_rating, "content_rating")
        if resolved is None:
            logger.warning(
                "content_rating_unresolved", series_id=series.id, raw=meta.content_rating
            )
        else:
            series.content_rating = resolved
    if unlocked("demographic") and meta.demographic:
        resolved = resolve_tag_id(session, meta.demographic, "demographic")
        if resolved is None:
            logger.warning("demographic_unresolved", series_id=series.id, raw=meta.demographic)
        else:
            series.demographic = resolved
    if unlocked("origin_country") and meta.original_language:
        series.origin_country = _LANG_COUNTRY.get(meta.original_language.lower())
    if unlocked("rating"):
        series.rating = meta.community_rating
    if unlocked("total_chapters"):
        series.total_chapters = meta.total_chapters
    if unlocked("cover") and fetch_covers and meta.cover_url:
        series.cover_source = meta.cover_url
    if unlocked("credits"):
        # Explicit delete-then-insert avoids SQLAlchemy INSERT-before-DELETE order
        # tripping UNIQUE(series_id, name, role) when re-applying the same credits.
        _ = session.execute(delete(SeriesCredit).where(SeriesCredit.series_id == series.id))
        session.flush()
        series.credits = _build_credits(series.id, meta)
    if unlocked("tags"):
        series.tags = reconcile_tags(session, meta.tags)
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
    """Build credits, de-duplicating identical (name, role) pairs from the provider."""
    credits: list[SeriesCredit] = []
    seen: set[tuple[str, str]] = set()
    for role, names in (("author", meta.authors), ("artist", meta.artists)):
        for name in names:
            key = (name, role)
            if key in seen:
                continue
            seen.add(key)
            credits.append(
                SeriesCredit(
                    series_id=series_id,
                    name=name,
                    role=role,
                    position=len([c for c in credits if c.role == role]),
                )
            )
    return credits


def reconcile_tags(session: Session, tags: list[tuple[str, str]]) -> list[Tag]:
    """Match each (name, group) to an existing Tag (by slug, name, or alias); create if missing."""
    known = list(session.scalars(select(Tag)))
    by_slug = {tag.id: tag for tag in known}
    by_name = {tag.name.lower(): tag for tag in known}
    by_alias = {alias.id: alias.tag for alias in session.scalars(select(TagAlias))}
    result: list[Tag] = []
    seen: set[str] = set()
    for name, group in tags:
        slug = slugify(name)
        tag = by_slug.get(slug) or by_name.get(name.lower()) or by_alias.get(slug)
        if tag is None:
            tag = Tag(id=slug, name=name, group=group or "genre")
            session.add(tag)
            by_slug[slug] = tag
            by_name[name.lower()] = tag
        if tag.id not in seen:
            seen.add(tag.id)
            result.append(tag)
    return result


def resolve_tag_id(session: Session, raw: str, group: str) -> str | None:
    """Resolve free text to a canonical Tag id in ``group`` (by slug or alias).

    For the closed content_rating/demographic enums: unlike ``reconcile_tags``,
    an unresolved value must never fall back to creating a new Tag — the caller
    is expected to warn and skip the field instead of writing an unknown value.
    """
    slug = slugify(raw)
    tag = session.get(Tag, slug)
    if tag is not None and tag.group == group:
        return slug
    alias = session.get(TagAlias, slug)
    if alias is not None and alias.tag.group == group:
        return alias.tag_id
    return None
