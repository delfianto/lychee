"""Every error response uses the {error:{code,message}} envelope."""

from fastapi.testclient import TestClient


def test_domain_not_found_shape(client: TestClient) -> None:
    body = client.get("/api/series/does-not-exist").json()
    assert body == {"error": {"code": "not_found", "message": "series 'does-not-exist' not found"}}


def test_unknown_route_shape(client: TestClient) -> None:
    resp = client.get("/api/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_validation_error_shape(client: TestClient) -> None:
    resp = client.patch("/api/import/config", json={"quality": 999})  # out of 1–100
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "validation_error"
    assert isinstance(error["message"], str) and error["message"]


def test_bad_request_shape(client: TestClient) -> None:
    resp = client.post("/api/import", json={"path": "/nope", "kind": "manga"})  # import disabled
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"
