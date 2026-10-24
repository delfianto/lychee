"""FTS5 trigram full-text search over series title / alt-titles / authors.

The index is maintained by DB triggers created in the test harness (conftest), so
inserting series via ``make_series`` populates it automatically.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.catalog.models import TitleVariant

from tests.support import make_series


def _titles(client: TestClient, q: str) -> list[str]:
    return [s["title"] for s in client.get("/api/search", params={"q": q}).json()]


def test_matches_substring_case_insensitively(client: TestClient, db_session: Session) -> None:
    make_series(db_session, title="Berserk")
    make_series(db_session, title="Frieren")
    db_session.commit()

    assert _titles(client, "erser") == ["Berserk"]  # mid-word substring (trigram)
    assert _titles(client, "BERSERK") == ["Berserk"]  # case-insensitive
    assert _titles(client, "zzz") == []  # no trigram match


def test_matches_alternative_titles(client: TestClient, db_session: Session) -> None:
    series = make_series(db_session, title="Attack on Titan", authors=("Hajime Isayama",))
    db_session.add(
        TitleVariant(series_id=series.id, title="Shingeki no Kyojin", variant_type="romanized")
    )
    db_session.commit()

    assert _titles(client, "Shingeki") == ["Attack on Titan"]  # found via alt title


def test_matches_authors(client: TestClient, db_session: Session) -> None:
    make_series(db_session, title="Naruto", authors=("Masashi Kishimoto",))
    make_series(db_session, title="Bleach", authors=("Tite Kubo",))
    db_session.commit()

    assert _titles(client, "Kishimoto") == ["Naruto"]  # found via author only


def test_title_outranks_author_match(client: TestClient, db_session: Session) -> None:
    make_series(db_session, title="Berserk", authors=("Kentaro Miura",))
    make_series(db_session, title="Gantz", authors=("Berserk Admirer",))
    db_session.commit()

    titles = _titles(client, "Berserk")
    assert set(titles) == {"Berserk", "Gantz"}
    assert titles[0] == "Berserk"  # title weight beats an author-only hit


def test_multiple_terms_are_all_required(client: TestClient, db_session: Session) -> None:
    make_series(db_session, title="Dragon Ball")
    make_series(db_session, title="Dragon Quest")
    db_session.commit()

    assert _titles(client, "dragon ball") == ["Dragon Ball"]  # every term must match


def test_short_query_falls_back_to_like(client: TestClient, db_session: Session) -> None:
    make_series(db_session, title="One Piece")
    db_session.commit()

    # a 2-char query yields no trigram; the LIKE fallback still substring-matches the title
    assert _titles(client, "On") == ["One Piece"]


def test_empty_query_returns_nothing(client: TestClient, db_session: Session) -> None:
    make_series(db_session, title="Vagabond")
    db_session.commit()

    assert client.get("/api/search", params={"q": ""}).json() == []
    assert client.get("/api/search", params={"q": "   "}).json() == []


def test_search_reparented_credits_refresh_both_series(
    client: TestClient, db_session: Session
) -> None:
    from sqlalchemy import select
    from src.catalog.models import SeriesCredit

    first = make_series(db_session, title="First", authors=("Unique Writer",))
    second = make_series(db_session, title="Second")
    db_session.commit()
    assert _titles(client, "Unique Writer") == ["First"]
    credit = db_session.scalar(
        select(SeriesCredit).where(
            SeriesCredit.series_id == first.id, SeriesCredit.role == "author"
        )
    )
    assert credit is not None
    credit.series_id = second.id
    db_session.commit()
    assert _titles(client, "Unique Writer") == ["Second"]


def test_search_uncommitted_flush_and_rollback(db_session: Session) -> None:
    from src.catalog.search_index import search_ids

    series = make_series(db_session, title="Original")
    db_session.commit()
    series_id = series.id
    series.title = "Temporary"
    db_session.flush()
    assert search_ids(db_session, "Temporary") == [series_id]
    db_session.rollback()
    assert search_ids(db_session, "Original") == [series_id]
    assert search_ids(db_session, "Temporary") == []


def test_literal_search_terms_are_escaped(client: TestClient, db_session: Session) -> None:
    make_series(db_session, title="O'Brien Chronicle")
    make_series(db_session, title="Unrelated")
    db_session.commit()
    assert _titles(client, "O'Brien") == ["O'Brien Chronicle"]
    assert _titles(client, "x' OR 1=1 --") == []
