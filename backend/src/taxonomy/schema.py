"""Taxonomy API schemas (Settings → Content table)."""

from __future__ import annotations

from src.core.schema import CamelModel


class AliasOut(CamelModel):
    id: str
    name: str
    tag_id: str


class TaxonomyItemOut(CamelModel):
    id: str
    name: str
    category: str  # the Tag.group
    uses: int
    enabled: bool
    system: bool
    aliases: list[AliasOut] = []


class TaxonomyCreate(CamelModel):
    name: str
    category: str


class TaxonomyUpdate(CamelModel):
    name: str | None = None
    enabled: bool | None = None


class AliasCreate(CamelModel):
    name: str
