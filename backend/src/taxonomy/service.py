"""Taxonomy services — the unified tag/rating/demographic table with uses counts.

``uses`` is computed per category: genre/theme/content/format from ``series_tag``;
content_rating/demographic from the matching ``Series`` column. System rows
(content_rating/demographic) can't be deleted and their ``id``/``group`` are
never editable, but ``name`` can be renamed like any other tag (see
``notes/09-tag-aliases.md``: the sync key and the display label are separate
concerns).
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.catalog.models import Series
from src.core.exceptions import BadRequestError, ConflictError, NotFoundError
from src.core.schema import OffsetPage
from src.downloads.provider import get_metadata_provider
from src.tasks.queue import Work, queue
from src.tasks.schema import TaskOut
from src.taxonomy.models import Tag, TagAlias, series_tag
from src.taxonomy.schema import (
    AliasCreate,
    AliasOut,
    TaxonomyCreate,
    TaxonomyItemOut,
    TaxonomyUpdate,
)
from src.taxonomy.slug import slugify

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


def _uses(
    tag: Tag, tag_uses: dict[str, int], ratings: dict[str, int], demos: dict[str, int]
) -> int:
    if tag.group == "content_rating":
        return ratings.get(tag.id, 0)
    if tag.group == "demographic":
        return demos.get(tag.id, 0)
    return tag_uses.get(tag.id, 0)


def _to_item(
    tag: Tag, maps: tuple[dict[str, int], dict[str, int], dict[str, int]]
) -> TaxonomyItemOut:
    return TaxonomyItemOut(
        id=tag.id,
        name=tag.name,
        category=tag.group,
        uses=_uses(tag, *maps),
        enabled=tag.enabled,
        system=tag.system,
        aliases=[AliasOut(id=a.id, name=a.name, tag_id=a.tag_id) for a in tag.aliases],
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
    tags = session.scalars(stmt.order_by(Tag.name).offset(page * page_size).limit(page_size)).all()
    maps = _uses_maps(session)
    return OffsetPage[TaxonomyItemOut](
        items=[_to_item(tag, maps) for tag in tags], total=total, page=page, page_size=page_size
    )


def create_taxonomy(session: Session, data: TaxonomyCreate) -> TaxonomyItemOut:
    if data.category not in _USER_GROUPS:
        raise BadRequestError(f"cannot create taxonomy in category {data.category!r}")
    slug = base = slugify(data.name)
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
        # System rows lock id/group/deletability (below), but the display name
        # is cosmetic and freely renamable like any other tag — see
        # notes/09-tag-aliases.md's "sync key vs. display label" split.
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


def add_alias(session: Session, tag_id: str, data: AliasCreate) -> AliasOut:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise NotFoundError(f"taxonomy {tag_id!r} not found")
    slug = slugify(data.name)
    if session.get(Tag, slug) is not None:
        raise ConflictError(f"{data.name!r} is already a distinct tag, not an alias")
    existing = session.get(TagAlias, slug)
    if existing is not None:
        if existing.tag_id == tag_id:
            return AliasOut(id=existing.id, name=existing.name, tag_id=existing.tag_id)
        raise ConflictError(f"{data.name!r} is already an alias of {existing.tag_id!r}")
    alias = TagAlias(id=slug, name=data.name, tag_id=tag_id)
    session.add(alias)
    session.commit()
    return AliasOut(id=alias.id, name=alias.name, tag_id=alias.tag_id)


def remove_alias(session: Session, tag_id: str, alias_id: str) -> None:
    alias = session.get(TagAlias, alias_id)
    if alias is None or alias.tag_id != tag_id:
        raise NotFoundError(f"alias {alias_id!r} not found on tag {tag_id!r}")
    session.delete(alias)
    session.commit()


def _refresh_work() -> Work:
    def work(session: Session, _on_progress: Callable[[int, str], None]) -> dict[str, int]:
        provider = get_metadata_provider(_TAXONOMY_PROVIDER)
        if provider is None:
            raise BadRequestError(f"metadata provider {_TAXONOMY_PROVIDER!r} is not available")
        existing = set(session.scalars(select(Tag.id)))
        added = 0
        for name, group in provider.list_tags():
            slug = slugify(name)
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
