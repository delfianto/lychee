"""MangaDexProvider.get_metadata parsing (mock transport — no network)."""

import httpx
from src.providers.mangadex import MangaDexProvider
from src.providers.mangadex_client import API_BASE

_MANGA = {
    "data": {
        "id": "m1",
        "attributes": {
            "title": {"en": "Berserk"},
            "altTitles": [{"ja": "ベルセルク"}, {"en": "Berserk (alt)"}],
            "description": {"en": "A dark fantasy.", "fr": "Fantaisie sombre."},
            "status": "ongoing",
            "year": 1989,
            "contentRating": "suggestive",
            "publicationDemographic": "seinen",
            "originalLanguage": "ja",
            "lastChapter": "364",
            "tags": [
                {"attributes": {"name": {"en": "Adventure"}, "group": "genre"}},
                {"attributes": {"name": {"en": "Gore"}, "group": "content"}},
            ],
            "links": {"mal": "2", "al": "33", "raw": "https://ignored.example"},
        },
        "relationships": [
            {"type": "author", "attributes": {"name": "Kentaro Miura"}},
            {"type": "artist", "attributes": {"name": "Kentaro Miura"}},
            {"type": "cover_art", "attributes": {"fileName": "cover.jpg"}},
        ],
    }
}


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.startswith("/statistics/manga/"):
        return httpx.Response(200, json={"statistics": {"m1": {"rating": {"average": 8.4}}}})
    if path == "/manga/m1":
        return httpx.Response(200, json=_MANGA)
    return httpx.Response(404)


def test_get_metadata_parses_attributes_relationships_and_stats() -> None:
    provider = MangaDexProvider(
        client=httpx.Client(base_url=API_BASE, transport=httpx.MockTransport(_handler))
    )
    meta = provider.get_metadata("m1")

    assert meta.title == "Berserk"
    assert ("ja", "ベルセルク") in meta.alt_titles
    assert meta.description == "A dark fantasy."  # preferred language wins
    assert (meta.status, meta.year, meta.demographic) == ("ongoing", 1989, "seinen")
    assert meta.content_rating == "suggestive"
    assert meta.original_language == "ja"
    assert ("Adventure", "genre") in meta.tags
    assert ("Gore", "content") in meta.tags
    assert meta.authors == ["Kentaro Miura"]
    assert meta.artists == ["Kentaro Miura"]
    assert meta.cover_url == "https://uploads.mangadex.org/covers/m1/cover.jpg.512.jpg"
    assert meta.total_chapters == 364
    assert meta.community_rating == 8.4
    assert meta.external_ids == {"mal": "2", "al": "33"}  # only tracker links kept
