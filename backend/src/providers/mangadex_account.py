"""MangaDex account: OAuth connect/disconnect + a re-runnable account sync.

Connecting exchanges a personal client's credentials for tokens (stored encrypted
on the provider config row). Syncing refreshes the token, then pulls the union of the
user's followed manga, reading statuses, and custom lists (MDLists) into a virtual
"MangaDex" library — applying provider metadata, mapping each status onto
``Series.library_status`` (MangaDex is the source of truth), and mirroring each custom
list into a managed Collection. It downloads no pages (download stays a triggered action).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.catalog.media import materialize_series_cover
from src.catalog.metadata import apply_metadata
from src.catalog.models import Chapter, Library, Series
from src.collections.models import Collection, CollectionSeries
from src.core.config import settings
from src.core.crypto import decrypt, encrypt
from src.core.exceptions import BadRequestError
from src.core.logging import get_logger
from src.downloads.provider import CustomList, SeriesMetadata
from src.integrations.models import Provider
from src.integrations.providers import get_provider_row, provider_out
from src.integrations.schema import ProviderConnect, ProviderOut
from src.media.thumbnails import ThumbnailStore
from src.progress.models import ReadingProgress
from src.providers.mangadex import MangaDexProvider
from src.providers.mangadex_auth import password_grant, refresh_grant
from src.providers.mangadex_client import API_BASE, USER_AGENT
from src.tasks.queue import Work, queue
from src.tasks.schema import TaskOut

_MANGADEX = "mangadex"
_MANGADEX_LIBRARY = "MangaDex"
# MangaDex reading statuses that map 1:1 onto Series.library_status.
_READING_STATUSES = {"reading", "on_hold", "plan_to_read", "dropped", "re_reading", "completed"}

logger = get_logger(__name__)
# Access token cached in-memory (~14 min) so a burst of pushes doesn't re-refresh (and
# re-rotate the refresh token) each time. Every current caller happens to run on the
# single-worker task queue, but that's an external invariant this module can't see —
# _TOKEN_LOCK makes the refresh-and-persist section safe regardless, since MangaDex
# rotates the refresh token on every use and redeeming a stale one can revoke the pair.
_TOKEN_LOCK = threading.Lock()
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


def connect(session: Session, provider_id: str, data: ProviderConnect) -> ProviderOut:
    """Exchange personal-client credentials for tokens; store the secret + refresh token encrypted."""
    provider = get_provider_row(session, provider_id)
    tokens = password_grant(
        client_id=data.client_id,
        client_secret=data.client_secret,
        username=data.username,
        password=data.password,
    )
    provider.client_id = data.client_id
    provider.client_secret_enc = encrypt(data.client_secret)
    provider.refresh_token_enc = encrypt(tokens.refresh_token)
    provider.account_name = data.username
    session.commit()
    return provider_out(provider)


def disconnect(session: Session, provider_id: str) -> ProviderOut:
    provider = get_provider_row(session, provider_id)
    provider.client_id = None
    provider.client_secret_enc = None
    provider.refresh_token_enc = None
    provider.account_name = None
    session.commit()
    return provider_out(provider)


def _authed_provider(access_token: str) -> MangaDexProvider:
    client = httpx.Client(
        base_url=API_BASE,
        timeout=30.0,
        headers={"User-Agent": USER_AGENT, "Authorization": f"Bearer {access_token}"},
    )
    return MangaDexProvider(client=client)


def _access_token(session: Session, config: Provider) -> str:
    """A valid access token for the connected account, cached in-memory (persisting the
    rotated refresh token whenever it does refresh). Locked end-to-end: two concurrent
    callers redeeming the same not-yet-rotated refresh token would race with MangaDex's
    server-side rotation, and the loser's redemption can permanently break the connection."""
    if not (config.client_id and config.client_secret_enc and config.refresh_token_enc):
        raise BadRequestError("MangaDex account is not connected")
    cache_key = config.client_id or ""
    with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(cache_key)
        now = time.monotonic()
        if cached and cached[1] > now:
            return cached[0]
        tokens = refresh_grant(
            client_id=config.client_id,
            client_secret=decrypt(config.client_secret_enc),
            refresh_token=decrypt(config.refresh_token_enc),
        )
        config.refresh_token_enc = encrypt(tokens.refresh_token)
        session.commit()  # persist the rotated refresh token before it's used again
        _TOKEN_CACHE[cache_key] = (tokens.access_token, now + 14 * 60)
        return tokens.access_token


def _mangadex_library(session: Session) -> Library:
    library = session.scalar(select(Library).where(Library.name == _MANGADEX_LIBRARY))
    if library is None:
        library = Library(name=_MANGADEX_LIBRARY, path="mangadex://follows", kind="mixed")
        session.add(library)
        session.flush()
    return library


def _upsert_series(
    session: Session,
    library: Library,
    meta: SeriesMetadata,
    status: str | None,
    *,
    fetch_covers: bool,
) -> Series:
    """Create/update the Series for a MangaDex manga, matched by provider id **globally** — so
    a scanned-and-matched series is updated in place, never duplicated. Applies metadata and,
    MangaDex being the source of truth here, maps its reading status onto the shelf."""
    series = session.scalar(
        select(Series).where(
            Series.provider == _MANGADEX, Series.provider_series_id == meta.provider_series_id
        )
    )
    if series is None:
        series = Series(
            library_id=library.id,
            kind="manga",
            title=meta.title,
            sort_title=meta.title.lower(),
            path_rel=meta.provider_series_id,
            provider=_MANGADEX,
            provider_series_id=meta.provider_series_id,
        )
        session.add(series)
        session.flush()
    apply_metadata(session, series, meta, fetch_covers=fetch_covers)
    if status in _READING_STATUSES:
        series.library_status = status  # MangaDex wins on pull
    if fetch_covers and series.cover_source:
        # Eagerly materialize so library grids don't blank while first cover request
        # hits the CDN + AVIF encode on the request path.
        store = ThumbnailStore(Path(settings.storage_path) / "thumbnails")
        _ = materialize_series_cover(session, store, series.id)
    return series


def _safe_metadata(provider: MangaDexProvider, md_id: str, language: str) -> SeriesMetadata | None:
    """Fetch one manga's metadata; None on any provider error (skip, don't fail the sync)."""
    try:
        return provider.get_metadata(md_id, language=language)
    except httpx.HTTPError, KeyError, TypeError, ValueError:
        return None


def _reconcile_membership(
    session: Session, collection: Collection, ordered_series_ids: list[str]
) -> None:
    """Set a synced collection's members to exactly ``ordered_series_ids`` (MangaDex order)."""
    want = set(ordered_series_ids)
    have = {entry.series_id: entry for entry in collection.entries}
    for series_id, entry in list(have.items()):
        if series_id not in want:
            collection.entries.remove(entry)  # delete-orphan drops the row
    for position, series_id in enumerate(ordered_series_ids):
        entry = have.get(series_id)
        if entry is None:
            collection.entries.append(CollectionSeries(series_id=series_id, position=position))
        else:
            entry.position = position


def _sync_lists(session: Session, lists: list[CustomList], series_by_id: dict[str, Series]) -> int:
    """Mirror each MangaDex custom list into a managed Collection (get-or-create by list id;
    name + membership from MangaDex). Returns the number of lists synced."""
    for custom in lists:
        collection = session.scalar(
            select(Collection).where(
                Collection.provider == _MANGADEX,
                Collection.provider_list_id == custom.provider_list_id,
            )
        )
        if collection is None:
            collection = Collection(
                name=custom.name, provider=_MANGADEX, provider_list_id=custom.provider_list_id
            )
            session.add(collection)
            session.flush()
        else:
            collection.name = custom.name  # MangaDex wins on the name
        ordered = [series_by_id[mid].id for mid in custom.manga_ids if mid in series_by_id]
        _reconcile_membership(session, collection, ordered)
    return len(lists)


def _sync_ratings(
    session: Session, provider: MangaDexProvider, series_by_id: dict[str, Series]
) -> int:
    """Pull personal ratings onto local series. MangaDex wins when a score is present;
    missing keys leave the local ``user_rating`` untouched (don't wipe lychee-only rates)."""
    if not series_by_id:
        return 0
    try:
        ratings = provider.list_ratings(list(series_by_id))
    except Exception as exc:  # noqa: BLE001 - ratings are best-effort
        logger.warning("mangadex_ratings_pull_failed", error=str(exc))
        return 0
    applied = 0
    for md_id, score in ratings.items():
        series = series_by_id.get(md_id)
        if series is None:
            continue
        series.user_rating = float(score)
        applied += 1
    return applied


def _sync_read_markers(
    session: Session, provider: MangaDexProvider, series_by_id: dict[str, Series]
) -> int:
    """Pull MangaDex read markers onto local chapters of already-downloaded series (matched by
    ``provider_chapter_id``). Additive — marks read, never un-reads. Writes progress directly
    (no tracker push — this is the inbound side). Sync-only series (no local chapters) are a
    no-op, so only series that have chapters are even requested."""
    downloaded = {
        md_id: series
        for md_id, series in series_by_id.items()
        if session.scalar(
            select(func.count()).select_from(Chapter).where(Chapter.series_id == series.id)
        )
    }
    if not downloaded:
        return 0
    markers = provider.read_markers(list(downloaded))
    marked = 0
    for md_id, series in downloaded.items():
        read_ids = set(markers.get(md_id, []))
        if not read_ids:
            continue
        chapters = session.scalars(
            select(Chapter).where(
                Chapter.series_id == series.id, Chapter.provider_chapter_id.in_(read_ids)
            )
        )
        for chapter in chapters:
            row = session.scalar(
                select(ReadingProgress).where(ReadingProgress.chapter_id == chapter.id)
            )
            if row is not None and row.completed:
                continue  # already read — additive, leave it
            if row is None:
                row = ReadingProgress(chapter_id=chapter.id, series_id=series.id)
                session.add(row)
            row.completed = True
            row.current_page = chapter.page_count
            marked += 1
    return marked


def _sync_work() -> Work:
    def work(session: Session, on_progress: Callable[[int, str], None]) -> dict[str, int]:
        config = get_provider_row(session, _MANGADEX)
        if not (config.client_id and config.client_secret_enc and config.refresh_token_enc):
            raise BadRequestError("MangaDex account is not connected")
        provider = _authed_provider(_access_token(session, config))
        library = _mangadex_library(session)

        on_progress(5, "Fetching account")
        follows = provider.list_follows(language=config.language)
        statuses = provider.reading_status()
        lists = provider.list_custom_lists()

        # The synced set = follows ∪ manga with a reading status ∪ custom-list members.
        meta_by_id: dict[str, SeriesMetadata] = {m.provider_series_id: m for m in follows}
        union_ids = (
            set(meta_by_id) | set(statuses) | {mid for lst in lists for mid in lst.manga_ids}
        )

        series_by_id: dict[str, Series] = {}
        total = len(union_ids) or 1
        for index, md_id in enumerate(sorted(union_ids), start=1):
            meta = meta_by_id.get(md_id) or _safe_metadata(provider, md_id, config.language)
            if meta is None:
                continue
            series_by_id[md_id] = _upsert_series(
                session, library, meta, statuses.get(md_id), fetch_covers=config.fetch_covers
            )
            session.commit()  # commit per series so progress is durable
            on_progress(round(index / total * 90), meta.title)

        on_progress(95, "Syncing lists")
        synced_lists = _sync_lists(session, lists, series_by_id)
        on_progress(96, "Syncing ratings")
        rated = _sync_ratings(session, provider, series_by_id)
        on_progress(98, "Syncing read markers")
        marked = _sync_read_markers(session, provider, series_by_id)
        session.commit()
        return {
            "synced": len(series_by_id),
            "lists": synced_lists,
            "ratings": rated,
            "readMarked": marked,
        }

    return work


def sync_account(session: Session, provider_id: str) -> TaskOut:
    """Validate the account is connected, then sync follows + statuses + lists on the queue."""
    config = get_provider_row(session, provider_id)
    if not (config.client_id and config.refresh_token_enc):
        raise BadRequestError("MangaDex account is not connected")
    return queue.submit_task("import", "Syncing MangaDex", _sync_work())


def is_connected(session: Session) -> bool:
    """Whether a MangaDex account is connected (i.e. an outbound push sink is available)."""
    config = session.get(Provider, _MANGADEX)
    return bool(config and config.client_id and config.refresh_token_enc)


def push_series(session: Session, series_id: str) -> bool:
    """Outbound two-way push: send a dex-linked series' reading status + read markers to
    MangaDex. Best-effort (swallows failures); a no-op when the series isn't MangaDex-linked
    or the account isn't connected. Called from the tracker sync-on-read task."""
    series = session.get(Series, series_id)
    if series is None or series.provider != _MANGADEX or not series.provider_series_id:
        return False
    config = get_provider_row(session, _MANGADEX)
    if not (config.client_id and config.client_secret_enc and config.refresh_token_enc):
        return False
    try:
        provider = _authed_provider(_access_token(session, config))
        status = series.library_status if series.library_status in _READING_STATUSES else None
        provider.push_status(series.provider_series_id, status)
        read_ids = [
            cid
            for cid in session.scalars(
                select(Chapter.provider_chapter_id)
                .join(ReadingProgress, ReadingProgress.chapter_id == Chapter.id)
                .where(
                    Chapter.series_id == series_id,
                    ReadingProgress.completed.is_(True),
                    Chapter.provider_chapter_id.is_not(None),
                )
            )
            if cid
        ]
        provider.push_read(series.provider_series_id, read_ids)
        # Personal score: int 1–10, or None to clear on MangaDex.
        personal = int(round(series.user_rating)) if series.user_rating is not None else None
        if personal is not None:
            personal = max(1, min(10, personal))
        provider.push_rating(series.provider_series_id, personal)
    except Exception as exc:  # noqa: BLE001 - best-effort; a push failure can't fail a read/edit
        logger.warning("mangadex_push_failed", series=series.title, error=str(exc))
        return False
    return True
