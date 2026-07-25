"""Secret encryption at rest (Fernet from LYCHEE_SECRET_KEY)."""

import pytest
from src.core.config import settings
from src.core.crypto import decrypt, encrypt, is_configured
from src.core.exceptions import BadRequestError


def test_encrypt_round_trips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "secret_key", "unit-test-key")
    token = encrypt("s3cret")
    assert token != "s3cret"
    assert decrypt(token) == "s3cret"
    assert is_configured()


def test_encrypt_requires_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "secret_key", None)
    assert not is_configured()
    with pytest.raises(BadRequestError):
        _ = encrypt("x")


def test_decrypt_with_wrong_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "secret_key", "key-a")
    token = encrypt("data")
    monkeypatch.setattr(settings, "secret_key", "key-b")
    with pytest.raises(BadRequestError):
        _ = decrypt(token)
