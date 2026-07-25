"""Taxonomy services — the unified tag/rating/demographic table with uses counts.

``uses`` is computed per category: genre/theme/content/format from ``series_tag``;
content_rating/demographic from the matching ``Series`` column. System rows
(content_rating/demographic) have read-only names and can't be deleted.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.catalog.models import Series
from src.core.exceptions import BadRequestError, NotFoundError
from src.core.schema import OffsetPage
from src.downloads.provider import get_metadata_provider
from src.tasks.queue import Work, queue
from src.tasks.schema import TaskOut
from src.taxonomy.models import Tag, series_tag
from src.taxonomy.schema import TaxonomyCreate, TaxonomyItemOut, TaxonomyUpdate

_USER_GROUPS = {"genre", "theme", "content", "format"}
_TAXONOMY_PROVIDER = "mangadex"


def _uses_maps(session: Session) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    tag_uses = {
        str(tid): int(n)
        for tid, n in session.execute(
            select(series_tag.c.tag_id, func.count()).group_by(series_tag.c.tag_id)
        ).all()
    }
    ratings = {
        str(rating): int(n)
        for rating, n in session.execute(
            select(Series.content_rating, func.count()).group_by(Series.content_rating)
        ).all()
    }
    demographics = {
        str(demo): int(n)
        for demo, n in session.execute(
            select(Series.demographic, func.count()).group_by(Series.demographic)
        ).all()
    }
    return tag_uses, ratings, demographics


def _uses(tag: Tag, tag_uses: dict[str, int], ratings: dict[str, int], demos: dict[str, int]) -> int:
    if tag.group == "content_rating":
        return ratings.get(tag.id, 0)
    if tag.group == "demographic":
        return demos.get(tag.id, 0)
    return tag_uses.get(tag.id, 0)


def _to_item(tag: Tag, maps: tuple[dict[str, int], dict[str, int], dict[str, int]]) -> TaxonomyItemOut:
    return TaxonomyItemOut(
        id=tag.id,
        name=tag.name,
        category=tag.group,
        uses=_uses(tag, *maps),
        enabled=tag.enabled,
        system=tag.system,
    )


def list_taxonomy(
    session: Session, *, type_: str | None, q: str | None, page: int, page_size: int
) -> OffsetPage[TaxonomyItemOut]:
    page = max(0, page)
    page_size = max(1, min(page_size, 100))
    stmt = select(Tag)
    if type_:
        stmt = stmt.where(Tag.group == type_)
    if q:
        stmt = stmt.where(Tag.name.ilike(f"%{q}%"))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    tags = session.scalars(
        stmt.order_by(Tag.name).offset(page * page_size).limit(page_size)
    ).all()
    maps = _uses_maps(session)
    return OffsetPage[TaxonomyItemOut](
        items=[_to_item(tag, maps) for tag in tags], total=total, page=page, page_size=page_size
    )


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "tag"


def create_taxonomy(session: Session, data: TaxonomyCreate) -> TaxonomyItemOut:
    if data.category not in _USER_GROUPS:
        raise BadRequestError(f"cannot create taxonomy in category {data.category!r}")
    slug = base = _slugify(data.name)
    suffix = 2
    while session.get(Tag, slug) is not None:
        slug = f"{base}-{suffix}"
        suffix += 1
    tag = Tag(id=slug, name=data.name, group=data.category, enabled=True, system=False)
    session.add(tag)
    session.commit()
    return _to_item(tag, _uses_maps(session))


def update_taxonomy(session: Session, tag_id: str, data: TaxonomyUpdate) -> TaxonomyItemOut:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise NotFoundError(f"taxonomy {tag_id!r} not found")
    if data.name is not None:
        if tag.system:
            raise BadRequestError("system taxonomy names are read-only")
        tag.name = data.name
    if data.enabled is not None:
        tag.enabled = data.enabled
    session.commit()
    return _to_item(tag, _uses_maps(session))


def delete_taxonomy(session: Session, tag_id: str) -> None:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise NotFoundError(f"taxonomy {tag_id!r} not found")
    if tag.system:
        raise BadRequestError("system taxonomy rows cannot be deleted")
    session.delete(tag)
    session.commit()


def _refresh_work() -> Work:
    def work(session: Session, _on_progress: Callable[[int, str], None]) -> dict[str, int]:
        provider = get_metadata_provider(_TAXONOMY_PROVIDER)
        if provider is None:
            raise BadRequestError(f"metadata provider {_TAXONOMY_PROVIDER!r} is not available")
        existing = set(session.scalars(select(Tag.id)))
        added = 0
        for name, group in provider.list_tags():
            slug = _slugify(name)
            if slug not in existing:
                session.add(
                    Tag(id=slug, name=name, group=group if group in _USER_GROUPS else "genre")
                )
                existing.add(slug)
                added += 1
        return {"added": added}

    return work


def refresh_taxonomy(session: Session) -> TaskOut:
    """Add any tags missing from the provider's canonical list (idempotent; user edits and
    extra tags are kept). Runs on the task queue since it hits the network."""
    if get_metadata_provider(_TAXONOMY_PROVIDER) is None:
        raise BadRequestError(f"metadata provider {_TAXONOMY_PROVIDER!r} is not available")
    return queue.submit_task("taxonomy", "Refreshing tag taxonomy", _refresh_work())
