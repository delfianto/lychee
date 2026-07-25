"""MangaDex account: connect (encrypted secrets) + follows import (monkeypatched, no network)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.core.config import settings
from src.core.crypto import decrypt
from src.downloads.provider import CustomList, SeriesMetadata
from src.integrations.models import Provider
from src.providers import mangadex_account
from src.providers.mangadex_auth import TokenPair
from src.tasks.queue import queue


class _FakeAuthedProvider:
    def list_follows(self, *, language: str = "en") -> list[SeriesMetadata]:
        return [
            SeriesMetadata(
                provider_series_id="md-1", title="Imported Manga", year=2011, tags=[("Action", "genre")]
            ),
            SeriesMetadata(provider_series_id="md-2", title="Listed Manga", year=2020),
        ]

    def reading_status(self) -> dict[str, str]:
        return {"md-1": "reading"}

    def list_custom_lists(self) -> list[CustomList]:
        return [CustomList(provider_list_id="list-1", name="Faves", manga_ids=["md-1", "md-2"])]


def test_connect_stores_encrypted_secrets(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-key")
    monkeypatch.setattr(mangadex_account, "password_grant", lambda **_kw: TokenPair("acc", "refresh-1"))

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
    monkeypatch.setattr(mangadex_account, "password_grant", lambda **_kw: TokenPair("acc", "refresh-1"))
    assert client.post(
        "/api/providers/mangadex/connect",
        json={"clientId": "cid", "clientSecret": "csecret", "username": "me", "password": "pw"},
    ).status_code == 200

    monkeypatch.setattr(mangadex_account, "refresh_grant", lambda **_kw: TokenPair("acc2", "refresh-2"))
    monkeypatch.setattr(mangadex_account, "_authed_provider", lambda _token: _FakeAuthedProvider())

    assert client.post("/api/providers/mangadex/sync").status_code == 202
    queue.wait_idle()

    items = {s["title"]: s for s in client.get("/api/series").json()["items"]}
    assert items["Imported Manga"]["libraryStatus"] == "reading"  # status → shelf
    assert items["Imported Manga"]["provider"] == "mangadex"

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


def test_sync_requires_connection(client: TestClient) -> None:
    assert client.post("/api/providers/mangadex/sync").status_code == 400
