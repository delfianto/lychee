"""MDList workflows use HTTP mocks: never mutate a real MangaDex account."""

import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.catalog.models import Series
from src.integrations.models import Provider
from src.providers import mangadex_account as account
from src.tasks.queue import queue

from tests.support import make_series

LIST = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
USER = "33333333-3333-4333-8333-333333333333"
MANGA = "44444444-4444-4444-8444-444444444444"
CHAPTER = "55555555-5555-4555-8555-555555555555"


def raw_list(
    list_id=LIST, *, owner=USER, name="My MDList", manga=None, visibility="private", version=1
):
    return {
        "id": list_id,
        "type": "custom_list",
        "attributes": {"name": name, "visibility": visibility, "version": version},
        "relationships": [{"type": "user", "id": owner}]
        + [{"type": "manga", "id": mid} for mid in (manga or [])],
    }


@pytest.fixture
def upstream(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch):
    config = db_session.get(Provider, "mangadex")
    assert config is not None
    config.client_id = "test-client"
    config.client_secret_enc = "encrypted-test-value"
    config.refresh_token_enc = "encrypted-test-value"
    config.fetch_covers = False
    db_session.commit()
    monkeypatch.setattr(account, "_access_token", lambda *_: "test-token")
    state = {
        "lists": {
            LIST: raw_list(manga=[MANGA]),
            OTHER: raw_list(
                OTHER, owner="another-owner", name="Public list", manga=[MANGA], visibility="public"
            ),
        },
        "requests": [],
        "fail": None,
        "followed": False,
    }

    def handle(request: httpx.Request):
        state["requests"].append(request)
        path, method = request.url.path, request.method
        if state["fail"] == (method, path):
            return httpx.Response(409, json={"result": "error"})
        if path == "/user/me":
            return httpx.Response(200, json={"data": {"id": USER}})
        if path in {"/user/list", f"/user/{USER}/list", "/user/follows/list"}:
            items = (
                [state["lists"][OTHER]]
                if path == f"/user/{USER}/list"
                or (path == "/user/follows/list" and state["followed"])
                else [state["lists"][LIST]]
                if path == "/user/list"
                else []
            )
            return httpx.Response(200, json={"data": items, "total": len(items)})
        if path == "/list" and method == "POST":
            data = json.loads(request.content)
            created = raw_list(str(uuid4()), name=data["name"], visibility=data["visibility"])
            state["lists"][created["id"]] = created
            return httpx.Response(200, json={"data": created})
        if path.startswith("/list/"):
            list_id = path.split("/")[2]
            if path.endswith("/follow"):
                state["followed"] = method == "POST"
                return httpx.Response(200, json={"result": "ok"})
            if path.endswith("/feed"):
                return httpx.Response(
                    200,
                    json={
                        "total": 1,
                        "data": [
                            {
                                "id": CHAPTER,
                                "attributes": {
                                    "chapter": "12",
                                    "title": "New chapter",
                                    "translatedLanguage": "en",
                                    "publishAt": "2026-10-24T01:00:00Z",
                                },
                                "relationships": [
                                    {"type": "manga", "id": MANGA},
                                    {
                                        "type": "scanlation_group",
                                        "id": "group",
                                        "attributes": {"name": "Test group"},
                                    },
                                ],
                            }
                        ],
                    },
                )
            if list_id not in state["lists"]:
                return httpx.Response(404)
            if method == "GET":
                return httpx.Response(200, json={"data": state["lists"][list_id]})
            if method == "PUT":
                data = json.loads(request.content)
                assert data["version"] == state["lists"][list_id]["attributes"]["version"]
                state["lists"][list_id]["attributes"].update(data)
                state["lists"][list_id]["attributes"]["version"] += 1
                return httpx.Response(200, json={"data": state["lists"][list_id]})
            if method == "DELETE":
                del state["lists"][list_id]
                return httpx.Response(200, json={"result": "ok"})
        if path.startswith("/manga/") and "/list/" in path:
            manga_id, list_id = path.split("/")[2], path.split("/")[4]
            entries = state["lists"][list_id]["relationships"]
            state["lists"][list_id]["relationships"] = [
                r for r in entries if r["type"] != "manga" or r["id"] != manga_id
            ]
            if method == "POST":
                state["lists"][list_id]["relationships"].append({"type": "manga", "id": manga_id})
            return httpx.Response(200, json={"result": "ok"})
        raise AssertionError(f"Unexpected upstream request {method} {path}")

    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle))
    )
    series = make_series(db_session, title="Remote manga")
    series.provider = "mangadex"
    series.provider_series_id = MANGA
    db_session.commit()
    state["series_id"] = series.id
    return state


def complete(client: TestClient, response):
    assert response.status_code == 202, response.text
    queue.wait_idle()
    task = next(t for t in client.get("/api/tasks").json() if t["id"] == response.json()["id"])
    assert task["status"] == "done", task
    return task["result"]


def test_import_owner_metadata_and_write_through(client: TestClient, db_session: Session, upstream):
    result = complete(
        client,
        client.post(
            "/api/collections/mangadex/import",
            json={"reference": f"https://mangadex.org/list/{LIST}/test"},
        ),
    )
    cid = result["collectionId"]
    data = client.get(f"/api/collections/{cid}").json()
    assert data["owned"] and data["editable"]
    assert data["sourceUrl"] == f"https://mangadex.org/list/{LIST}"
    assert data["lastSyncedAt"] and data["visibility"] == "private"
    assert len(data["series"]) == 1
    renamed = client.patch(
        f"/api/collections/{cid}", json={"name": "Renamed", "visibility": "public"}
    )
    assert renamed.status_code == 200, renamed.text
    assert upstream["lists"][LIST]["attributes"]["name"] == "Renamed"
    assert renamed.json()["visibility"] == "public"
    series_id = upstream["series_id"]
    assert client.delete(f"/api/collections/{cid}/series/{series_id}").status_code == 200
    assert (
        client.post(f"/api/collections/{cid}/series", json={"seriesId": series_id}).status_code
        == 200
    )
    # Idempotent membership uses the dedicated endpoint, not a stale full-list overwrite.
    assert (
        client.post(f"/api/collections/{cid}/series", json={"seriesId": series_id}).status_code
        == 200
    )
    assert client.delete(f"/api/collections/{cid}?remote=true").status_code == 204
    assert LIST not in upstream["lists"]
    assert db_session.get(Series, series_id) is not None


def test_followed_readonly_feed_and_local_removal(client: TestClient, upstream):
    cid = complete(
        client, client.post("/api/collections/mangadex/import", json={"reference": OTHER})
    )["collectionId"]
    url = f"/api/collections/{cid}"
    assert client.get(url).json()["editable"] is False
    assert client.patch(url, json={"name": "No"}).status_code == 400
    assert client.delete(f"{url}?remote=true").status_code == 400
    assert client.post(f"{url}/series", json={"seriesId": upstream["series_id"]}).status_code == 400
    assert client.delete(f"{url}/series/{upstream['series_id']}").status_code == 400
    assert client.put(f"{url}/follow", json={"followed": True}).json()["followed"] is True
    assert client.put(f"{url}/follow", json={"followed": False}).json()["followed"] is False
    feed = client.get(f"{url}/feed?language=en").json()
    assert feed["items"][0]["mangaTitle"] == "Remote manga"
    assert feed["items"][0]["seriesId"] == upstream["series_id"]
    assert feed["items"][0]["chapterId"] == CHAPTER
    request = next(r for r in upstream["requests"] if r.url.path.endswith("/feed"))
    assert request.url.params.get_list("contentRating[]") == [
        "safe",
        "suggestive",
        "erotica",
        "pornographic",
    ]
    assert request.url.params["translatedLanguage[]"] == "en"
    assert client.get(f"{url}/feed?page=400").status_code == 400
    assert client.delete(url).status_code == 204
    assert OTHER in upstream["lists"]


def test_lists_discovery_creation_sync_errors_and_validation(client: TestClient, upstream):
    assert client.get(f"/api/collections/mangadex/users/{USER}/lists").json()[0]["id"] == OTHER
    upstream["followed"] = True
    complete(client, client.post("/api/collections/mangadex/sync"))
    lists = client.get("/api/collections").json()
    assert len(lists) == 2
    public = next(item for item in lists if item["providerListId"] == OTHER)
    assert public["followed"] and not public["editable"]
    mine = next(item for item in lists if item["owned"])
    url = f"/api/collections/{mine['id']}"
    complete(client, client.post(f"{url}/sync"))
    upstream["fail"] = ("PUT", f"/list/{LIST}")
    assert client.patch(url, json={"name": "Lost edit"}).status_code == 409
    assert client.get(url).json()["name"] == "My MDList"
    upstream["fail"] = None
    created = client.post(
        "/api/collections",
        json={"name": "New MDList", "provider": "mangadex", "visibility": "private"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["owned"]
    assert client.put(f"{url}/follow", json={"followed": True}).status_code == 400
    for reference in (
        "https://evil.example/list/" + LIST,
        "not-a-uuid",
        "http://mangadex.org/list/" + LIST,
    ):
        assert (
            client.post(
                "/api/collections/mangadex/import", json={"reference": reference}
            ).status_code
            == 400
        )
    assert client.get("/api/collections/mangadex/users/no/lists").status_code == 400
    local = client.post("/api/collections", json={"name": "Local"}).json()["id"]
    assert client.post(f"/api/collections/{local}/sync").status_code == 400
    assert client.get(f"/api/collections/{local}/feed").status_code == 400
    assert client.post("/api/collections", json={"name": "  "}).status_code == 400


def test_public_import_without_connected_account_and_auth_required_for_writes(
    client: TestClient, db_session: Session, upstream
):
    config = db_session.get(Provider, "mangadex")
    assert config is not None
    config.client_id = None
    config.client_secret_enc = None
    config.refresh_token_enc = None
    db_session.commit()
    result = complete(
        client, client.post("/api/collections/mangadex/import", json={"reference": OTHER})
    )
    data = client.get(f"/api/collections/{result['collectionId']}").json()
    assert data["editable"] is False
    assert all("Authorization" not in request.headers for request in upstream["requests"])
    before = len(upstream["requests"])
    response = client.post("/api/collections", json={"name": "Private", "provider": "mangadex"})
    assert response.status_code == 400
    assert len(upstream["requests"]) == before
