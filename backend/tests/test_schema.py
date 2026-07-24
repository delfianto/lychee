"""Tests for the shared API schema conventions."""

import pytest
from src.core.schema import CamelModel, OffsetPage, Page, decode_cursor, encode_cursor


class _Item(CamelModel):
    series_id: str
    unread_count: int


def test_camel_alias_output_and_input() -> None:
    item = _Item(series_id="s1", unread_count=3)  # constructed by field name
    assert item.model_dump(by_alias=True) == {"seriesId": "s1", "unreadCount": 3}
    # …and camelCase input is accepted too (populate_by_name).
    parsed = _Item.model_validate({"seriesId": "s2", "unreadCount": 5})
    assert (parsed.series_id, parsed.unread_count) == ("s2", 5)


def test_page_envelope_is_camel() -> None:
    page = Page[_Item](items=[_Item(series_id="s1", unread_count=0)], next_cursor="abc")
    dumped = page.model_dump(by_alias=True)
    assert dumped["nextCursor"] == "abc"
    assert dumped["items"][0]["seriesId"] == "s1"


def test_offset_page_envelope_is_camel() -> None:
    page = OffsetPage[_Item](items=[], total=38, page=0, page_size=20)
    assert page.model_dump(by_alias=True) == {"items": [], "total": 38, "page": 0, "pageSize": 20}


def test_cursor_roundtrip() -> None:
    cursor = encode_cursor({"created_at": "2026-07-24T00:00:00Z", "id": "s1"})
    assert decode_cursor(cursor) == {"created_at": "2026-07-24T00:00:00Z", "id": "s1"}


def test_decode_cursor_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="invalid cursor"):
        decode_cursor("!!!not-base64!!!")
