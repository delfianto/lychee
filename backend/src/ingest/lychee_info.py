"""``lychee.info`` — the native YAML metadata sidecar format (schema v1).

Design doc: ``notes/08-metadata.md``. Written by an LLM agent (``mcp/``), read on
scan. This module owns the strict schema (the same Pydantic tool used everywhere
else in the backend — it doubles as a JSON-Schema source for whatever writes
these files) and pure YAML parsing/validation. Applying a parsed file onto a
``Series`` is ``catalog.service.apply_lychee_info``; finding the file on disk and
gating re-application on a content hash is ``ingest.scanner``.

Every field is optional except ``schema``/``kind`` — a partial patch, not a full
record. ``extra="forbid"`` everywhere: a hallucinated field name or wrong enum
value must fail validation loudly rather than silently doing something wrong.
"""

from __future__ import annotations

from typing import Literal

import yaml
from pydantic import ConfigDict, Field, ValidationError, field_validator
from pydantic.alias_generators import to_camel

from src.core.schema import CamelModel

LYCHEE_INFO_FILENAME = "lychee.info"
_SUPPORTED_SCHEMA_VERSION = 1

_strict_config = ConfigDict(
    alias_generator=to_camel,
    populate_by_name=True,
    from_attributes=True,
    extra="forbid",
)


class _Strict(CamelModel):
    """Base for every lychee.info (sub)model: camelCase wire fields, no unknown keys."""

    model_config = _strict_config


class SidecarTitle(_Strict):
    """One entry of the ``titles:`` list — mirrors ``TitleVariant`` (ADR 18)."""

    lang: str
    type: Literal["native", "romanized", "english", "alt"]
    title: str


class SidecarCredit(_Strict):
    """One entry of the ``credits:`` list — mirrors ``SeriesCredit``."""

    name: str
    role: Literal["author", "artist"]


class SidecarCrossover(_Strict):
    """One entry of the ``crossovers:`` list — the franchise/parody a work depicts."""

    series: str | None = None
    characters: list[str] = Field(default_factory=list)


class SidecarGenerated(_Strict):
    """Provenance of the last write — describes the last write only, not a history."""

    by: str | None = None
    model: str | None = None
    at: str | None = None  # informational; not parsed into a datetime
    version: int | None = None


class SidecarTags(_Strict):
    """The four user-assignable taxonomy groups (ADR 10) — content_rating/demographic
    are their own top-level scalar fields, not tag groups, so they aren't here."""

    genre: list[str] = Field(default_factory=list)
    theme: list[str] = Field(default_factory=list)
    format: list[str] = Field(default_factory=list)
    content: list[str] = Field(default_factory=list)


class LycheeInfoFile(_Strict):
    """Schema v1 of ``lychee.info`` — see ``notes/08-metadata.md`` for the full spec."""

    schema_version: int = Field(alias="schema")
    kind: Literal["manga", "comic", "gallery"]

    title: str | None = None
    titles: list[SidecarTitle] | None = None
    description: str | None = None

    status: Literal["ongoing", "completed", "hiatus", "cancelled"] | None = None
    year: int | None = None
    origin_country: str | None = Field(default=None, pattern=r"^[a-z]{2}$")

    content_rating: Literal["safe", "suggestive", "erotica", "mature"] | None = None
    demographic: Literal["shonen", "shojo", "seinen", "josei", "none"] | None = None

    tags: SidecarTags | None = None
    credits: list[SidecarCredit] | None = None
    crossovers: list[SidecarCrossover] | None = None

    # site -> id, e.g. {"mangadex": "..."}; seeds a match (catalog.matching.set_match).
    provider: dict[str, str] | None = None
    # tracker -> id, e.g. {"anilist": "...", "myanimelist": "..."} -> external_ids_json.
    external: dict[str, str] | None = None
    generated: SidecarGenerated | None = None

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, value: int) -> int:
        if value != _SUPPORTED_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema version {value!r} (only {_SUPPORTED_SCHEMA_VERSION} is known)"
            )
        return value


class LycheeInfoParseError(Exception):
    """Raised for anything wrong with a ``lychee.info`` file: bad YAML, not a mapping,
    or a schema validation failure (unknown field, bad enum, wrong version, …)."""


def parse_lychee_info(raw: bytes) -> LycheeInfoFile:
    """Parse + strictly validate raw YAML bytes into a ``LycheeInfoFile``.

    Raises ``LycheeInfoParseError`` with a human-readable reason on any failure —
    callers (the scanner) log it and skip applying that file for the scan pass,
    without failing the scan itself.
    """
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise LycheeInfoParseError(f"invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise LycheeInfoParseError("top-level YAML content must be a mapping")
    try:
        return LycheeInfoFile.model_validate(data)
    except ValidationError as exc:
        raise LycheeInfoParseError(str(exc)) from exc
