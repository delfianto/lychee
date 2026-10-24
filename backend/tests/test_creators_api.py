"""Creator filters are role-specific, literal, and usable without a title query."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.support import make_series


def test_creator_search_filters_and_autocomplete(client: TestClient, db_session: Session) -> None:
    first = make_series(
        db_session, title="Alpha", authors=["Writer A", "Writer B"], artists=["Artist X"]
    )
    second = make_series(db_session, title="Beta", authors=["Writer B"], artists=["Writer A"])
    special = make_series(db_session, title="Literal", authors=["100%_Name"], artists=["Zed"])
    db_session.commit()
    assert client.get("/api/creators", params={"role": "author", "q": "writer"}).json() == [
        "Writer A",
        "Writer B",
    ]
    assert client.get("/api/creators", params={"role": "artist", "q": "writer"}).json() == [
        "Writer A"
    ]
    assert client.get("/api/creators", params={"role": "author", "q": "%_"}).json() == ["100%_Name"]
    assert len(client.get("/api/creators", params={"role": "author", "limit": 1}).json()) == 1
    assert client.get("/api/creators", params={"role": "invalid"}).status_code == 422
    assert [s["id"] for s in client.get("/api/search", params={"author": " writer a "}).json()] == [
        first.id
    ]
    assert [s["id"] for s in client.get("/api/search", params={"artist": "writer a"}).json()] == [
        second.id
    ]
    assert [s["id"] for s in client.get("/api/search", params={"author": "%_"}).json()] == [
        special.id
    ]
    assert [
        s["id"]
        for s in client.get(
            "/api/search", params={"author": "writer b", "artist": "x", "q": "Alpha"}
        ).json()
    ] == [first.id]
    assert client.get("/api/search", params={"author": "unknown"}).json() == []
    rows = client.get("/api/series", params={"author": "writer b", "artist": "writer a"}).json()[
        "items"
    ]
    assert [s["id"] for s in rows] == [second.id]
