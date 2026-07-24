"""Shared API schema conventions.

- ``CamelModel`` — base for every request/response model so JSON is **camelCase**
  (matching ``frontend/src/types/index.ts``) while Python stays snake_case.
  FastAPI serializes response models ``by_alias`` by default, and ``populate_by_name``
  lets request bodies arrive as either casing.
- ``Page`` / ``OffsetPage`` — the two pagination envelopes: cursor for grids/feeds,
  offset for the settings taxonomy table.
- ``encode_cursor`` / ``decode_cursor`` — opaque keyset-pagination cursors.
"""

import base64
import json
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model: camelCase JSON aliases, populate-by-name, ORM-friendly."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class Page[T](CamelModel):
    """Cursor-paginated envelope for grids and feeds."""

    items: list[T]
    next_cursor: str | None = None


class OffsetPage[T](CamelModel):
    """Offset/page-paginated envelope (the settings taxonomy table)."""

    items: list[T]
    total: int
    page: int
    page_size: int


def encode_cursor(data: dict[str, Any]) -> str:
    """Opaque, URL-safe cursor encoding a keyset position."""
    raw = json.dumps(data, separators=(",", ":"), default=str).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> dict[str, Any]:
    """Inverse of :func:`encode_cursor`; raises ``ValueError`` on malformed input."""
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid cursor") from exc
