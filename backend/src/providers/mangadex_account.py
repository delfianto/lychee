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

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.media import materialize_series_cover, warm_series_covers
from src.catalog.metadata import apply_metadata
from src.catalog.models import Chapter, Library, Series
from src.collections.sync import apply_list, reconcile_account_flags
from src.core.crypto import decrypt, encrypt
from src.core.exceptions import BadRequestError
from src.core.logging import get_logger
from src.downloads.provider import CustomList, SeriesMetadata
from src.integrations.models import Provider
from src.integrations.providers import get_provider_row, provider_out
from src.integrations.schema import ProviderConnect, ProviderOut
from src.integrations.sync import SyncCancelled, sync_jobs
from src.media.storage import thumbnail_root
from src.media.thumbnails import ThumbnailStore
from src.progress.models import ProviderReadingProgress, ReadingProgress
from src.providers.mangadex import MangaDexProvider
from src.providers.mangadex_auth import password_grant, refresh_grant
from src.providers.mangadex_client import API_BASE, USER_AGENT
from src.providers.mangadex_lists import LIST_LOCK
from src.tasks.concurrency import parallel_map
from src.tasks.context import checkpoint, report_phase
from src.tasks.queue import MAX_WORKERS, Work, queue
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
    library = session.scalar(select(Library).where(Library.path == "mangadex://follows"))
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
    warm_cover: bool = True,
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
    if warm_cover and fetch_covers and series.cover_source:
        # Eagerly materialize so library grids don't blank while first cover request
        # hits the CDN + AVIF encode on the request path.
        store = ThumbnailStore(thumbnail_root(session))
        _ = materialize_series_cover(session, store, series.id)
    return series


def _safe_metadata(provider: MangaDexProvider, md_id: str, language: str) -> SeriesMetadata | None:
    """Fetch one manga's metadata; None on any provider error (skip, don't fail the sync)."""
    try:
        checkpoint()
        return provider.get_metadata(md_id, language=language)
    except httpx.HTTPError, KeyError, TypeError, ValueError:
        return None


def _sync_lists(session: Session, lists: list[CustomList], series_by_id: dict[str, Series]) -> int:
    """Mirror each MangaDex custom list into a managed Collection (get-or-create by list id;
    name + membership from MangaDex). Returns the number of lists synced."""
    reconcile_account_flags(session, lists)
    synced = 0
    for custom in lists:
        checkpoint()
        if any(mid not in series_by_id for mid in custom.manga_ids):
            logger.warning("mdlist_incomplete_metadata", list_id=custom.provider_list_id)
            continue  # Keep the last complete membership if upstream metadata failed.
        apply_list(session, custom, series_by_id)
        synced += 1
    return synced


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
    """Pull read markers for downloaded and provider-only chapters; never un-read on pull."""
    from src.progress.state import write_state

    if not series_by_id:
        return 0
    markers = provider.read_markers(list(series_by_id))
    marked = 0
    for md_id, series in series_by_id.items():
        for remote_id in set(markers.get(md_id, [])):
            chapter = session.scalar(
                select(Chapter).where(
                    Chapter.series_id == series.id, Chapter.provider_chapter_id == remote_id
                )
            )
            marked += write_state(
                session,
                series_id=series.id,
                chapter=chapter,
                provider="mangadex",
                provider_chapter_id=remote_id,
                page=chapter.page_count if chapter else 0,
                completed=True,
            )
    return marked


def _sync_work() -> Work:
    def work(session: Session, on_progress: Callable[[int, str], None]) -> dict[str, int]:
        config = get_provider_row(session, _MANGADEX)
        if not (config.client_id and config.client_secret_enc and config.refresh_token_enc):
            raise BadRequestError("MangaDex account is not connected")
        provider = _authed_provider(_access_token(session, config))
        library = _mangadex_library(session)

        job = sync_jobs.create(
            kind="import",
            title="MangaDex Account",
            source="MangaDex",
            status="running",
            detail="Fetching account follows and lists from MangaDex",
        )
        checkpoint()
        report_phase("account", 0, 1, "Fetching account")
        on_progress(5, "Fetching account")
        follows = provider.list_follows(language=config.language)
        statuses = provider.reading_status()
        lists = list(
            {
                item.provider_list_id: item
                for item in [*provider.list_followed_lists(), *provider.list_custom_lists()]
            }.values()
        )

        # The synced set = follows ∪ manga with a reading status ∪ custom-list members.
        meta_by_id: dict[str, SeriesMetadata] = {m.provider_series_id: m for m in follows}
        union_ids = (
            set(meta_by_id) | set(statuses) | {mid for lst in lists for mid in lst.manga_ids}
        )

        series_by_id: dict[str, Series] = {}
        total = len(union_ids) or 1
        report_phase("account", 1, 1)
        report_phase("metadata", 0, len(union_ids), "Fetching manga metadata")

        def fetch_metadata(md_id: str) -> tuple[str, SeriesMetadata | None]:
            checkpoint()
            with queue.io_limit.slot():
                return md_id, meta_by_id.get(md_id) or _safe_metadata(
                    provider, md_id, config.language
                )

        try:
            for index, (md_id, meta) in enumerate(
                parallel_map(
                    fetch_metadata, sorted(union_ids), workers=MAX_WORKERS, limit=queue.io_limit
                ),
                start=1,
            ):
                sync_jobs.check_state(job.id)
                pct = round(index / total * 90)
                if meta is None:
                    _ = sync_jobs.create(
                        kind="import",
                        title=md_id,
                        source="MangaDex",
                        status="failed",
                        detail=f"Failed pulling manga {md_id} from MangaDex",
                        error="Could not fetch metadata from MangaDex",
                    )
                    continue
                _ = sync_jobs.update(
                    job.id,
                    status="running",
                    progress=pct,
                    detail=f"Pulling {meta.title} from MangaDex",
                )
                series_by_id[md_id] = _upsert_series(
                    session,
                    library,
                    meta,
                    statuses.get(md_id),
                    fetch_covers=config.fetch_covers,
                    warm_cover=False,
                )
                session.commit()  # commit per series so progress is durable
                report_phase("metadata", index, len(union_ids), meta.title)
                on_progress(pct, meta.title)
        except SyncCancelled:
            raise

        checkpoint()
        report_phase("lists", 0, 1, "Syncing lists")
        on_progress(95, "Syncing lists")
        _ = sync_jobs.update(job.id, progress=95, detail="Syncing MangaDex lists")
        with LIST_LOCK:
            # Refresh snapshots after the long metadata import so a concurrent
            # user edit cannot be overwritten by membership fetched at startup.
            lists = list(
                {
                    item.provider_list_id: item
                    for item in [*provider.list_followed_lists(), *provider.list_custom_lists()]
                }.values()
            )
            for custom in lists:
                checkpoint()
                for mid in custom.manga_ids:
                    if mid not in series_by_id:
                        meta = _safe_metadata(provider, mid, config.language)
                        if meta is not None:
                            series_by_id[mid] = _upsert_series(
                                session,
                                library,
                                meta,
                                None,
                                fetch_covers=config.fetch_covers,
                                warm_cover=False,
                            )
            synced_lists = _sync_lists(session, lists, series_by_id)
            session.commit()
        report_phase("lists", 1, 1)
        report_phase("ratings", 0, 1, "Syncing ratings")
        on_progress(96, "Syncing ratings")
        rated = _sync_ratings(session, provider, series_by_id)
        report_phase("ratings", 1, 1)
        report_phase("reading", 0, 1, "Syncing read markers")
        on_progress(98, "Syncing read markers")
        marked = _sync_read_markers(session, provider, series_by_id)
        session.commit()
        report_phase("reading", 1, 1)
        if config.fetch_covers:
            store = ThumbnailStore(thumbnail_root(session))
            _ = warm_series_covers(session, store, [series.id for series in series_by_id.values()])
        checkpoint()
        _ = sync_jobs.update(
            job.id,
            status="running",
            progress=99,
            detail=f"Synced {len(series_by_id)} manga from MangaDex",
        )
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
        remote_states = list(
            session.scalars(
                select(ProviderReadingProgress).where(
                    ProviderReadingProgress.series_id == series_id,
                    ProviderReadingProgress.provider == "mangadex",
                )
            )
        )
        read_ids = sorted(
            set(read_ids) | {row.provider_chapter_id for row in remote_states if row.completed}
        )
        unread_ids = [
            row.provider_chapter_id
            for row in remote_states
            if not row.completed and row.provider_chapter_id not in read_ids
        ]
        provider.push_read(series.provider_series_id, read_ids, unread_ids=unread_ids)
        # Personal score: int 1–10, or None to clear on MangaDex.
        personal = int(round(series.user_rating)) if series.user_rating is not None else None
        if personal is not None:
            personal = max(1, min(10, personal))
        provider.push_rating(series.provider_series_id, personal)
    except Exception as exc:  # noqa: BLE001 - best-effort; a push failure can't fail a read/edit
        logger.warning("mangadex_push_failed", series=series.title, error=str(exc))
        return False
    return True
