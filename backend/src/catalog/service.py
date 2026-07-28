"""Catalog read services — parse query params and assemble API responses.

Series/chapter reads, feeds (updates, dashboard), search, and the DTO mappers.
Provider matching + metadata refresh live in ``catalog.matching``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog import matching as catalog_matching
from src.catalog import repository as repo
from src.catalog.metadata import reconcile_tags
from src.catalog.models import ProviderChapter, Series, SeriesCredit, TitleVariant
from src.catalog.remote_chapters import (
    download_status_map,
    ensure_chapter_index,
    local_by_number_lang,
    local_by_provider_id,
)
from src.catalog.repository import ChapterRow, SeriesFilters, SeriesRow, UpdateRow
from src.catalog.schema import (
    ChapterDetailOut,
    ChapterOut,
    DashboardOut,
    DashboardStats,
    LibrarySummaryOut,
    RecentUpdateOut,
    SeriesArtOut,
    SeriesOut,
    SeriesUpdate,
    TagOut,
    VolumeGroupOut,
)
from src.core.exceptions import BadRequestError, NotFoundError
from src.core.schema import Page
from src.ingest.lychee_info import LycheeInfoFile
from src.progress.models import ReadingProgress
from src.taxonomy.models import Tag
from src.trackers.sync import enqueue_push

_LIBRARY_STATUSES = {
    "none",
    "reading",
    "on_hold",
    "dropped",
    "plan_to_read",
    "completed",
    "re_reading",
}

# Allowed values for the enum-like metadata fields (mirrors the model comments).
_PUB_STATUSES = {"ongoing", "completed", "hiatus", "cancelled"}
_CONTENT_RATINGS = {"safe", "suggestive", "erotica", "pornographic", "explicit"}
_DEMOGRAPHICS = {"shonen", "shojo", "seinen", "josei", "none"}

_MAX_LIMIT = 100


def cover_url(series_id: str) -> str:
    # Covers — provider art or local page — are downloaded once and served by our own
    # endpoint as cached AVIF thumbnails (never hotlinked).
    return f"/api/series/{series_id}/cover"


def _csv(value: str | None) -> list[str]:
    return [part for part in value.split(",") if part] if value else []


def _parse_tags(tags: str | None) -> tuple[list[str], list[str]]:
    """Split a tag csv into (include, exclude); a leading ``-`` marks exclusion."""
    include: list[str] = []
    exclude: list[str] = []
    for raw in _csv(tags):
        (exclude if raw.startswith("-") else include).append(raw.removeprefix("-"))
    return include, exclude


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
        available_chapters=s.available_chapters,
        chapters_synced_at=s.chapter_index_at,
    )


def build_series_filters(
    *,
    kind: str | None = None,
    shelf: str | None = None,
    favorite: bool | None = None,
    q: str | None = None,
    tags: str | None = None,
    tag_mode: str = "and",
    ratings: str | None = None,
    demographics: str | None = None,
    pub_status: str | None = None,
    read_state: str | None = None,
    artist: str | None = None,
    source: str | None = None,
    sort: str = "recentlyAdded",
) -> SeriesFilters:
    include, exclude = _parse_tags(tags)
    return SeriesFilters(
        kind=kind,
        shelf=shelf,
        favorite=favorite,
        q=q,
        tags_include=include,
        tags_exclude=exclude,
        tag_mode=tag_mode,
        ratings=_csv(ratings),
        demographics=_csv(demographics),
        pub_status=_csv(pub_status),
        read_state=read_state,
        artist=artist,
        source=source,
        sort=sort,
    )


def list_series(
    session: Session, *, filters: SeriesFilters, cursor: str | None, limit: int
) -> Page[SeriesOut]:
    limit = max(1, min(limit, _MAX_LIMIT))
    rows, next_cursor = repo.list_series(session, filters, cursor=cursor, limit=limit)
    return Page[SeriesOut](items=[to_series_out(r) for r in rows], next_cursor=next_cursor)


def get_series(session: Session, series_id: str) -> SeriesOut:
    row = repo.get_series(session, series_id)
    if row is None:
        raise NotFoundError(f"series {series_id!r} not found")
    return to_series_out(row)


def _credit_rows(series_id: str, role: str, names: list[str]) -> list[SeriesCredit]:
    """Fresh SeriesCredit rows for one role — trimmed, de-duplicated (the
    uq_series_credit constraint), and positioned in the order given."""
    out: list[SeriesCredit] = []
    seen: set[str] = set()
    for raw in names:
        name = raw.strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        out.append(SeriesCredit(series_id=series_id, name=name, role=role, position=len(out)))
    return out


def _resolve_tags(session: Session, tag_ids: list[str]) -> list[Tag]:
    """Load taxonomy Tags by id (manual edits pick from the existing vocabulary)."""
    if not tag_ids:
        return []
    tags = list(session.scalars(select(Tag).where(Tag.id.in_(tag_ids))))
    missing = [tid for tid in tag_ids if tid not in {t.id for t in tags}]
    if missing:
        raise BadRequestError(f"unknown tag ids: {missing}")
    return tags


def _apply_action_state(series: Series, fields: dict[str, Any]) -> tuple[bool, bool]:
    """Per-user action-row state: favorite / shelf status / personal rating. Returns
    (shelf_changed, rating_changed) so the caller knows whether to push to trackers."""
    if "favorite" in fields:
        series.favorite = bool(fields["favorite"])
    shelf_changed = False
    if "library_status" in fields:
        status = fields["library_status"]
        if status not in _LIBRARY_STATUSES:
            raise BadRequestError(f"invalid library status: {status!r}")
        shelf_changed = series.library_status != status
        series.library_status = status
    rating_changed = False
    if "rating" in fields:
        raw = fields["rating"]
        if raw is None:
            series.user_rating = None
        else:
            score = float(raw)
            if not 1.0 <= score <= 10.0:
                raise BadRequestError("rating must be between 1 and 10 (or null)")
            series.user_rating = score
        rating_changed = True
    return shelf_changed, rating_changed


def _apply_metadata_fields(session: Session, series: Series, fields: dict[str, Any]) -> None:
    """Manual metadata edits, shared by the ``PATCH /api/series/{id}`` handler
    (``update_series``) and the ``lychee.info`` sidecar apply path
    (``apply_lychee_info``) — both build the same ``SeriesUpdate``-shaped ``fields``
    dict, so this is the *one* place metadata actually gets written + locked.

    Each edited scalar/collection field is added to ``locked_fields_json`` so a later
    provider refresh won't clobber it — except ``titles``, which is a pure additive
    union (ADR 18: every source contributes titles as a union; nothing here ever
    replaces or needs to lock the collection), and the gallery-only extras below,
    which no provider populates.
    """
    locked = set(series.locked_fields_json or [])
    if "title" in fields:
        title = (fields["title"] or "").strip()
        if not title:
            raise BadRequestError("title cannot be empty")
        series.title = title
        series.sort_title = title.lower()
        locked.add("title")
    if "titles" in fields:
        existing_keys = {(tv.language, tv.title) for tv in series.title_variants}
        for variant in fields["titles"] or []:
            key = (variant["language"], variant["title"])
            if key not in existing_keys:
                series.title_variants.append(
                    TitleVariant(
                        series_id=series.id,
                        title=variant["title"],
                        language=variant["language"],
                        variant_type=variant["variant_type"],
                    )
                )
                existing_keys.add(key)
    if "description" in fields:
        series.description = fields["description"] or None
        locked.add("description")
    if "year" in fields:
        series.year = fields["year"]
        locked.add("year")
    if "status" in fields:
        if fields["status"] not in _PUB_STATUSES:
            raise BadRequestError(f"invalid status: {fields['status']!r}")
        series.status = fields["status"]
        locked.add("status")
    if "content_rating" in fields:
        if fields["content_rating"] not in _CONTENT_RATINGS:
            raise BadRequestError(f"invalid content rating: {fields['content_rating']!r}")
        series.content_rating = fields["content_rating"]
        locked.add("content_rating")
    if "demographic" in fields:
        if fields["demographic"] not in _DEMOGRAPHICS:
            raise BadRequestError(f"invalid demographic: {fields['demographic']!r}")
        series.demographic = fields["demographic"]
        locked.add("demographic")
    if "origin_country" in fields:
        cc = (fields["origin_country"] or "").strip().lower()
        series.origin_country = cc[:2] or None
        locked.add("origin_country")
    if "authors" in fields or "artists" in fields:
        # Rebuild only the edited role(s), leaving the other role's rows untouched.
        edited: dict[str, list[str]] = {}
        if "authors" in fields:
            edited["author"] = fields["authors"] or []
        if "artists" in fields:
            edited["artist"] = fields["artists"] or []
        # Drop the edited roles' current rows and flush the DELETEs before re-inserting,
        # so a recreated name can't collide with an old row on uq_series_credit.
        series.credits = [c for c in series.credits if c.role not in edited]
        session.flush()
        for role, names in edited.items():
            series.credits.extend(_credit_rows(series.id, role, names))
        locked.add("credits")
    if "tag_ids" in fields:
        series.tags = _resolve_tags(session, fields["tag_ids"] or [])
        locked.add("tags")
    # Gallery-only extras — no provider populates these, so they aren't locked.
    if "source" in fields:
        series.source = (fields["source"] or "").strip() or None
    if "characters" in fields:
        series.characters_json = [c.strip() for c in fields["characters"] if c.strip()] or None

    series.locked_fields_json = sorted(locked) or None


def update_series(session: Session, series_id: str, data: SeriesUpdate) -> SeriesOut:
    """Apply series edits: per-user action-row state (favorite / shelf status / personal
    rating) and manual metadata (title, credits, tags, …). Each edited metadata field is
    added to ``locked_fields_json`` so a later provider refresh won't clobber it."""
    series = session.get(Series, series_id)
    if series is None:
        raise NotFoundError(f"series {series_id!r} not found")
    fields = data.model_dump(exclude_unset=True)

    shelf_changed, rating_changed = _apply_action_state(series, fields)
    _apply_metadata_fields(session, series, fields)

    session.commit()
    # Shelf or personal rating → push to connected sinks (trackers + MangaDex), best-effort.
    if shelf_changed or rating_changed:
        enqueue_push(session, series_id)
    row = repo.get_series(session, series_id)
    assert row is not None  # just updated
    return to_series_out(row)


_EXTERNAL_TRACKER_KEYS = {"anilist": "al", "myanimelist": "mal", "mangaupdates": "mu"}


def apply_lychee_info(session: Session, series: Series, info: LycheeInfoFile) -> list[str]:
    """Apply a parsed ``lychee.info`` sidecar (notes/decisions/20-lychee-info-metadata.md) to ``series``.

    Builds a ``SeriesUpdate``-shaped ``fields`` dict for the scalar/credit/title
    fields and runs it through the same ``_apply_metadata_fields`` the
    ``PATCH /api/series/{id}`` handler uses — applying the file auto-locks every
    field it touches, with zero new locking logic. Tags/external ids/provider match
    aren't part of ``SeriesUpdate`` (not user-facing manual-edit concepts) and are
    applied directly here instead. Returns human-readable warnings (kind mismatch,
    kind-inapplicable fields, unknown provider/tracker keys, unsupported multi-
    crossover) for the caller (the scanner) to log and surface on the scan result.
    """
    warnings: list[str] = []
    gallery = series.kind == "gallery"

    if info.kind != series.kind:
        warnings.append(
            f"kind {info.kind!r} in lychee.info does not match the series' library "
            f"kind {series.kind!r} — kind field ignored"
        )
    if gallery and info.status is not None:
        warnings.append("status is manga/comic-only — ignored for a gallery series")
    if gallery and info.demographic is not None:
        warnings.append("demographic is manga/comic-only — ignored for a gallery series")

    fields: dict[str, Any] = {}
    if info.title is not None:
        fields["title"] = info.title
    if info.titles is not None:
        fields["titles"] = [
            {"language": t.lang, "variant_type": t.type, "title": t.title} for t in info.titles
        ]
    if info.description is not None:
        fields["description"] = info.description
    if info.year is not None:
        fields["year"] = info.year
    if info.status is not None and not gallery:
        fields["status"] = info.status
    if info.content_rating is not None:
        fields["content_rating"] = info.content_rating
    if info.demographic is not None and not gallery:
        fields["demographic"] = info.demographic
    if info.origin_country is not None:
        fields["origin_country"] = info.origin_country

    if info.credits:
        authors = [c.name for c in info.credits if c.role == "author"]
        artists = [c.name for c in info.credits if c.role == "artist"]
        if authors:
            fields["authors"] = authors
        if artists:
            fields["artists"] = artists

    if info.crossovers:
        first = info.crossovers[0]
        if first.series is not None:
            fields["source"] = first.series
        if first.characters:
            fields["characters"] = first.characters
        if len(info.crossovers) > 1:
            warnings.append(
                "multiple crossovers found; only the first is applied "
                "(multi-franchise crossovers aren't fully supported yet)"
            )

    if fields:
        _apply_metadata_fields(session, series, fields)

    if info.tags is not None:
        pairs = [
            (name, group)
            for group in ("genre", "theme", "format", "content")
            for name in getattr(info.tags, group)
        ]
        if pairs:
            # Union, not replace — a partial file shouldn't drop tags another source
            # (e.g. a provider match) already set in groups it doesn't mention.
            new_tags = reconcile_tags(session, pairs)
            existing_ids = {t.id for t in series.tags}
            for tag in new_tags:
                if tag.id not in existing_ids:
                    series.tags.append(tag)
                    existing_ids.add(tag.id)

    if info.external:
        current = dict(series.external_ids_json or {})
        for name, value in info.external.items():
            key = _EXTERNAL_TRACKER_KEYS.get(name)
            if key is None:
                warnings.append(f"unknown external tracker {name!r} ignored")
                continue
            current[key] = value
        series.external_ids_json = current or None

    if info.provider:
        for provider_id, provider_series_id in info.provider.items():
            if series.provider == provider_id and series.provider_series_id == provider_series_id:
                continue  # already matched to this id — nothing to do
            try:
                _ = catalog_matching.set_match(
                    session,
                    series.id,
                    provider_id=provider_id,
                    provider_series_id=provider_series_id,
                )
            except BadRequestError as exc:
                warnings.append(f"provider {provider_id!r}: {exc.message}")

    series.metadata_file_version = info.generated.version if info.generated else None

    session.flush()
    return warnings


def to_chapter_out(row: ChapterRow) -> ChapterOut:
    c = row.chapter
    return ChapterOut(
        id=c.id,
        volume=c.volume,
        number=c.number or "",
        title=c.title,
        group=c.group_name,
        language=c.language,
        uploaded_at=c.source_uploaded_at or c.created_at,
        read=row.read,
        comments=c.comment_count,
        status="downloaded",
        provider_chapter_id=c.provider_chapter_id,
    )


def list_chapters(
    session: Session, series_id: str, *, language: str | None, order: str
) -> list[VolumeGroupOut]:
    """Chapters grouped by volume, preserving the requested chapter order.

    For series matched to a provider, merges the cached remote feed (``ProviderChapter``)
    with local chapters and live download-queue status so undownloaded chapters appear
    as ``available`` / ``queued`` / etc. The "No Volume" group sorts first; numbered
    volumes follow the chapter order direction.
    """
    series = session.get(Series, series_id)
    if series is None:
        raise NotFoundError(f"series {series_id!r} not found")

    # Best-effort: pull MangaDex feed when cache is empty/stale so first open works.
    ensure_chapter_index(session, series_id)

    ascending = order == "asc"
    rows = repo.list_chapters(session, series_id, language=language, descending=not ascending)
    local_pid = local_by_provider_id(session, series_id)
    local_num = local_by_number_lang(session, series_id)
    dl_status = download_status_map(session, series_id)
    read_ids = set(
        session.scalars(
            select(ReadingProgress.chapter_id).where(
                ReadingProgress.series_id == series_id,
                ReadingProgress.completed.is_(True),
            )
        )
    )

    # Start from remote index when present; otherwise local-only (scanned series).
    remote_rows = list(
        session.scalars(
            select(ProviderChapter)
            .where(ProviderChapter.series_id == series_id)
            .order_by(
                ProviderChapter.number_sort.asc()
                if ascending
                else ProviderChapter.number_sort.desc(),
                ProviderChapter.id.asc() if ascending else ProviderChapter.id.desc(),
            )
        )
    )
    if language:
        remote_rows = [r for r in remote_rows if r.language == language]

    chapters_out: list[ChapterOut] = []
    if remote_rows:
        covered_local_ids: set[str] = set()
        for remote in remote_rows:
            local = local_pid.get(remote.provider_chapter_id)
            if local is None and remote.number is not None:
                local = local_num.get((remote.number, remote.language))
            if local is not None:
                covered_local_ids.add(local.id)
                status = "downloaded"
                chapters_out.append(
                    ChapterOut(
                        id=local.id,
                        volume=local.volume if local.volume is not None else remote.volume,
                        number=local.number or remote.number or "",
                        title=local.title or remote.title,
                        group=local.group_name or remote.group_name,
                        language=local.language,
                        uploaded_at=local.source_uploaded_at
                        or remote.published_at
                        or local.created_at,
                        read=local.id in read_ids,
                        comments=local.comment_count,
                        status=status,
                        provider_chapter_id=remote.provider_chapter_id,
                    )
                )
            else:
                status = dl_status.get(remote.provider_chapter_id, "available")
                chapters_out.append(
                    ChapterOut(
                        id=None,
                        volume=remote.volume,
                        number=remote.number or "",
                        title=remote.title,
                        group=remote.group_name,
                        language=remote.language,
                        uploaded_at=remote.published_at,
                        read=False,
                        comments=0,
                        status=status,
                        provider_chapter_id=remote.provider_chapter_id,
                    )
                )
        # Local chapters not represented in the remote index (e.g. scan-only extras).
        for row in rows:
            if row.chapter.id not in covered_local_ids:
                chapters_out.append(to_chapter_out(row))
    else:
        chapters_out = [to_chapter_out(row) for row in rows]

    # Sort merged list by number_sort when we mixed remote + local extras.
    def _sort_key(c: ChapterOut) -> tuple[float, str]:
        try:
            n = float(c.number) if c.number else 0.0
        except ValueError:
            n = 0.0
        return (n, c.provider_chapter_id or c.id or "")

    chapters_out.sort(key=_sort_key, reverse=not ascending)

    groups: list[VolumeGroupOut] = []
    by_volume: dict[int | None, VolumeGroupOut] = {}
    for chapter in chapters_out:
        volume = chapter.volume
        group = by_volume.get(volume)
        if group is None:
            group = VolumeGroupOut(volume=volume, chapters=[])
            by_volume[volume] = group
            groups.append(group)
        group.chapters.append(chapter)
    groups.sort(
        key=lambda g: (g.volume is not None, (g.volume or 0) if ascending else -(g.volume or 0))
    )
    return groups


def get_chapter(session: Session, chapter_id: str) -> ChapterDetailOut:
    row = repo.get_chapter(session, chapter_id)
    if row is None:
        raise NotFoundError(f"chapter {chapter_id!r} not found")
    c = row.chapter
    return ChapterDetailOut(
        id=c.id,
        series_id=c.series_id,
        volume=c.volume,
        number=c.number or "",
        title=c.title,
        group=c.group_name,
        language=c.language,
        page_count=c.page_count,
        comments=c.comment_count,
        read=row.read,
        uploaded_at=c.source_uploaded_at or c.created_at,
    )


def _to_recent_update(row: UpdateRow, series: SeriesOut) -> RecentUpdateOut:
    return RecentUpdateOut(
        series=series,
        volume=row.chapter.volume,
        chapter=row.chapter.number or "",
        updated_at=row.updated_at,
    )


def updates(
    session: Session, *, unread_only: bool, cursor: str | None, limit: int
) -> Page[RecentUpdateOut]:
    limit = max(1, min(limit, _MAX_LIMIT))
    rows, next_cursor = repo.recent_updates(
        session, unread_only=unread_only, cursor=cursor, limit=limit
    )
    series_map = repo.get_series_rows(session, [r.chapter.series_id for r in rows])
    items = [
        _to_recent_update(r, to_series_out(series_map[r.chapter.series_id]))
        for r in rows
        if r.chapter.series_id in series_map
    ]
    return Page[RecentUpdateOut](items=items, next_cursor=next_cursor)


def dashboard(session: Session) -> DashboardOut:
    series_count, unread_chapters, reading = repo.dashboard_counts(session)
    recent = updates(session, unread_only=False, cursor=None, limit=12)
    return DashboardOut(
        stats=DashboardStats(series=series_count, unread_chapters=unread_chapters, reading=reading),
        continue_reading=[to_series_out(r) for r in repo.continue_reading(session, limit=6)],
        recent_updates=recent.items,
        recently_added=[to_series_out(r) for r in repo.recently_added(session, limit=12)],
    )


def search(session: Session, q: str, *, limit: int = 20) -> list[SeriesOut]:
    if not q.strip():
        return []
    return [to_series_out(r) for r in repo.search_series(session, q.strip(), limit=limit)]


def related(session: Session, series_id: str, *, limit: int = 12) -> list[SeriesOut]:
    """Other series of the same kind (Related tab)."""
    if session.get(Series, series_id) is None:
        raise NotFoundError(f"series {series_id!r} not found")
    rows = repo.related_series(session, series_id, limit=limit)
    return [to_series_out(r) for r in rows]


def series_art(session: Session, series_id: str) -> SeriesArtOut:
    """Extra art for a series (Art tab). Empty until an art store exists (backlog)."""
    if session.get(Series, series_id) is None:
        raise NotFoundError(f"series {series_id!r} not found")
    return SeriesArtOut(images=[])


_KIND_ROUTE: dict[str, tuple[str, str]] = {
    "manga": ("manga", "Manga"),
    "comic": ("comics", "Comics"),
    "gallery": ("gallery", "Gallery"),
}


def library_summaries(session: Session) -> list[LibrarySummaryOut]:
    """Per-kind storage usage (Home + About). GB rounded; caller hides zero-size."""
    summaries: list[LibrarySummaryOut] = []
    for kind, size_bytes in repo.library_size_by_kind(session):
        meta = _KIND_ROUTE.get(kind)
        if meta is None:
            continue
        route, title = meta
        summaries.append(
            LibrarySummaryOut(key=route, title=title, size_gb=round(size_bytes / 1e9, 1))
        )
    order = {"manga": 0, "comics": 1, "gallery": 2}
    summaries.sort(key=lambda s: order.get(s.key, 9))
    return summaries
