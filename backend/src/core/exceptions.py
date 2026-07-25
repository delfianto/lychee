"""Domain exceptions.

Services (and routers) raise these; a single handler in ``main.py`` maps each to its
HTTP status, so the service layer stays HTTP-agnostic. Never raise ``HTTPException``.
"""

from typing import Any


class LycheeError(Exception):
    """Base application error. ``status_code`` is the HTTP status the global handler
    maps it to; ``code`` is the stable machine-readable slug in the error body."""

    status_code: int = 400
    code: str = "error"

    def __init__(self, message: str, detail: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class BadRequestError(LycheeError):
    """Malformed or inapplicable request (HTTP 400)."""

    status_code = 400
    code = "bad_request"


class NotFoundError(LycheeError):
    """A requested resource does not exist (HTTP 404)."""

    status_code = 404
    code = "not_found"


class ConflictError(LycheeError):
    """A uniqueness or state conflict (HTTP 409)."""

    status_code = 409
    code = "conflict"


class ValidationError(LycheeError):
    """Input that parsed but fails a business rule (HTTP 422)."""

    status_code = 422
    code = "validation_error"
