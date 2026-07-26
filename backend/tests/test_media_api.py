"""Tests for binary media serving: covers, chapter pages, gallery images."""

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session
from src.catalog.models import Book, Chapter, Series
from src.media.thumbnails import ThumbnailStore, ThumbVariant

from tests.support import ensure_library, make_series


def _write_pages(directory: Path, count: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        buf = io.BytesIO()
        Image.new("RGB", (40, 60), (10 * i, 20, 30)).save(buf, format="PNG")
        _ = (directory / f"{i + 1:03d}.png").write_bytes(buf.getvalue())


def _make_book_series(
    session: Session, tmp_path: Path, *, kind: str, pages: int, with_chapter: bool
) -> tuple[Series, Chapter | None]:
    root = tmp_path / "lib"
    library = ensure_library(session)
    library.path = str(root)
    series = Series(library_id=library.id, kind=kind, title="Media Series", sort_title="media")
    session.add(series)
    session.flush()

    _write_pages(root / series.id, pages)
    book = Book(
        series_id=series.id,
        library_id=library.id,
        path_rel=series.id,
        content_kind="image_dir",
        page_count=pages,
    )
    session.add(book)
    session.flush()

    chapter: Chapter | None = None
    if with_chapter:
        chapter = Chapter(
            series_id=series.id,
            book_id=book.id,
            number="1",
            number_sort=1.0,
            language="en",
            page_start=0,
            page_count=pages,
        )
        session.add(chapter)
        session.flush()
    session.commit()
    return series, chapter


def test_chapter_page_serving_and_304(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    _, chapter = _make_book_series(db_session, tmp_path, kind="manga", pages=3, with_chapter=True)
    assert chapter is not None

    resp = client.get(f"/api/chapters/{chapter.id}/pages/1")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"
    etag = resp.headers["etag"]

    cached = client.get(f"/api/chapters/{chapter.id}/pages/1", headers={"If-None-Match": etag})
    assert cached.status_code == 304

    assert client.get(f"/api/chapters/{chapter.id}/pages/9").status_code == 404


def test_cover_is_generated_as_avif(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    series, _ = _make_book_series(db_session, tmp_path, kind="manga", pages=2, with_chapter=True)

    resp = client.get(f"/api/series/{series.id}/cover")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/avif"
    assert b"ftyp" in resp.content[:16]
    # Served again from the store (now cached on disk).
    assert client.get(f"/api/series/{series.id}/cover").status_code == 200
    assert client.get("/api/series/missing/cover").status_code == 404


def test_cover_detail_serves_canonical_avif(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    series, _ = _make_book_series(db_session, tmp_path, kind="manga", pages=2, with_chapter=True)
    # ?size=detail serves the canonical cover bytes directly (not a store variant).
    resp = client.get(f"/api/series/{series.id}/cover", params={"size": "detail"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/avif"
    assert b"ftyp" in resp.content[:16]


def test_gallery_images_list_and_serve(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    series, _ = _make_book_series(db_session, tmp_path, kind="gallery", pages=4, with_chapter=False)

    first = client.get(f"/api/series/{series.id}/images", params={"limit": 2}).json()
    assert len(first["items"]) == 2
    assert first["items"][0]["url"] == f"/api/series/{series.id}/images/0"
    assert first["items"][0]["thumbUrl"] == f"/api/series/{series.id}/images/0/thumb"
    assert first["items"][0]["kind"] == "image"
    assert first["items"][0]["posterUrl"] is None
    assert first["nextCursor"] is not None

    second = client.get(
        f"/api/series/{series.id}/images", params={"limit": 2, "cursor": first["nextCursor"]}
    ).json()
    assert len(second["items"]) == 2
    assert second["nextCursor"] is None

    img = client.get(f"/api/series/{series.id}/images/0")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"

    # Lazy grid thumb: AVIF, not full PNG; second hit is cache.
    thumb = client.get(f"/api/series/{series.id}/images/0/thumb")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/avif"
    assert b"ftyp" in thumb.content[:32]
    assert client.get(f"/api/series/{series.id}/images/0/thumb").status_code == 200


def test_gallery_mp4_stream_and_range(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    """Progressive MP4 via FileResponse: full GET + Range 206."""
    root = tmp_path / "lib"
    library = ensure_library(db_session)
    library.path = str(root)
    series = Series(library_id=library.id, kind="gallery", title="Clips", sort_title="clips")
    db_session.add(series)
    db_session.flush()
    folder = root / series.id
    folder.mkdir(parents=True)
    # Minimal-ish MP4 is hard; use a small fake payload — FileResponse streams bytes as-is.
    # Browsers need real MP4; the server contract is media_type + Range, tested here.
    payload = b"0" * 4096 + b"mp4-test-payload"
    (folder / "clip.mp4").write_bytes(payload)
    book = Book(
        series_id=series.id,
        library_id=library.id,
        path_rel=series.id,
        content_kind="image_dir",
        page_count=1,
    )
    db_session.add(book)
    db_session.commit()

    listed = client.get(f"/api/series/{series.id}/images").json()
    assert listed["items"][0]["kind"] == "video"
    assert listed["items"][0]["thumbUrl"] == f"/api/series/{series.id}/images/0/thumb"
    assert listed["items"][0]["posterUrl"] == f"/api/series/{series.id}/images/0/poster"

    full = client.get(f"/api/series/{series.id}/images/0")
    assert full.status_code == 200
    assert full.headers["content-type"].startswith("video/mp4")
    assert full.content == payload
    assert full.headers.get("accept-ranges", "").lower() == "bytes"

    partial = client.get(f"/api/series/{series.id}/images/0", headers={"Range": "bytes=0-99"})
    assert partial.status_code == 206
    assert partial.content == payload[:100]
    assert partial.headers["content-range"].startswith("bytes 0-99/")


def test_related_and_art(client: TestClient, db_session: Session, tmp_path: Path) -> None:
    series, _ = _make_book_series(db_session, tmp_path, kind="manga", pages=1, with_chapter=True)
    other = Series(
        library_id=series.library_id, kind="manga", title="Sibling", sort_title="sibling"
    )
    db_session.add(other)
    db_session.commit()

    related = client.get(f"/api/series/{series.id}/related").json()
    assert series.id not in [s["id"] for s in related]
    assert other.id in [s["id"] for s in related]

    assert client.get(f"/api/series/{series.id}/art").json() == {"images": []}


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (100, 150), (120, 60, 40)).save(buf, format="PNG")
    return buf.getvalue()


def test_provider_cover_is_downloaded_and_served_locally(
    client: TestClient, db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.catalog import media

    series = make_series(db_session, title="Matched")  # no book — cover must come from the source
    series.cover_source = "https://uploads.mangadex.org/covers/x/cover.512.jpg"
    db_session.commit()
    monkeypatch.setattr(media, "_download_image", lambda _url: _png_bytes())  # no real network

    resp = client.get(f"/api/series/{series.id}/cover")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/avif"  # transcoded from the downloaded cover

    # coverUrl is local, and the cover is now cached
    listed = client.get("/api/series").json()["items"]
    assert (
        next(s for s in listed if s["id"] == series.id)["coverUrl"]
        == f"/api/series/{series.id}/cover"
    )
    assert ThumbnailStore(tmp_path / "storage" / "thumbnails").exists(series.id, ThumbVariant.COVER)


def test_page_render_with_width_downscales_and_caches(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    series, chapter = _make_book_series(
        db_session, tmp_path, kind="manga", pages=1, with_chapter=True
    )
    assert chapter is not None
    # replace page 1 with a wide image so a width cap actually downscales
    wide = io.BytesIO()
    Image.new("RGB", (400, 600), (30, 60, 90)).save(wide, "PNG")
    _ = (tmp_path / "lib" / series.id / "001.png").write_bytes(wide.getvalue())

    resp = client.get(f"/api/chapters/{chapter.id}/pages/1", params={"w": 150})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/avif"  # re-encoded
    rendered = Image.open(io.BytesIO(resp.content))
    rendered.load()
    assert rendered.width == 150  # downscaled from 400

    # second request is served from the disk render cache (identical bytes)
    again = client.get(f"/api/chapters/{chapter.id}/pages/1", params={"w": 150})
    assert again.content == resp.content
    assert list((tmp_path / "storage" / "renders").rglob("*.avif"))  # cached on disk


def test_page_without_width_serves_original(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    _, chapter = _make_book_series(db_session, tmp_path, kind="manga", pages=1, with_chapter=True)
    assert chapter is not None
    resp = client.get(f"/api/chapters/{chapter.id}/pages/1")
    assert resp.headers["content-type"] == "image/png"  # untouched original


def test_chapters_group_no_volume_first_then_descending(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    library = ensure_library(db_session)
    library.path = str(tmp_path / "lib")
    series = Series(library_id=library.id, kind="manga", title="Vol Test", sort_title="vol test")
    db_session.add(series)
    db_session.flush()
    book = Book(
        series_id=series.id,
        library_id=library.id,
        path_rel=series.id,
        content_kind="image_dir",
        page_count=1,
    )
    db_session.add(book)
    db_session.flush()
    for volume, number, sort in [(None, "100", 100.0), (1, "1", 1.0), (2, "10", 10.0)]:
        db_session.add(
            Chapter(
                series_id=series.id,
                book_id=book.id,
                volume=volume,
                number=number,
                number_sort=sort,
                page_count=1,
            )
        )
    db_session.commit()

    groups = client.get(f"/api/series/{series.id}/chapters").json()
    assert [g["volume"] for g in groups] == [None, 2, 1]  # No Volume first, then volumes descending
