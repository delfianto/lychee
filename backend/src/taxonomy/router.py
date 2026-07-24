"""Taxonomy API (Settings → Content)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from src.core.persistence.database import DbSession
from src.core.schema import OffsetPage
from src.taxonomy import service
from src.taxonomy.schema import TaxonomyCreate, TaxonomyItemOut, TaxonomyUpdate

router = APIRouter(prefix="/api", tags=["taxonomy"])


@router.get("/taxonomy")
def list_taxonomy(
    db: DbSession,
    type: str | None = None,
    q: str | None = None,
    page: int = 0,
    page_size: int = Query(20, alias="pageSize"),
) -> OffsetPage[TaxonomyItemOut]:
    return service.list_taxonomy(db, type_=type, q=q, page=page, page_size=page_size)


@router.post("/taxonomy", status_code=status.HTTP_201_CREATED)
def create_taxonomy(db: DbSession, data: TaxonomyCreate) -> TaxonomyItemOut:
    return service.create_taxonomy(db, data)


@router.patch("/taxonomy/{tag_id}")
def update_taxonomy(db: DbSession, tag_id: str, data: TaxonomyUpdate) -> TaxonomyItemOut:
    return service.update_taxonomy(db, tag_id, data)


@router.delete("/taxonomy/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_taxonomy(db: DbSession, tag_id: str) -> Response:
    service.delete_taxonomy(db, tag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
