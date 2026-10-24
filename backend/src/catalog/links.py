"""Trusted provider URLs derived from catalog identifiers."""

from urllib.parse import quote


def source_url(
    provider: str | None, identifier: str | None, *, chapter: bool = False
) -> str | None:
    if provider != "mangadex" or not identifier:
        return None
    return f"https://mangadex.org/{'chapter' if chapter else 'title'}/{quote(identifier, safe='')}"
