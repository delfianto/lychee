"""Tests for the series grid + detail API."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.downloads.provider import RemoteChapter, SeriesMetadata, register_provider
from src.tasks.queue import queue

from tests.support import make_series


class _FakeMetaProvider:
    """Satisfies both provider protocols; only get_metadata is exercised here."""

    id = "fakemeta"

    def list_chapters(self, provider_series_id: str, *, language: str = "en") -> list[RemoteChapter]:
        raise NotImplementedError

    def fetch_pages(self, chapter: RemoteChapter, *, data_saver: bool = False) -> list[bytes]:
        raise NotImplementedError

    def get_metadata(self, provider_series_id: str, *, language: str = "en") -> SeriesMetadata:
        return SeriesMetadata(
            provider_series_id=provider_series_id,
            title="Fetched Title",
            description="Fetched description.",
            year=2001,
            tags=[("Action", "genre")],
            authors=["Fetched Author"],
        )


register_provider(_FakeMetaProvider())


def test_list_series_empty(client: TestClient) -> None:
    resp = client.get("/api/series")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "nextCursor": None}


def test_list_and_detail_with_derived_counts(client: TestClient, db_session: Session) -> None:
    make_series(
        db_session,
        title="Berserk",
        kind="manga",
        chapter_count=5,
        unread=2,
        tag_ids=["action"],
        favorite=True,
    )
    db_session.commit()

    data = client.get("/api/series").json()
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["title"] == "Berserk"
    assert item["chapterCount"] == 5
    assert item["unreadCount"] == 2
    assert item["lastReadChapter"] == 3.0  # 3 of 5 read
    assert item["favorite"] is True
    assert item["coverUrl"].endswith(f"/api/series/{item['id']}/cover")
    assert item["tags"][0]["id"] == "action"

    detail = client.get(f"/api/series/{item['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == item["id"]


def test_detail_missing_is_404(client: TestClient) -> None:
    assert client.get("/api/series/does-not-exist").status_code == 404


def test_filter_by_kind_and_favorite(client: TestClient, db_session: Session) -> None:
    make_series(db_session, title="Manga A", kind="manga", favorite=True)
    make_series(db_session, title="Comic B", kind="comic", favorite=False)
    make_series(db_session, title="Gallery C", kind="gallery")
    db_session.commit()

    manga = client.get("/api/series", params={"kind": "manga"}).json()["items"]
    assert [s["title"] for s in manga] == ["Manga A"]

    favorites = client.get("/api/series", params={"favorite": "true"}).json()["items"]
    assert [s["title"] for s in favorites] == ["Manga A"]


def test_tag_include_and_exclude(client: TestClient, db_session: Session) -> None:
    make_series(db_session, title="Action Only", tag_ids=["action"])
    make_series(db_session, title="Action + Romance", tag_ids=["action", "romance"])
    make_series(db_session, title="Romance Only", tag_ids=["romance"])
    db_session.commit()

    only_action = client.get("/api/series", params={"tags": "action,-romance"}).json()["items"]
    assert [s["title"] for s in only_action] == ["Action Only"]

    both = client.get("/api/series", params={"tags": "action,romance", "tagMode": "and"}).json()
    assert [s["title"] for s in both["items"]] == ["Action + Romance"]


def test_sort_by_title(client: TestClient, db_session: Session) -> None:
    for title in ("Charlie", "alpha", "Bravo"):
        make_series(db_session, title=title)
    db_session.commit()

    titles = [s["title"] for s in client.get("/api/series", params={"sort": "title"}).json()["items"]]
    assert titles == ["alpha", "Bravo", "Charlie"]


def test_cursor_pagination_walks_all(client: TestClient, db_session: Session) -> None:
    for i in range(5):
        make_series(db_session, title=f"S{i}")
    db_session.commit()

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):  # safety bound
        params: dict[str, str | int] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = client.get("/api/series", params=params).json()
        seen.extend(s["id"] for s in page["items"])
        cursor = page["nextCursor"]
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5  # no dupes, no gaps


def test_patch_series_persists_action_row(client: TestClient, db_session: Session) -> None:
    series = make_series(db_session, title="Berserk")
    db_session.commit()

    resp = client.patch(
        f"/api/series/{series.id}",
        json={"favorite": True, "libraryStatus": "reading", "rating": 8},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["favorite"] is True
    assert body["libraryStatus"] == "reading"
    assert body["userRating"] == 8

    got = client.get(f"/api/series/{series.id}").json()
    assert (got["favorite"], got["libraryStatus"], got["userRating"]) == (True, "reading", 8)


def test_patch_series_partial_and_clear_rating(client: TestClient, db_session: Session) -> None:
    series = make_series(db_session, title="Frieren")
    db_session.commit()

    client.patch(f"/api/series/{series.id}", json={"rating": 9})
    client.patch(f"/api/series/{series.id}", json={"favorite": True})  # rating untouched
    got = client.get(f"/api/series/{series.id}").json()
    assert got["favorite"] is True
    assert got["userRating"] == 9

    client.patch(f"/api/series/{series.id}", json={"rating": None})  # clear
    assert client.get(f"/api/series/{series.id}").json()["userRating"] is None


def test_patch_series_invalid_status_and_missing(client: TestClient, db_session: Session) -> None:
    series = make_series(db_session, title="Saga")
    db_session.commit()
    assert client.patch(f"/api/series/{series.id}", json={"libraryStatus": "bogus"}).status_code == 400
    assert client.patch("/api/series/nope", json={"favorite": True}).status_code == 404


def test_refresh_fetches_and_applies_metadata(client: TestClient, db_session: Session) -> None:
    series = make_series(db_session, title="original folder", kind="manga")
    series.provider = "fakemeta"
    series.provider_series_id = "x1"
    db_session.commit()

    resp = client.post(f"/api/series/{series.id}/refresh")
    assert resp.status_code == 202
    queue.wait_idle()

    got = client.get(f"/api/series/{series.id}").json()
    assert got["title"] == "Fetched Title"
    assert got["year"] == 2001
    assert got["description"] == "Fetched description."
    assert "Fetched Author" in got["authors"]


def test_refresh_requires_a_provider_match(client: TestClient, db_session: Session) -> None:
    series = make_series(db_session, title="Unmatched")
    db_session.commit()
    assert client.post(f"/api/series/{series.id}/refresh").status_code == 400
    assert client.post("/api/series/nope/refresh").status_code == 404
