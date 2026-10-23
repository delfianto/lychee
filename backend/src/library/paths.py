"""Distinguish provider homes from canonical filesystem library roots."""

import re


def is_provider_path(path: str) -> bool:
    return re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", path.strip()) is not None
