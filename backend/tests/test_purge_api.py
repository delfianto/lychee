"""Provider-aware chapter purge (delete local files)."""

from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.catalog.models import Book, Chapter, Series
from src.catalog.remote_chapters import upsert_provider_chapters
from src.downloads.provider import RemoteChapter, register_provider
from src.tasks.queue import queue

from tests.support import ensure_library, ensure_manga_library, make_series


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 24), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


class _FakeProvider:
    # Unique id — must not stomp test_downloads_api's "fake" (collection order).
    id = "fake-purge"

    def list_chapters(
        self, provider_series_id: str, *, language: str = "en"
    ) -> list[RemoteChapter]:
        return [RemoteChapter("pc1", "1", 1, "One", "en")]

    def fetch_pages(
        self, chapter: RemoteChapter, *, data_saver: bool = False, on_page=None
    ) -> list[bytes]:
        pages = [_png(), _png()]
        if on_page is not None:
            for i, _ in enumerate(pages, start=1):
                on_page(i, len(pages))
        return pages


register_provider(_FakeProvider())


def test_delete_provider_chapter_keeps_series_and_allows_redownload(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    manga_root = tmp_path / "manga"
    ensure_manga_library(db_session, manga_root)
    series = make_series(db_session, title="PurgeMe", kind="manga")
    series.provider = "fake-purge"
    series.provider_series_id = "remote-p"
    db_session.commit()

    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
    queue.wait_idle()

    chapters = client.get(f"/api/series/{series.id}/chapters").json()
    ch = next(c for g in chapters for c in g["chapters"] if c["status"] == "downloaded")
    chapter_id = ch["id"]
    assert chapter_id

    # File exists under human-readable path
    cbz = next(manga_root.rglob("*.cbz"))
    assert cbz.is_file()

    # Seed remote index so list can show available after purge
    remote = RemoteChapter("pc1", "1", 1, "One", "en")
    upsert_provider_chapters(db_session, series, [remote], provider="fake-purge")
    db_session.commit()

    resp = client.delete(f"/api/chapters/{chapter_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "provider"
    assert body["redownloadable"] is True

    assert not cbz.exists()
    assert client.get(f"/api/chapters/{chapter_id}").status_code == 404
    # Series still there
    assert client.get(f"/api/series/{series.id}").status_code == 200
    # Book soft-deleted
    book = db_session.scalar(select(Book).where(Book.series_id == series.id))
    assert book is not None
    assert book.deleted_at is not None
    # Remote index kept → available again
    listed = client.get(f"/api/series/{series.id}/chapters").json()
    statuses = [c["status"] for g in listed for c in g["chapters"]]
    assert "available" in statuses


def test_delete_local_chapter_hard_purges_db_and_file(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    root = tmp_path / "lib"
    root.mkdir()
    library = ensure_library(db_session, kind="mixed")
    library.path = str(root)
    series = Series(
        library_id=library.id,
        kind="manga",
        title="LocalOnly",
        sort_title="localonly",
    )
    db_session.add(series)
    db_session.flush()
    series_dir = root / "LocalOnly"
    series_dir.mkdir()
    cbz = series_dir / "Ch.1.cbz"
    cbz.write_bytes(b"PK\x03\x04fake")
    book = Book(
        series_id=series.id,
        library_id=library.id,
        path_rel="LocalOnly/Ch.1.cbz",
        content_kind="cbz",
        page_count=1,
        file_size=cbz.stat().st_size,
    )
    db_session.add(book)
    db_session.flush()
    chapter = Chapter(
        series_id=series.id,
        book_id=book.id,
        number="1",
        number_sort=1.0,
        language="en",
        page_count=1,
    )
    db_session.add(chapter)
    db_session.commit()
    chapter_id = chapter.id
    book_id = book.id

    resp = client.delete(f"/api/chapters/{chapter_id}")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "local"
    assert resp.json()["redownloadable"] is False

    assert not cbz.exists()
    assert client.get(f"/api/chapters/{chapter_id}").status_code == 404
    db_session.expire_all()
    assert db_session.get(Chapter, chapter_id) is None
    assert db_session.get(Book, book_id) is None
    # Series remains
    assert db_session.get(Series, series.id) is not None


def test_delete_missing_chapter_404(client: TestClient) -> None:
    assert client.delete("/api/chapters/does-not-exist").status_code == 404
