"""Select the lowest queued chapter even when a bulk insert has tied timestamps."""

from typing import Any

from sqlalchemy import Float, case, cast, func
from sqlalchemy.sql.elements import ColumnElement

from src.downloads.models import DownloadTask


def chapter_queue_order() -> tuple[ColumnElement[Any], ...]:
    number = func.coalesce(
        DownloadTask.remote_json["number"].as_string(),
        func.replace(DownloadTask.chapter_label, "Ch. ", ""),
    )
    numeric = number.op("REGEXP")(r"^[+-]?[0-9]+(?:\.[0-9]+)?$")
    return (
        case((numeric, 0), else_=1),
        case((numeric, cast(number, Float)), else_=None),
        func.lower(number),
        DownloadTask.created_at.asc(),
        DownloadTask.id.asc(),
    )
