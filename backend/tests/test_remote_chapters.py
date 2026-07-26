"""Remote chapter index: upsert, merge into list_chapters, download-by-id."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.catalog.models import Chapter, ProviderChapter, Series
from src.catalog.remote_chapters import upsert_provider_chapters
from src.downloads.provider import RemoteChapter, register_provider
from src.media.thumbnails import ThumbnailStore, ThumbVariant

from tests.support import ensure_library, make_series


class _FeedProvider:
    id = "mangadex"

    def __init__(self, remotes: list[RemoteChapter]) -> None:
        self._remotes = remotes

    def list_chapters(
        self, provider_series_id: str, *, language: str = "en"
    ) -> list[RemoteChapter]:
        return list(self._remotes)

    def fetch_pages(
        self, chapter: RemoteChapter, *, data_saver: bool = False, on_page=None
    ) -> list[bytes]:
        return [b"fake"]


def _remote(n: str, pid: str, *, volume: int | None = 1) -> RemoteChapter:
    return RemoteChapter(
        provider_chapter_id=pid,
        number=n,
        volume=volume,
        title=f"Chapter {n}",
        language="en",
        group_name="Test Group",
        published_at="2024-01-01T00:00:00+00:00",
    )


def test_upsert_provider_chapters_idempotent(db_session: Session) -> None:
    series = make_series(db_session, title="Indexed")
    series.provider = "mangadex"
    series.provider_series_id = "md-1"
    db_session.commit()

    remotes = [_remote("1", "c1"), _remote("2", "c2")]
    assert upsert_provider_chapters(db_session, series, remotes) == 2
    db_session.commit()
    assert db_session.query(ProviderChapter).filter_by(series_id=series.id).count() == 2
    assert series.available_chapters == 2
    assert series.chapter_index_at is not None

    # Second upsert with one removed updates + prunes.
    remotes2 = [_remote("1", "c1"), _remote("3", "c3")]
    assert upsert_provider_chapters(db_session, series, remotes2) == 2
    db_session.commit()
    pids = {
        r.provider_chapter_id
        for r in db_session.query(ProviderChapter).filter_by(series_id=series.id)
    }
    assert pids == {"c1", "c3"}


def test_list_chapters_merges_remote_and_local(client: TestClient, db_session: Session) -> None:
    library = ensure_library(db_session)
    series = Series(
        library_id=library.id,
        kind="manga",
        title="Merge Series",
        sort_title="merge series",
        provider="mangadex",
        provider_series_id="md-merge",
    )
    db_session.add(series)
    db_session.flush()

    remotes = [_remote("1", "c1"), _remote("2", "c2")]
    register_provider(_FeedProvider(remotes))
    _ = upsert_provider_chapters(db_session, series, remotes)
    # Local only for ch 1
    from src.catalog.models import Book

    book = Book(
        series_id=series.id,
        library_id=library.id,
        path_rel="x.cbz",
        content_kind="cbz",
        page_count=10,
    )
    db_session.add(book)
    db_session.flush()
    db_session.add(
        Chapter(
            series_id=series.id,
            book_id=book.id,
            number="1",
            number_sort=1.0,
            language="en",
            page_count=10,
            provider="mangadex",
            provider_chapter_id="c1",
        )
    )
    db_session.commit()

    resp = client.get(f"/api/series/{series.id}/chapters")
    assert resp.status_code == 200
    groups = resp.json()
    chapters = [c for g in groups for c in g["chapters"]]
    by_num = {c["number"]: c for c in chapters}
    assert by_num["1"]["status"] == "downloaded"
    assert by_num["1"]["id"] is not None
    assert by_num["2"]["status"] == "available"
    assert by_num["2"]["id"] is None
    assert by_num["2"]["providerChapterId"] == "c2"


def test_materialize_cover_writes_both_variants(db_session: Session, tmp_path, monkeypatch) -> None:
    import io
    from pathlib import Path

    import httpx
    from PIL import Image
    from src.catalog.media import get_cover, materialize_series_cover
    from src.core.config import settings

    monkeypatch.setattr(settings, "storage_path", str(tmp_path / "storage"))
    store = ThumbnailStore(Path(settings.storage_path) / "thumbnails")

    series = make_series(db_session, title="CoverMe")
    series.cover_source = "https://example.com/cover.jpg"
    db_session.commit()

    buf = io.BytesIO()
    Image.new("RGB", (80, 120), (200, 40, 40)).save(buf, format="JPEG")
    jpeg = buf.getvalue()

    class _Resp:
        status_code = 200
        content = jpeg

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp())

    assert materialize_series_cover(db_session, store, series.id) is True
    assert store.exists(series.id, ThumbVariant.COVER)
    assert store.exists(series.id, ThumbVariant.DETAIL)

    served = get_cover(db_session, store, series.id, "detail")
    assert served.media_type == "image/avif"
    assert store.read(series.id, ThumbVariant.DETAIL) == served.data
