"""Shared slug normalization for taxonomy identity (Tag/TagAlias ids)."""

from __future__ import annotations

import re


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "tag"
