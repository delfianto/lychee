"""Tests for the series grid + detail API."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.downloads.provider import RemoteChapter, SeriesMetadata, register_provider
from src.tasks.queue import queue

from tests.support import make_series


class _FakeMetaProvider:
    """Satisfies both provider protocols; only get_metadata is exercised here."""

    id = "fakemeta"

    def list_chapters(
        self, provider_series_id: str, *, language: str = "en"
    ) -> list[RemoteChapter]:
        raise NotImplementedError

    def fetch_pages(
        self, chapter: RemoteChapter, *, data_saver: bool = False, on_page=None
    ) -> list[bytes]:
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
    assert item["coverUrl"].endswith(f"/api/series/{item['id']}/cover?v=2")
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

    multi = client.get("/api/series", params={"kind": "manga,comics"}).json()["items"]
    assert {s["title"] for s in multi} == {"Manga A", "Comic B"}

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

    titles = [
        s["title"] for s in client.get("/api/series", params={"sort": "title"}).json()["items"]
    ]
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
    assert (
        client.patch(f"/api/series/{series.id}", json={"libraryStatus": "bogus"}).status_code == 400
    )
    assert client.patch("/api/series/nope", json={"favorite": True}).status_code == 404


def test_patch_series_edits_metadata(client: TestClient, db_session: Session) -> None:
    series = make_series(db_session, title="old title", kind="manga", tag_ids=["action"])
    db_session.commit()

    resp = client.patch(
        f"/api/series/{series.id}",
        json={
            "title": "Berserk",
            "description": "A dark fantasy epic.",
            "authors": ["Kentaro Miura"],
            "artists": ["Kentaro Miura"],
            "originCountry": "JP",
            "year": 1989,
            "status": "hiatus",
            "contentRating": "pornographic",
            "demographic": "seinen",
            "tagIds": ["romance"],
        },
    )
    assert resp.status_code == 200

    got = client.get(f"/api/series/{series.id}").json()
    assert got["title"] == "Berserk"
    assert got["description"] == "A dark fantasy epic."
    assert got["authors"] == ["Kentaro Miura"]
    assert got["artists"] == ["Kentaro Miura"]
    assert got["originCountry"] == "jp"  # normalized to lowercase alpha-2
    assert got["year"] == 1989
    assert got["status"] == "hiatus"
    assert got["contentRating"] == "pornographic"
    assert got["demographic"] == "seinen"
    assert [t["id"] for t in got["tags"]] == ["romance"]


def test_patch_edit_locks_field_against_refresh(client: TestClient, db_session: Session) -> None:
    """A manually edited field is locked, so a later provider refresh leaves it alone
    while still applying the fields the user didn't touch."""
    series = make_series(db_session, title="local name", kind="manga")
    series.provider = "fakemeta"
    series.provider_series_id = "x1"
    db_session.commit()

    # Edit title + authors → locks "title" and "credits".
    edit = client.patch(
        f"/api/series/{series.id}", json={"title": "My Title", "authors": ["My Author"]}
    )
    assert edit.status_code == 200

    assert client.post(f"/api/series/{series.id}/refresh").status_code == 202
    queue.wait_idle()

    got = client.get(f"/api/series/{series.id}").json()
    assert got["title"] == "My Title"  # locked — provider "Fetched Title" ignored
    assert got["authors"] == ["My Author"]  # credits locked
    assert got["year"] == 2001  # not locked — provider value applied
    assert got["description"] == "Fetched description."  # not locked


def test_patch_gallery_source_and_characters(client: TestClient, db_session: Session) -> None:
    gallery = make_series(db_session, title="Art Set", kind="gallery", image_count=12)
    db_session.commit()

    resp = client.patch(
        f"/api/series/{gallery.id}",
        json={"source": "Genshin Impact", "characters": ["Raiden Shogun", "Yae Miko"]},
    )
    assert resp.status_code == 200
    got = client.get(f"/api/series/{gallery.id}").json()
    assert got["source"] == "Genshin Impact"
    assert got["characters"] == ["Raiden Shogun", "Yae Miko"]


def test_patch_unknown_tag_is_400(client: TestClient, db_session: Session) -> None:
    series = make_series(db_session, title="Tagless")
    db_session.commit()
    assert (
        client.patch(f"/api/series/{series.id}", json={"tagIds": ["does-not-exist"]}).status_code
        == 400
    )


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


def test_chapters_synced_at_reflects_index_sync(client: TestClient, db_session: Session) -> None:
    """Distinguishes "never synced" (null) from "synced, provider has zero chapters"."""
    unmatched = make_series(db_session, title="Unmatched2")
    matched = make_series(db_session, title="Matched, unsynced")
    matched.provider = "mangadex"
    matched.provider_series_id = "does-not-matter"
    db_session.commit()

    assert client.get(f"/api/series/{unmatched.id}").json()["chaptersSyncedAt"] is None
    assert client.get(f"/api/series/{matched.id}").json()["chaptersSyncedAt"] is None

    # Loading the chapters list triggers a best-effort remote-index sync; the offline
    # provider stub (conftest) returns zero chapters — the "provider genuinely has no
    # chapters" case, not "never synced".
    assert client.get(f"/api/series/{matched.id}/chapters").json() == []
    got = client.get(f"/api/series/{matched.id}").json()
    assert got["chaptersSyncedAt"] is not None
    assert got["availableChapters"] == 0


def test_library_filter_scopes_gallery_cursor_pages(
    client: TestClient, db_session: Session
) -> None:
    from src.catalog.models import Library

    first = Library(name="First gallery", path="/gallery/first", kind="gallery")
    second = Library(name="Second gallery", path="/gallery/second", kind="gallery")
    db_session.add_all([first, second])
    db_session.flush()
    for title, library in [("A", first), ("B", second), ("C", first)]:
        series = make_series(db_session, title=title, kind="gallery")
        series.library_id = library.id
    db_session.commit()

    params = {"kind": "gallery", "libraryId": first.id, "sort": "title", "limit": 1}
    page = client.get("/api/series", params=params).json()
    assert [s["title"] for s in page["items"]] == ["A"]
    assert page["nextCursor"]
    page = client.get("/api/series", params={**params, "cursor": page["nextCursor"]}).json()
    assert [s["title"] for s in page["items"]] == ["C"]
    assert page["nextCursor"] is None
    assert client.get("/api/series", params={"libraryId": "missing"}).json()["items"] == []


def test_rating_sort_is_highest_first_across_ties_and_cursors(
    client: TestClient, db_session: Session
) -> None:
    for index, score in enumerate([None, 3.2, 9.8, 0.0, 9.8]):
        make_series(db_session, title=f"Rated {index}", rating=score)
    db_session.commit()
    ratings = []
    cursor = None
    while True:
        params = {"sort": "rating", "limit": 1}
        if cursor:
            params["cursor"] = cursor
        page = client.get("/api/series", params=params).json()
        ratings.extend(s["rating"] for s in page["items"])
        cursor = page["nextCursor"]
        if not cursor:
            break
    assert ratings == [9.8, 9.8, 3.2, 0.0, None]


def test_recently_updated_uses_source_chapters_then_local_chapter_creation(
    client: TestClient, db_session: Session
) -> None:
    from datetime import UTC, datetime

    from sqlalchemy import select
    from src.catalog.models import Chapter, Series
    from src.catalog.remote_chapters import upsert_provider_chapters
    from src.downloads.provider import RemoteChapter

    old = make_series(db_session, title="Old source", chapter_count=1)
    new = make_series(db_session, title="New source", chapter_count=1)
    local = make_series(db_session, title="Local release", chapter_count=1)
    no_chapters = make_series(db_session, title="No chapters", chapter_count=0)
    for series in [old, new, local, no_chapters]:
        series.created_at = datetime(2020, 1, 1, tzinfo=UTC)
    for series in [old, new]:
        series.provider = "mangadex"
        series.provider_series_id = series.id
    for series, date in [(old, "2021-01-01T00:00:00+00:00"), (new, "2024-01-01T00:00:00+00:00")]:
        upsert_provider_chapters(
            db_session,
            series,
            [RemoteChapter("remote-" + series.id, "1", None, None, "en", published_at=date)],
        )
        chapter = db_session.scalar(select(Chapter).where(Chapter.series_id == series.id))
        assert chapter is not None
        chapter.created_at = datetime(
            2026, 1, 1, tzinfo=UTC
        )  # downloading an old release cannot make it new
    chapter = db_session.scalar(select(Chapter).where(Chapter.series_id == local.id))
    assert chapter is not None
    chapter.created_at = datetime(2023, 1, 1, tzinfo=UTC)
    db_session.commit()
    # Local metadata edits invert the order, but must not affect content chronology.
    old.title = "Old source (edited)"
    db_session.commit()
    ids = []
    cursor = None
    while True:
        params = {"sort": "recentlyUpdated", "limit": 1}
        if cursor:
            params["cursor"] = cursor
        page = client.get("/api/series", params=params).json()
        ids.extend(s["id"] for s in page["items"])
        cursor = page["nextCursor"]
        if not cursor:
            break
    assert ids == [new.id, local.id, old.id, no_chapters.id]
    db_session.expire_all()
    assert db_session.get(Series, old.id) is not None
