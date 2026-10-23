"""Tests for ad-hoc reading mode (buffered loose files in temp/, never in real library)."""

from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.catalog.models import Book, Chapter, Library, Series
from src.downloads.provider import RemoteChapter, register_provider

from tests.support import make_series


def _jpeg_bytes(color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 96), color=color).save(buf, format="JPEG")
    return buf.getvalue()


class _AdhocWindowProvider:
    """Implements AdhocPageProvider so only the requested window of pages is fetched."""

    id = "adhocprov"

    def __init__(self, page_total: int = 6) -> None:
        self.page_total = page_total
        self.fetched_pages: list[int] = []

    def list_chapters(
        self, provider_series_id: str, *, language: str = "en"
    ) -> list[RemoteChapter]:
        return [
            RemoteChapter(
                provider_chapter_id=f"{provider_series_id}-ch1",
                number="1",
                volume=1,
                title="Opening",
                language=language,
            ),
            RemoteChapter(
                provider_chapter_id=f"{provider_series_id}-ch5",
                number="5",
                volume=1,
                title="Midpoint",
                language=language,
            ),
        ]

    def fetch_pages(
        self, chapter: RemoteChapter, *, data_saver: bool = False, on_page=None
    ) -> list[bytes]:
        return [_jpeg_bytes((i * 20, 40, 80)) for i in range(1, self.page_total + 1)]

    def fetch_adhoc_pages(
        self,
        chapter: RemoteChapter,
        directory: Path,
        *,
        start_page: int = 1,
        count: int = 4,
        data_saver: bool = False,
    ) -> tuple[int, list[int]]:
        directory.mkdir(parents=True, exist_ok=True)
        first = max(1, min(self.page_total, start_page))
        last = min(self.page_total, first + max(1, count) - 1)
        buffered: list[int] = []
        for page_num in range(first, last + 1):
            target = directory / f"{page_num:04d}.jpg"
            if not target.is_file():
                self.fetched_pages.append(page_num)
                target.write_bytes(_jpeg_bytes((page_num * 30, 50, 100)))
            buffered.append(page_num)
        return self.page_total, buffered


class _GenericPageProvider:
    """Provider that only implements fetch_pages (no fetch_adhoc_pages)."""

    id = "genericprov"

    def list_chapters(
        self, provider_series_id: str, *, language: str = "en"
    ) -> list[RemoteChapter]:
        return [
            RemoteChapter(
                provider_chapter_id="gen-ch2",
                number="2",
                volume=1,
                title="Second",
                language=language,
            )
        ]

    def fetch_pages(
        self, chapter: RemoteChapter, *, data_saver: bool = False, on_page=None
    ) -> list[bytes]:
        return [_jpeg_bytes((10, i * 30, 90)) for i in range(1, 6)]


def test_adhoc_reading_buffers_window_into_temp_not_library(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    provider = _AdhocWindowProvider(page_total=6)
    register_provider(provider)

    lib_dir = tmp_path / "manga_lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    lib = Library(name="Manga", path=str(lib_dir), kind="manga", enabled=True)
    db_session.add(lib)
    db_session.flush()

    series = Series(
        library_id=lib.id,
        kind="manga",
        title="Remote Manga",
        sort_title="remote manga",
        path_rel="Remote Manga",
        provider="adhocprov",
        provider_series_id="rm-1",
    )
    db_session.add(series)
    db_session.commit()

    # Read chapter 5 directly (not starting from the beginning) with preloadPages=2.
    adhoc_id = f"adhoc:{series.id}:rm-1-ch5"
    detail_resp = client.get(f"/api/chapters/{adhoc_id}", params={"preloadPages": 2})
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["id"] == adhoc_id
    assert detail["seriesId"] == series.id
    assert detail["number"] == "5"
    assert detail["title"] == "Midpoint"
    assert detail["pageCount"] == 6

    # Only pages 1 and 2 were fetched initially.
    assert provider.fetched_pages == [1, 2]

    # Loose files live strictly under <lib_dir>/temp/adhoc/<series.id>/rm-1-ch5/
    temp_chapter_dir = lib_dir / "temp" / "adhoc" / series.id / "rm-1-ch5"
    assert (temp_chapter_dir / "0001.jpg").is_file()
    assert (temp_chapter_dir / "0002.jpg").is_file()
    assert not (temp_chapter_dir / "0003.jpg").exists()

    # Nothing was written to the real library series folder or Book/Chapter tables.
    assert not (lib_dir / "Remote Manga").exists()
    assert db_session.scalars(select(Book).where(Book.series_id == series.id)).all() == []
    assert db_session.scalars(select(Chapter).where(Chapter.series_id == series.id)).all() == []

    # Buffer pages 3..4 via POST /api/chapters/{id}/buffer.
    buf_resp = client.post(
        f"/api/chapters/{adhoc_id}/buffer",
        json={"startPage": 3, "preloadPages": 2},
    )
    assert buf_resp.status_code == 200
    assert buf_resp.json() == {
        "chapterId": adhoc_id,
        "pageCount": 6,
        "bufferedPages": [3, 4],
    }
    assert provider.fetched_pages == [1, 2, 3, 4]
    assert (temp_chapter_dir / "0003.jpg").is_file()
    assert (temp_chapter_dir / "0004.jpg").is_file()

    # Serving page 3 and unbuffered page 6 (plus width-rendered page).
    p3 = client.get(f"/api/chapters/{adhoc_id}/pages/3")
    assert p3.status_code == 200
    assert p3.headers["content-type"] == "image/jpeg"

    p6_resized = client.get(f"/api/chapters/{adhoc_id}/pages/6", params={"w": 320})
    assert p6_resized.status_code == 200
    assert p6_resized.headers["content-type"] == "image/avif"

    # Out-of-range page returns 404.
    assert client.get(f"/api/chapters/{adhoc_id}/pages/99").status_code == 404

    # Progress updates on ad-hoc chapters are a safe 204 no-op.
    prog = client.put(f"/api/chapters/{adhoc_id}/progress", json={"page": 2})
    assert prog.status_code == 204


def test_generic_provider_adhoc_and_series_start_resolution(
    client: TestClient, db_session: Session
) -> None:
    register_provider(_GenericPageProvider())
    series = make_series(db_session, title="Generic Series", chapter_count=0)
    series.provider = "genericprov"
    series.provider_series_id = "gen-1"
    db_session.commit()

    # Navigating to /api/chapters/{series.id} ("Start reading") resolves the first remote chapter.
    start_detail = client.get(f"/api/chapters/{series.id}", params={"preloadPages": 3}).json()
    assert start_detail["id"] == f"adhoc:{series.id}:gen-ch2"
    assert start_detail["pageCount"] == 5

    # Subsequent buffer call hits cached meta.json and writes remaining loose files.
    buf = client.post(
        f"/api/chapters/adhoc:{series.id}:gen-ch2/buffer",
        json={"startPage": 4, "preloadPages": 2},
    ).json()
    assert buf["bufferedPages"] == [4, 5]

    # Repeat buffer on already-buffered range uses cached files without re-fetching.
    buf_cached = client.post(
        f"/api/chapters/adhoc:{series.id}:gen-ch2/buffer",
        json={"startPage": 1, "preloadPages": 2},
    ).json()
    assert buf_cached["bufferedPages"] == [1, 2]

    # Also test local downloaded chapter with /buffer and /api/chapters/{series_id}.
    local_series = make_series(db_session, title="Local Series", chapter_count=2, unread=1)
    db_session.commit()
    local_start = client.get(f"/api/chapters/{local_series.id}").json()
    assert local_start["seriesId"] == local_series.id
    assert local_start["number"] == "2"  # first unread chapter

    local_buf = client.post(
        f"/api/chapters/{local_start['id']}/buffer",
        json={"startPage": 1, "preloadPages": 4},
    ).json()
    assert local_buf["chapterId"] == local_start["id"]
    assert local_buf["bufferedPages"] == [1]

    # Invalid ad-hoc id returns 400.
    assert client.get("/api/chapters/adhoc:bad").status_code == 400
