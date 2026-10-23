"""Readable oneshots, confirmed empty feeds, language mismatches and failed checks."""

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.downloads.provider import register_provider
from src.providers.mangadex import MangaDexProvider
from src.providers.mangadex_client import API_BASE, MangaDexClient

from tests.support import make_series


def chapter(pid="oneshot", *, language="en", pages=7, unavailable=False, external=None):
    return {
        "id": pid,
        "attributes": {
            "chapter": None,
            "volume": None,
            "translatedLanguage": language,
            "pages": pages,
            "isUnavailable": unavailable,
            "externalUrl": external,
            "publishAt": "2024-07-19T07:49:06+00:00",
        },
    }


def provider_for(records, *, fail=False):
    state = {"fail": fail, "requests": []}

    def handle(request):
        state["requests"].append(request)
        if state["fail"]:
            return httpx.Response(503)
        rows = records
        if request.url.params.get("translatedLanguage[]"):
            rows = [
                row
                for row in rows
                if row["attributes"]["translatedLanguage"]
                == request.url.params["translatedLanguage[]"]
            ]
        if request.url.params.get("includeUnavailable") == "0":
            rows = [
                row
                for row in rows
                if not row["attributes"]["isUnavailable"]
                and row["attributes"]["pages"] > 0
                and not row["attributes"]["externalUrl"]
            ]
        return httpx.Response(200, json={"data": rows, "total": len(rows)})

    provider = MangaDexProvider(
        api=MangaDexClient(
            client=httpx.Client(base_url=API_BASE, transport=httpx.MockTransport(handle)),
            max_retries=0,
        )
    )
    register_provider(provider)
    return state


def linked(db_session):
    series = make_series(db_session, title="Unnumbered oneshot")
    series.provider = "mangadex"
    series.provider_series_id = "fcdfec78-1b75-4f3f-a640-dc4ce2ea85b1"
    db_session.commit()
    return series.id


def test_real_oneshot_shape_is_available_and_not_deduplicated(
    client: TestClient, db_session: Session
):
    sid = linked(db_session)
    state = provider_for([chapter(), chapter("second-unnumbered")])
    response = client.get(f"/api/series/{sid}/chapters")
    assert response.status_code == 200
    rows = [c for v in response.json() for c in v["chapters"]]
    assert len(rows) == 2
    assert all(c["number"] == "Oneshot" and c["status"] == "available" for c in rows)
    status = client.get(f"/api/series/{sid}/chapter-availability").json()
    assert status["status"] == "ready" and status["availableCount"] == 2
    assert status["checkedAt"]
    requests = len(state["requests"])
    client.get(f"/api/series/{sid}/chapters")
    assert len(state["requests"]) == requests


@pytest.mark.parametrize(
    ("records", "status"),
    [
        ([], "no_chapters"),
        ([chapter(language="fr")], "language_unavailable"),
        ([chapter(pages=0, unavailable=True)], "unavailable"),
        ([chapter(pages=0, external="https://publisher.example/read")], "external_only"),
    ],
)
def test_confirmed_empty_states(client: TestClient, db_session: Session, records, status):
    sid = linked(db_session)
    provider_for(records)
    assert client.get(f"/api/series/{sid}/chapters").json() == []
    data = client.get(f"/api/series/{sid}/chapter-availability").json()
    assert data["status"] == status
    if status == "language_unavailable":
        assert data["availableLanguages"] == ["fr"]
        # Explicit language changes must refresh a previously empty preferred-language index.
        groups = client.get(f"/api/series/{sid}/chapters?language=fr").json()
        assert len(groups[0]["chapters"]) == 1
        assert (
            client.get(f"/api/series/{sid}/chapter-availability?language=fr").json()["status"]
            == "ready"
        )


def test_failed_check_is_not_a_confirmed_empty_result_and_can_retry(
    client: TestClient, db_session: Session
):
    sid = linked(db_session)
    state = provider_for([chapter()], fail=True)
    assert client.get(f"/api/series/{sid}/chapters").json() == []
    status = client.get(f"/api/series/{sid}/chapter-availability").json()
    assert status["status"] == "error"
    count = len(state["requests"])
    client.get(f"/api/series/{sid}/chapters")
    assert len(state["requests"]) == count  # short cooldown, not a hammering retry loop
    state["fail"] = False
    retried = client.get(f"/api/series/{sid}/chapter-availability?refresh=true").json()
    assert retried["status"] == "ready"
    assert client.get(f"/api/series/{sid}/chapters").json()[0]["chapters"][0]["number"] == "Oneshot"
    assert client.get("/api/series/nope/chapter-availability").status_code == 404
