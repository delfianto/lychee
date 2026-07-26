"""Tests for chapters, update feeds, dashboard, and search."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.catalog.models import Book

from tests.support import make_series


def test_chapters_grouped_with_read_flags(client: TestClient, db_session: Session) -> None:
    series = make_series(db_session, title="Berserk", chapter_count=5, unread=2)
    db_session.commit()

    groups = client.get(f"/api/series/{series.id}/chapters").json()
    assert len(groups) == 1  # factory chapters share a null volume
    chapters = groups[0]["chapters"]
    assert [c["number"] for c in chapters] == ["5", "4", "3", "2", "1"]  # desc default
    assert [c["read"] for c in chapters] == [False, False, True, True, True]

    asc = client.get(f"/api/series/{series.id}/chapters", params={"order": "asc"}).json()
    assert [c["number"] for c in asc[0]["chapters"]] == ["1", "2", "3", "4", "5"]


def test_chapters_missing_series_404(client: TestClient) -> None:
    assert client.get("/api/series/missing/chapters").status_code == 404


def test_chapter_detail(client: TestClient, db_session: Session) -> None:
    series = make_series(db_session, title="Frieren", chapter_count=3, unread=3)
    db_session.commit()
    first = client.get(f"/api/series/{series.id}/chapters").json()[0]["chapters"][-1]

    detail = client.get(f"/api/chapters/{first['id']}").json()
    assert detail["seriesId"] == series.id
    assert detail["number"] == "1"
    assert detail["pageCount"] == 1
    assert detail["read"] is False

    assert client.get("/api/chapters/nope").status_code == 404


def test_updates_and_unread_feeds(client: TestClient, db_session: Session) -> None:
    make_series(db_session, title="Reading Manga", chapter_count=4, unread=1)
    make_series(db_session, title="Art Set", kind="gallery", image_count=10)
    db_session.commit()

    updates = client.get("/api/updates").json()
    assert len(updates["items"]) == 4  # gallery contributes no chapter updates
    assert updates["items"][0]["series"]["title"] == "Reading Manga"
    assert "updatedAt" in updates["items"][0]

    unread = client.get("/api/updates/unread").json()
    assert len(unread["items"]) == 1  # only the single unread chapter


def test_dashboard_shape(client: TestClient, db_session: Session) -> None:
    make_series(
        db_session,
        title="In Progress",
        chapter_count=10,
        unread=3,
        library_status="reading",
    )
    make_series(db_session, title="Gallery", kind="gallery", image_count=5)
    db_session.commit()

    data = client.get("/api/dashboard").json()
    assert data["stats"]["series"] == 1  # galleries excluded from the count
    assert data["stats"]["unreadChapters"] == 3
    assert data["stats"]["reading"] == 1
    assert [s["title"] for s in data["continueReading"]] == ["In Progress"]
    assert len(data["recentUpdates"]) == 10
    assert {s["title"] for s in data["recentlyAdded"]} == {"In Progress", "Gallery"}


def test_search(client: TestClient, db_session: Session) -> None:
    make_series(db_session, title="Berserk")
    make_series(db_session, title="Frieren")
    db_session.commit()

    assert [s["title"] for s in client.get("/api/search", params={"q": "ber"}).json()] == [
        "Berserk"
    ]
    assert client.get("/api/search", params={"q": ""}).json() == []


def test_library_summary(client: TestClient, db_session: Session) -> None:
    make_series(db_session, title="M", kind="manga", chapter_count=1)
    db_session.commit()
    book = db_session.scalars(select(Book)).first()
    assert book is not None
    book.file_size = 2_000_000_000  # 2 GB
    db_session.commit()

    data = client.get("/api/libraries/summary").json()
    assert {"key": "manga", "title": "Manga", "sizeGb": 2.0} in data
