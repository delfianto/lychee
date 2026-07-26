"""Provider matching: scan auto-match + manual match/unlink endpoints (fakes, no network)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.catalog.matching import auto_match_library
from src.downloads.provider import MangaMatch, RemoteChapter, SeriesMetadata, register_provider
from src.tasks.queue import queue

from tests.support import ensure_library, make_series


class _MatchingProvider:
    """A 'mangadex' provider whose search echoes the query title (→ an exact match)."""

    id = "mangadex"

    def list_chapters(
        self, provider_series_id: str, *, language: str = "en"
    ) -> list[RemoteChapter]:
        return []

    def fetch_pages(
        self, chapter: RemoteChapter, *, data_saver: bool = False, on_page=None
    ) -> list[bytes]:
        return []

    def search(self, title: str, *, limit: int = 5) -> list[MangaMatch]:
        return [MangaMatch(provider_series_id="mx-1", title=title, year=1989, status="ongoing")]

    def get_metadata(self, provider_series_id: str, *, language: str = "en") -> SeriesMetadata:
        return SeriesMetadata(
            provider_series_id=provider_series_id,
            title="Berserk (Matched)",
            description="Fetched.",
            year=1989,
            authors=["Miura"],
        )

    def list_new_chapters(
        self, provider_series_id: str, *, known: set[str], language: str = "en"
    ) -> list[RemoteChapter]:
        return []


def test_auto_match_library_adopts_exact_title(db_session: Session) -> None:
    register_provider(_MatchingProvider())
    library = ensure_library(db_session)
    series = make_series(db_session, title="Berserk", kind="manga")
    db_session.commit()

    matched = auto_match_library(db_session, library.id)
    db_session.commit()

    assert matched == 1
    assert series.provider == "mangadex"
    assert series.provider_series_id == "mx-1"
    assert series.title == "Berserk (Matched)"  # metadata applied
    assert series.description == "Fetched."


def test_auto_match_skips_when_no_exact_title(db_session: Session) -> None:
    class _NoExact(_MatchingProvider):
        def search(self, title: str, *, limit: int = 5) -> list[MangaMatch]:
            return [MangaMatch(provider_series_id="mx-2", title="Something Else")]

    register_provider(_NoExact())
    library = ensure_library(db_session)
    series = make_series(db_session, title="Unique Title", kind="manga")
    db_session.commit()

    assert auto_match_library(db_session, library.id) == 0
    assert series.provider is None  # left for manual matching


def test_manual_match_then_unlink(client: TestClient, db_session: Session) -> None:
    register_provider(_MatchingProvider())  # override the offline provider for this test
    series = make_series(db_session, title="Frieren", kind="manga")
    db_session.commit()

    candidates = client.get(f"/api/series/{series.id}/match-candidates").json()
    assert candidates[0]["providerSeriesId"] == "mx-1"

    resp = client.post(f"/api/series/{series.id}/match", json={"providerSeriesId": "mx-1"})
    assert resp.status_code == 202
    queue.wait_idle()
    assert client.get(f"/api/series/{series.id}").json()["title"] == "Berserk (Matched)"

    assert client.delete(f"/api/series/{series.id}/match").status_code == 204
    # unlinked → a refresh is now rejected
    assert client.post(f"/api/series/{series.id}/refresh").status_code == 400
