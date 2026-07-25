"""Symmetric encryption for provider secrets at rest.

The OAuth client secret + refresh token are encrypted with Fernet using a key
derived from ``settings.secret_key`` (env ``LYCHEE_SECRET_KEY``). With no key
configured, encryption is unavailable and connecting an account is refused — so
secrets are never written in plaintext. Rotating the key invalidates stored
secrets (the user just re-connects).
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from src.core.config import settings
from src.core.exceptions import BadRequestError


def is_configured() -> bool:
    return bool(settings.secret_key)


def _cipher() -> Fernet:
    if not settings.secret_key:
        raise BadRequestError(
            "set LYCHEE_SECRET_KEY to connect an account (it encrypts stored secrets)"
        )
    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _cipher().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise BadRequestError("stored secret can't be decrypted (LYCHEE_SECRET_KEY changed?)") from exc
