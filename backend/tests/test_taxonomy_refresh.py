"""Taxonomy refresh from the metadata provider's canonical tag list."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.downloads.provider import register_provider
from src.tasks.queue import queue
from src.taxonomy.models import Tag


class _TagProvider:
    """A metadata provider that returns a canned tag list (one already seeded, one new)."""

    id = "mangadex"

    def list_tags(self, *, language: str = "en") -> list[tuple[str, str]]:
        return [("Action", "genre"), ("Cybernetic Ninjas", "theme")]

    def get_metadata(self, *_args: object, **_kwargs: object) -> object:  # for get_metadata_provider
        raise NotImplementedError


def test_refresh_adds_only_missing_tags(client: TestClient, db_session: Session) -> None:
    register_provider(_TagProvider())
    assert db_session.get(Tag, "cybernetic-ninjas") is None  # not seeded

    resp = client.post("/api/taxonomy/refresh")
    assert resp.status_code == 202
    queue.wait_idle()

    tasks = {t["id"]: t for t in client.get("/api/tasks").json()}
    assert tasks[resp.json()["id"]]["result"] == {"added": 1}  # "Action" already existed

    db_session.expire_all()
    tag = db_session.get(Tag, "cybernetic-ninjas")
    assert tag is not None
    assert (tag.name, tag.group) == ("Cybernetic Ninjas", "theme")


def test_refresh_is_idempotent(client: TestClient) -> None:
    register_provider(_TagProvider())
    client.post("/api/taxonomy/refresh")
    queue.wait_idle()
    again = client.post("/api/taxonomy/refresh")
    queue.wait_idle()
    tasks = {t["id"]: t for t in client.get("/api/tasks").json()}
    assert tasks[again.json()["id"]]["result"] == {"added": 0}
