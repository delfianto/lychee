"""MangaDex account: connect (encrypted secrets) + follows import (monkeypatched, no network)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.catalog.models import Book, Chapter, Library, Series
from src.core.config import settings
from src.core.crypto import decrypt
from src.downloads.provider import CustomList, SeriesMetadata
from src.integrations.models import Provider
from src.progress.models import ReadingProgress
from src.providers import mangadex_account
from src.providers.mangadex_auth import TokenPair
from src.tasks.queue import queue


class _FakeAuthedProvider:
    def list_follows(self, *, language: str = "en") -> list[SeriesMetadata]:
        return [
            SeriesMetadata(
                provider_series_id="md-1",
                title="Imported Manga",
                year=2011,
                tags=[("Action", "genre")],
            ),
            SeriesMetadata(provider_series_id="md-2", title="Listed Manga", year=2020),
        ]

    def reading_status(self) -> dict[str, str]:
        return {"md-1": "reading"}

    def list_custom_lists(self) -> list[CustomList]:
        return [CustomList(provider_list_id="list-1", name="Faves", manga_ids=["md-1", "md-2"])]

    def read_markers(self, manga_ids: list[str]) -> dict[str, list[str]]:
        return {"md-1": ["c1"]}

    def list_ratings(self, manga_ids: list[str]) -> dict[str, int]:
        # Personal scores from MangaDex (md-1 rated 9; md-2 unrated).
        return {"md-1": 9}

    def push_status(self, provider_series_id: str, status: str | None) -> None:
        return None

    def push_read(self, provider_series_id: str, chapter_ids: list[str]) -> None:
        return None

    def push_rating(self, provider_series_id: str, rating: int | None) -> None:
        return None


def test_connect_stores_encrypted_secrets(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-key")
    monkeypatch.setattr(
        mangadex_account, "password_grant", lambda **_kw: TokenPair("acc", "refresh-1")
    )

    resp = client.post(
        "/api/providers/mangadex/connect",
        json={"clientId": "cid", "clientSecret": "csecret", "username": "me", "password": "pw"},
    )
    assert resp.status_code == 200
    assert resp.json()["connected"] is True
    assert resp.json()["accountName"] == "me"

    row = db_session.get(Provider, "mangadex")
    assert row is not None
    assert row.client_secret_enc not in (None, "csecret")  # stored ciphertext, not plaintext
    assert decrypt(row.client_secret_enc or "") == "csecret"
    assert decrypt(row.refresh_token_enc or "") == "refresh-1"


def test_sync_creates_series_status_and_lists(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-key")
    monkeypatch.setattr(
        mangadex_account, "password_grant", lambda **_kw: TokenPair("acc", "refresh-1")
    )
    assert (
        client.post(
            "/api/providers/mangadex/connect",
            json={"clientId": "cid", "clientSecret": "csecret", "username": "me", "password": "pw"},
        ).status_code
        == 200
    )

    monkeypatch.setattr(
        mangadex_account, "refresh_grant", lambda **_kw: TokenPair("acc2", "refresh-2")
    )
    monkeypatch.setattr(mangadex_account, "_authed_provider", lambda _token: _FakeAuthedProvider())

    assert client.post("/api/providers/mangadex/sync").status_code == 202
    queue.wait_idle()

    items = {s["title"]: s for s in client.get("/api/series").json()["items"]}
    assert items["Imported Manga"]["libraryStatus"] == "reading"  # status → shelf
    assert items["Imported Manga"]["provider"] == "mangadex"
    assert items["Imported Manga"]["userRating"] == 9  # personal rating from /rating
    assert items["Listed Manga"].get("userRating") in (None,)  # unrated on MD → left alone

    # each custom list → a managed Collection with its members
    collections = {c["name"]: c for c in client.get("/api/collections").json()}
    assert "Faves" in collections
    detail = client.get(f"/api/collections/{collections['Faves']['id']}").json()
    assert {s["title"] for s in detail["series"]} == {"Imported Manga", "Listed Manga"}

    # re-sync is idempotent (no duplicate series / collections / members)
    assert client.post("/api/providers/mangadex/sync").status_code == 202
    queue.wait_idle()
    md = [s for s in client.get("/api/series").json()["items"] if s["provider"] == "mangadex"]
    assert len(md) == 2
    assert len([c for c in client.get("/api/collections").json() if c["name"] == "Faves"]) == 1

    db_session.expire_all()
    row = db_session.get(Provider, "mangadex")
    assert row is not None
    assert decrypt(row.refresh_token_enc or "") == "refresh-2"  # rotated token persisted


def test_sync_marks_read_chapters_of_downloaded_series(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-key")
    monkeypatch.setattr(
        mangadex_account, "password_grant", lambda **_kw: TokenPair("acc", "refresh-1")
    )
    assert (
        client.post(
            "/api/providers/mangadex/connect",
            json={"clientId": "cid", "clientSecret": "csecret", "username": "me", "password": "pw"},
        ).status_code
        == 200
    )
    monkeypatch.setattr(
        mangadex_account, "refresh_grant", lambda **_kw: TokenPair("acc2", "refresh-2")
    )
    monkeypatch.setattr(mangadex_account, "_authed_provider", lambda _token: _FakeAuthedProvider())

    # a downloaded series+chapter for md-1 (as if matched to MangaDex + downloaded)
    library = Library(name="Downloads", path="mangadex://dl", kind="mixed")
    db_session.add(library)
    db_session.flush()
    series = Series(
        library_id=library.id,
        kind="manga",
        title="Imported Manga",
        sort_title="imported manga",
        provider="mangadex",
        provider_series_id="md-1",
    )
    db_session.add(series)
    db_session.flush()
    book = Book(
        series_id=series.id,
        library_id=library.id,
        path_rel="md-1/c1.cbz",
        content_kind="cbz",
        page_count=2,
    )
    db_session.add(book)
    db_session.flush()
    chapter = Chapter(
        series_id=series.id,
        book_id=book.id,
        number="1",
        number_sort=1.0,
        page_count=2,
        provider="mangadex",
        provider_chapter_id="c1",
    )
    db_session.add(chapter)
    db_session.commit()
    chapter_id = chapter.id

    assert client.post("/api/providers/mangadex/sync").status_code == 202
    queue.wait_idle()

    groups = client.get(f"/api/series/{series.id}/chapters").json()
    read = {c["id"]: c["read"] for group in groups for c in group["chapters"]}
    assert read[chapter_id] is True  # MangaDex read marker → local chapter marked read


def _connect(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-key")
    monkeypatch.setattr(
        mangadex_account, "password_grant", lambda **_kw: TokenPair("acc", "refresh-1")
    )
    assert (
        client.post(
            "/api/providers/mangadex/connect",
            json={"clientId": "cid", "clientSecret": "csecret", "username": "me", "password": "pw"},
        ).status_code
        == 200
    )


def _dex_series(db_session: Session, provider_series_id: str, **kw: object) -> Series:
    library = db_session.scalar(select(Library).where(Library.name == "Downloads")) or Library(
        name="Downloads", path="mangadex://dl", kind="mixed"
    )
    db_session.add(library)
    db_session.flush()
    series = Series(
        library_id=library.id,
        kind="manga",
        title=provider_series_id,
        sort_title=provider_series_id,
        provider="mangadex",
        provider_series_id=provider_series_id,
        **kw,
    )
    db_session.add(series)
    db_session.flush()
    return series


def test_push_series_sends_status_and_read_markers(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _connect(client, monkeypatch)
    series = _dex_series(db_session, "md-9", library_status="completed")
    book = Book(
        series_id=series.id,
        library_id=series.library_id,
        path_rel="md-9/c.cbz",
        content_kind="cbz",
        page_count=1,
    )
    db_session.add(book)
    db_session.flush()
    chapter = Chapter(
        series_id=series.id,
        book_id=book.id,
        number="1",
        page_count=1,
        provider="mangadex",
        provider_chapter_id="ch-9",
    )
    db_session.add(chapter)
    db_session.flush()
    db_session.add(ReadingProgress(chapter_id=chapter.id, series_id=series.id, completed=True))
    db_session.commit()

    calls: dict[str, object] = {}

    class _Recorder:
        def push_status(self, mid: str, status: str | None) -> None:
            calls["status"] = (mid, status)

        def push_read(self, mid: str, ids: list[str]) -> None:
            calls["read"] = (mid, ids)

        def push_rating(self, mid: str, rating: int | None) -> None:
            calls["rating"] = (mid, rating)

    monkeypatch.setattr(mangadex_account, "_access_token", lambda *_a: "tok")
    monkeypatch.setattr(mangadex_account, "_authed_provider", lambda _t: _Recorder())

    series.user_rating = 8.0
    db_session.commit()

    assert mangadex_account.push_series(db_session, series.id) is True
    assert calls["status"] == ("md-9", "completed")  # shelf → MangaDex status
    assert calls["read"] == ("md-9", ["ch-9"])  # completed chapter → read marker
    assert calls["rating"] == ("md-9", 8)  # personal score → /rating


def test_shelf_change_enqueues_mangadex_push(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _connect(client, monkeypatch)
    series = _dex_series(db_session, "md-7")
    db_session.commit()
    series_id = series.id

    pushed: list[str] = []
    monkeypatch.setattr(mangadex_account, "push_series", lambda _s, sid: bool(pushed.append(sid)))

    assert (
        client.patch(f"/api/series/{series_id}", json={"libraryStatus": "completed"}).status_code
        == 200
    )
    queue.wait_idle()
    assert pushed == [series_id]  # a shelf change pushes the dex-linked series to MangaDex


def test_rating_change_enqueues_mangadex_push(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _connect(client, monkeypatch)
    series = _dex_series(db_session, "md-rate")
    db_session.commit()
    series_id = series.id

    pushed: list[str] = []
    monkeypatch.setattr(mangadex_account, "push_series", lambda _s, sid: bool(pushed.append(sid)))

    assert client.patch(f"/api/series/{series_id}", json={"rating": 7}).status_code == 200
    queue.wait_idle()
    assert pushed == [series_id]
    detail = client.get(f"/api/series/{series_id}").json()
    assert detail["userRating"] == 7


def test_sync_requires_connection(client: TestClient) -> None:
    assert client.post("/api/providers/mangadex/sync").status_code == 400
