"""Tracker OAuth connect flow: begin (authorize URL) + callback (token) — no network."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.core.config import settings
from src.core.crypto import decrypt
from src.integrations.models import Tracker
from src.trackers.base import TokenPair, register_tracker


class _FakeAniList:
    id = "anilist"
    external_id_key = "al"
    auth_kind = "oauth"
    uses_pkce = False

    def login(self, *, username: str, password: str) -> TokenPair:
        raise NotImplementedError

    def authorize_url(
        self, *, client_id: str, redirect_uri: str, state: str, code_challenge: str | None = None
    ) -> str:
        return f"https://fake/authorize?client_id={client_id}&state={state}"

    def exchange_code(
        self,
        *,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> TokenPair:
        assert code == "the-code"
        return TokenPair("access-1", "refresh-1")

    def account_name(self, access_token: str) -> str | None:
        return "AniUser"

    def push(self, *, access_token: str, media_id: str, status: str, progress: int) -> None:
        pass


class _FakeMangaUpdates:
    id = "mangaupdates"
    external_id_key = "mu"
    auth_kind = "credentials"
    uses_pkce = False

    def authorize_url(
        self, *, client_id: str, redirect_uri: str, state: str, code_challenge: str | None = None
    ) -> str:
        raise NotImplementedError

    def exchange_code(
        self,
        *,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> TokenPair:
        raise NotImplementedError

    def login(self, *, username: str, password: str) -> TokenPair:
        return TokenPair(f"sess-{username}")

    def account_name(self, access_token: str) -> str | None:
        return "u"

    def push(self, *, access_token: str, media_id: str, status: str, progress: int) -> None:
        pass


def test_connect_returns_authorize_url_and_encrypts_secret(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-key")
    resp = client.post(
        "/api/trackers/anilist/connect",
        json={"clientId": "cid", "clientSecret": "csecret", "redirectUri": "http://localhost/cb"},
    )
    assert resp.status_code == 200
    assert "client_id=cid" in resp.json()["authorizeUrl"]

    row = db_session.get(Tracker, "anilist")
    assert row is not None
    assert row.client_id == "cid"
    assert decrypt(row.client_secret_enc or "") == "csecret"
    assert row.connected is False  # not connected until the callback


def test_callback_completes_and_stores_encrypted_token(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-key")
    register_tracker(_FakeAniList())  # avoid the real network exchange

    client.post(
        "/api/trackers/anilist/connect",
        json={"clientId": "cid", "clientSecret": "csecret", "redirectUri": "http://cb"},
    )
    resp = client.post(
        "/api/trackers/anilist/callback", json={"code": "the-code", "redirectUri": "http://cb"}
    )
    assert resp.status_code == 200
    assert resp.json()["connected"] is True
    assert resp.json()["accountName"] == "AniUser"

    db_session.expire_all()
    row = db_session.get(Tracker, "anilist")
    assert row is not None
    assert decrypt(row.access_token_enc or "") == "access-1"


def test_myanimelist_connect_uses_pkce(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-key")
    resp = client.post(
        "/api/trackers/myanimelist/connect",
        json={"clientId": "cid", "clientSecret": "csec", "redirectUri": "http://cb"},
    )
    assert resp.status_code == 200
    url = resp.json()["authorizeUrl"]
    assert "code_challenge_method=plain" in url

    row = db_session.get(Tracker, "myanimelist")
    assert row is not None and row.pkce_verifier  # a verifier is stored for the callback
    assert f"code_challenge={row.pkce_verifier}" in url  # plain PKCE: challenge == verifier


def test_connect_unsupported_tracker_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-key")
    resp = client.post(
        "/api/trackers/novelupdates/connect",
        json={"clientId": "c", "clientSecret": "s", "redirectUri": "u"},
    )
    assert resp.status_code == 400  # no implementation registered (NovelUpdates has no public API)


def test_credentials_login_connects_and_encrypts_token(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-key")
    register_tracker(_FakeMangaUpdates())

    resp = client.post("/api/trackers/mangaupdates/login", json={"username": "me", "password": "pw"})
    assert resp.status_code == 200
    assert resp.json()["connected"] is True
    assert resp.json()["accountName"] == "me"

    row = db_session.get(Tracker, "mangaupdates")
    assert row is not None
    assert decrypt(row.access_token_enc or "") == "sess-me"


def test_oauth_tracker_rejects_password_login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-key")
    # AniList is OAuth → the credentials login endpoint refuses it.
    resp = client.post("/api/trackers/anilist/login", json={"username": "u", "password": "p"})
    assert resp.status_code == 400
