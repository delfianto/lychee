"""Tests for reading-progress writes."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.support import make_series


def _first_unread_chapter_id(client: TestClient, series_id: str) -> str:
    groups = client.get(f"/api/series/{series_id}/chapters").json()
    for group in groups:
        for chapter in group["chapters"]:
            if not chapter["read"]:
                return chapter["id"]
    raise AssertionError("no unread chapter")


def test_completing_a_chapter_drops_unread(client: TestClient, db_session: Session) -> None:
    series = make_series(db_session, title="Berserk", chapter_count=3, unread=3)
    db_session.commit()
    assert client.get(f"/api/series/{series.id}").json()["unreadCount"] == 3

    chapter_id = _first_unread_chapter_id(client, series.id)
    resp = client.put(f"/api/chapters/{chapter_id}/progress", json={"page": 1})
    assert resp.status_code == 204

    detail = client.get(f"/api/series/{series.id}").json()
    assert detail["unreadCount"] == 2
    assert detail["lastReadChapter"] is not None


def test_partial_progress_does_not_complete(client: TestClient, db_session: Session) -> None:
    series = make_series(db_session, title="Frieren", chapter_count=2, unread=2)
    db_session.commit()
    chapter_id = _first_unread_chapter_id(client, series.id)

    # page 0 of a 1-page chapter → not complete; unread unchanged.
    resp = client.put(f"/api/chapters/{chapter_id}/progress", json={"page": 0})
    assert resp.status_code == 204
    assert client.get(f"/api/series/{series.id}").json()["unreadCount"] == 2


def test_explicit_completed_flag(client: TestClient, db_session: Session) -> None:
    series = make_series(db_session, title="Saga", chapter_count=2, unread=2)
    db_session.commit()
    chapter_id = _first_unread_chapter_id(client, series.id)

    client.put(f"/api/chapters/{chapter_id}/progress", json={"page": 0, "completed": True})
    assert client.get(f"/api/series/{series.id}").json()["unreadCount"] == 1


def test_progress_on_missing_chapter_404(client: TestClient) -> None:
    assert client.put("/api/chapters/nope/progress", json={"page": 1}).status_code == 404
