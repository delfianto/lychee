"""MangaDex custom-list operations over the shared rate-limited API client."""

from dataclasses import replace
from threading import RLock
from typing import Any

from src.downloads.provider import CustomList
from src.providers.mangadex_client import MangaDexClient

# Snapshot reconciliation and user writes must not race within the single app process.
LIST_LOCK = RLock()


def parse_list(data: dict[str, Any]) -> CustomList:
    attrs = data["attributes"]
    relationships = data.get("relationships", [])
    return CustomList(
        provider_list_id=data["id"],
        name=attrs["name"],
        manga_ids=[r["id"] for r in relationships if r["type"] == "manga"],
        owner_id=next((r["id"] for r in relationships if r["type"] == "user"), None),
        visibility=attrs.get("visibility", "public"),
        version=attrs.get("version", 1),
    )


class MangaDexLists:
    def __init__(self, api: MangaDexClient) -> None:
        self.api = api

    def user_id(self) -> str:
        return self.api.get("/user/me").json()["data"]["id"]

    def get(self, list_id: str) -> CustomList:
        return parse_list(self.api.get(f"/list/{list_id}").json()["data"])

    def listing(
        self, path: str, *, owned: bool = False, followed: bool = False
    ) -> list[CustomList]:
        results: list[CustomList] = []
        offset = 0
        while True:
            body = self.api.get(path, params={"limit": 100, "offset": offset}).json()
            results.extend(
                replace(parse_list(item), owned=owned, followed=followed) for item in body["data"]
            )
            offset += 100
            if offset >= int(body["total"]):
                return results

    def create(self, name: str, visibility: str) -> CustomList:
        return replace(
            parse_list(
                self.api.post(
                    "/list", json={"name": name, "visibility": visibility}, retry=False
                ).json()["data"]
            ),
            owned=True,
        )

    def update(
        self, custom: CustomList, *, name: str | None = None, visibility: str | None = None
    ) -> CustomList:
        body: dict[str, object] = {"version": custom.version}
        if name is not None:
            body["name"] = name
        if visibility is not None:
            body["visibility"] = visibility
        return parse_list(
            self.api.put(f"/list/{custom.provider_list_id}", json=body).json()["data"]
        )

    def delete(self, list_id: str) -> None:
        self.api.delete(f"/list/{list_id}")

    def membership(self, list_id: str, manga_id: str, *, add: bool) -> None:
        path = f"/manga/{manga_id}/list/{list_id}"
        if add:
            self.api.post(path)
        else:
            self.api.delete(path)

    def follow(self, list_id: str, *, followed: bool) -> None:
        if followed:
            self.api.post(f"/list/{list_id}/follow")
        else:
            self.api.delete(f"/list/{list_id}/follow")

    def feed(self, list_id: str, *, language: str, offset: int, limit: int) -> dict[str, Any]:
        return self.api.get(
            f"/list/{list_id}/feed",
            params={
                "translatedLanguage[]": language,
                "contentRating[]": ["safe", "suggestive", "erotica", "pornographic"],
                "order[publishAt]": "desc",
                "includes[]": ["manga", "scanlation_group"],
                "includeFutureUpdates": "0",
                "includeFuturePublishAt": 0,
                "includeEmptyPages": 0,
                "includeUnavailable": "0",
                "limit": limit,
                "offset": offset,
            },
        ).json()
