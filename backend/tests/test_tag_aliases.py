"""Tag aliases (notes/09-tag-aliases.md): synonym resolution + the taxonomy alias API."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.catalog.metadata import apply_metadata, reconcile_tags, resolve_tag_id
from src.downloads.provider import SeriesMetadata
from src.taxonomy.models import Tag

from tests.support import make_series


def test_reconcile_tags_resolves_alias_instead_of_duplicating(db_session: Session) -> None:
    tags = reconcile_tags(db_session, [("Yaoi", "genre")])
    assert [t.id for t in tags] == ["boys-love"]
    db_session.flush()
    assert db_session.get(Tag, "yaoi") is None  # no duplicate tag minted


def test_reconcile_tags_still_creates_new_tag_for_unknown_name(db_session: Session) -> None:
    tags = reconcile_tags(db_session, [("Cooking Battle", "theme")])
    assert len(tags) == 1
    assert tags[0].id == "cooking-battle"
    assert tags[0].name == "Cooking Battle"


def test_resolve_tag_id_via_slug_and_alias(db_session: Session) -> None:
    assert resolve_tag_id(db_session, "mature", "content_rating") == "mature"
    assert resolve_tag_id(db_session, "Pornographic", "content_rating") == "mature"
    assert resolve_tag_id(db_session, "Hentai", "content_rating") == "mature"
    assert resolve_tag_id(db_session, "Ecchi", "content_rating") == "suggestive"


def test_resolve_tag_id_unknown_value_returns_none(db_session: Session) -> None:
    assert resolve_tag_id(db_session, "made-up-rating", "content_rating") is None


def test_resolve_tag_id_rejects_wrong_group(db_session: Session) -> None:
    # "safe" is a content_rating tag, not a demographic — must not cross groups.
    assert resolve_tag_id(db_session, "safe", "demographic") is None


def test_apply_metadata_resolves_mangadex_pornographic_to_mature(db_session: Session) -> None:
    series = make_series(db_session, title="Doujin A", content_rating="safe")
    meta = SeriesMetadata(provider_series_id="p1", title="Doujin A", content_rating="pornographic")
    apply_metadata(db_session, series, meta, fetch_covers=False)
    assert series.content_rating == "mature"


def test_apply_metadata_warns_and_skips_unresolvable_rating(db_session: Session) -> None:
    series = make_series(db_session, title="Doujin B", content_rating="safe")
    meta = SeriesMetadata(provider_series_id="p2", title="Doujin B", content_rating="nonsense")
    apply_metadata(db_session, series, meta, fetch_covers=False)
    assert series.content_rating == "safe"  # left untouched, not overwritten with garbage


def test_alias_crud_endpoints(client: TestClient) -> None:
    # "action" has no seeded aliases (unlike boys-love/girls-love/mature), so it's a
    # clean slate for asserting the exact aliases list.
    created = client.post("/api/taxonomy/action/aliases", json={"name": "Battle Shonen"})
    assert created.status_code == 201
    body = created.json()
    assert (body["id"], body["name"], body["tagId"]) == ("battle-shonen", "Battle Shonen", "action")

    item = next(
        i
        for i in client.get("/api/taxonomy", params={"type": "genre"}).json()["items"]
        if i["id"] == "action"
    )
    assert item["aliases"] == [{"id": "battle-shonen", "name": "Battle Shonen", "tagId": "action"}]

    assert client.delete(f"/api/taxonomy/action/aliases/{body['id']}").status_code == 204
    item = next(
        i
        for i in client.get("/api/taxonomy", params={"type": "genre"}).json()["items"]
        if i["id"] == "action"
    )
    assert item["aliases"] == []


def test_alias_rejects_collision_with_existing_tag(client: TestClient) -> None:
    # "action" is already a real, distinct tag — can't also become an alias.
    resp = client.post("/api/taxonomy/boys-love/aliases", json={"name": "Action"})
    assert resp.status_code == 409


def test_alias_rejects_pointing_at_two_tags(client: TestClient) -> None:
    resp = client.post("/api/taxonomy/girls-love/aliases", json={"name": "Yaoi"})
    assert resp.status_code == 409  # "Yaoi" is already seeded as an alias of boys-love


def test_alias_create_is_idempotent_for_same_tag(client: TestClient) -> None:
    first = client.post("/api/taxonomy/action/aliases", json={"name": "Battle Shonen"})
    second = client.post("/api/taxonomy/action/aliases", json={"name": "Battle Shonen"})
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_system_tag_name_is_renamable_but_id_and_deletability_stay_locked(
    client: TestClient,
) -> None:
    renamed = client.patch("/api/taxonomy/mature", json={"name": "Hentai"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Hentai"
    assert renamed.json()["id"] == "mature"  # sync key unchanged

    assert client.delete("/api/taxonomy/mature").status_code == 400  # still not deletable
