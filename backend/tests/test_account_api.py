"""MangaDex account: connect (encrypted secrets) + follows import (monkeypatched, no network)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.core.config import settings
from src.core.crypto import decrypt
from src.downloads.provider import SeriesMetadata
from src.integrations import service
from src.integrations.models import Provider
from src.providers.mangadex_auth import TokenPair
from src.tasks.queue import queue


class _FakeAuthedProvider:
    def list_follows(self, *, language: str = "en") -> list[SeriesMetadata]:
        return [
            SeriesMetadata(
                provider_series_id="md-1", title="Imported Manga", year=2011, tags=[("Action", "genre")]
            )
        ]

    def reading_status(self) -> dict[str, str]:
        return {"md-1": "reading"}


def test_connect_stores_encrypted_secrets(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-key")
    monkeypatch.setattr(service, "password_grant", lambda **_kw: TokenPair("acc", "refresh-1"))

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


def test_import_creates_followed_series_with_status(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-key")
    monkeypatch.setattr(service, "password_grant", lambda **_kw: TokenPair("acc", "refresh-1"))
    assert client.post(
        "/api/providers/mangadex/connect",
        json={"clientId": "cid", "clientSecret": "csecret", "username": "me", "password": "pw"},
    ).status_code == 200

    monkeypatch.setattr(service, "refresh_grant", lambda **_kw: TokenPair("acc2", "refresh-2"))
    monkeypatch.setattr(service, "_authed_provider", lambda _token: _FakeAuthedProvider())

    assert client.post("/api/providers/mangadex/import").status_code == 202
    queue.wait_idle()

    items = {s["title"]: s for s in client.get("/api/series").json()["items"]}
    assert "Imported Manga" in items
    assert items["Imported Manga"]["libraryStatus"] == "reading"
    assert items["Imported Manga"]["provider"] == "mangadex"

    db_session.expire_all()
    row = db_session.get(Provider, "mangadex")
    assert row is not None
    assert decrypt(row.refresh_token_enc or "") == "refresh-2"  # rotated token persisted


def test_import_requires_connection(client: TestClient) -> None:
    assert client.post("/api/providers/mangadex/import").status_code == 400
