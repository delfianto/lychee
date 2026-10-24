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


def test_older_page_save_cannot_clear_completion(client: TestClient, db_session: Session) -> None:
    from sqlalchemy import select
    from src.catalog.models import Chapter
    from src.progress.models import ReadingProgress

    series = make_series(db_session, title="Sticky", chapter_count=1, unread=1)
    chapter = db_session.scalar(select(Chapter).where(Chapter.series_id == series.id))
    assert chapter is not None
    chapter.page_count = 8
    db_session.commit()
    assert client.put(f"/api/chapters/{chapter.id}/progress", json={"page": 8}).status_code == 204
    assert client.put(f"/api/chapters/{chapter.id}/progress", json={"page": 2}).status_code == 204
    db_session.expire_all()
    state = db_session.scalar(
        select(ReadingProgress).where(ReadingProgress.chapter_id == chapter.id)
    )
    assert state and state.completed and state.current_page == 8
    assert client.get(f"/api/series/{series.id}/chapters").json()[0]["chapters"][0]["read"]
    assert client.put(
        f"/api/series/{series.id}/read-status",
        json={"chapterIds": [chapter.id], "completed": False},
    ).json() == {"updated": 1}
    db_session.expire_all()
    assert not state.completed and state.current_page == 0


def test_provider_only_progress_and_manual_batch_survive_download_removal(
    client: TestClient, db_session: Session
) -> None:
    from datetime import UTC, datetime

    from sqlalchemy import select
    from src.catalog.models import Chapter, ProviderChapter
    from src.progress.models import ProviderReadingProgress

    series = make_series(db_session, title="Remote", chapter_count=1, unread=1)
    series.provider = "mangadex"
    series.provider_series_id = "md-title"
    series.chapter_index_at = datetime.now(UTC)
    series.chapter_index_language = "en"
    series.chapter_availability_json = {"status": "ready", "language": "en"}
    chapter = db_session.scalar(select(Chapter).where(Chapter.series_id == series.id))
    assert chapter is not None
    chapter.provider = "mangadex"
    chapter.provider_chapter_id = "remote-1"
    for n in (1, 2):
        db_session.add(
            ProviderChapter(
                series_id=series.id,
                provider="mangadex",
                provider_chapter_id=f"remote-{n}",
                number=str(n),
                number_sort=n,
                language="en",
                last_seen_at=datetime.now(UTC),
            )
        )
    db_session.commit()
    adhoc = f"adhoc:{series.id}:remote-2"
    assert (
        client.put(
            f"/api/chapters/{adhoc}/progress", json={"page": 5, "completed": True}
        ).status_code
        == 204
    )
    assert client.put(f"/api/chapters/{adhoc}/progress", json={"page": 1}).status_code == 204
    db_session.expire_all()
    remote = db_session.scalar(
        select(ProviderReadingProgress).where(
            ProviderReadingProgress.provider_chapter_id == "remote-2"
        )
    )
    assert remote and remote.completed and remote.current_page == 5
    assert len(db_session.scalars(select(Chapter).where(Chapter.series_id == series.id)).all()) == 1
    assert client.put(
        f"/api/series/{series.id}/read-status",
        json={"chapterIds": [chapter.id, adhoc, chapter.id], "completed": True},
    ).json() == {"updated": 2}
    assert client.get(f"/api/series/{series.id}").json()["unreadCount"] == 0
    db_session.delete(chapter)
    db_session.commit()
    rows = client.get(f"/api/series/{series.id}/chapters").json()[0]["chapters"]
    assert len(rows) == 2 and all(row["read"] for row in rows)
    assert all(row["sourceUrl"].startswith("https://mangadex.org/chapter/") for row in rows)
    assert (
        client.get(f"/api/series/{series.id}").json()["sourceUrl"]
        == "https://mangadex.org/title/md-title"
    )
    assert (
        client.put(
            f"/api/series/{series.id}/read-status", json={"chapterIds": [adhoc], "completed": False}
        ).status_code
        == 200
    )
    rows = client.get(f"/api/series/{series.id}/chapters").json()[0]["chapters"]
    assert {row["number"]: row["read"] for row in rows} == {"1": True, "2": False}


def test_batch_validation_changes_nothing_and_rejects_bad_positions(
    client: TestClient, db_session: Session
) -> None:
    one = make_series(db_session, title="One", chapter_count=1, unread=1)
    two = make_series(db_session, title="Two", chapter_count=1, unread=1)
    db_session.commit()
    a, b = (_first_unread_chapter_id(client, series.id) for series in (one, two))
    endpoint = f"/api/series/{one.id}/read-status"
    assert client.put(endpoint, json={"chapterIds": [a, b], "completed": True}).status_code == 400
    assert (
        client.put(endpoint, json={"chapterIds": [a, "nope"], "completed": True}).status_code == 404
    )
    assert client.put(endpoint, json={"chapterIds": [], "completed": True}).status_code == 422
    assert client.get(f"/api/series/{one.id}").json()["unreadCount"] == 1
    assert client.put(f"/api/chapters/{a}/progress", json={"page": -1}).status_code == 422
    assert (
        client.put("/api/chapters/adhoc:missing:chapter/progress", json={"page": 1}).status_code
        == 404
    )
    assert client.put("/api/chapters/adhoc:invalid/progress", json={"page": 1}).status_code == 400
