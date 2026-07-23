"""Domain exceptions.

Services (and routers) raise these; a single handler in ``main.py`` maps each to its
HTTP status, so the service layer stays HTTP-agnostic. Never raise ``HTTPException``.
"""

from typing import Any


class LycheeError(Exception):
    """Base application error. ``status_code`` is what the global handler maps it to."""

    status_code: int = 400

    def __init__(self, message: str, detail: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class BadRequestError(LycheeError):
    """Malformed or inapplicable request (HTTP 400)."""

    status_code = 400


class NotFoundError(LycheeError):
    """A requested resource does not exist (HTTP 404)."""

    status_code = 404


class ConflictError(LycheeError):
    """A uniqueness or state conflict (HTTP 409)."""

    status_code = 409


class ValidationError(LycheeError):
    """Input that parsed but fails a business rule (HTTP 422)."""

    status_code = 422
