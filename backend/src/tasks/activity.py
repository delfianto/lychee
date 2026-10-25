"""Count concrete unfinished work; coordinators are never chapter counts."""

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.downloads.models import DownloadTask
from src.integrations.sync import sync_jobs
from src.tasks.schema import ActivityOut
from src.tasks.tracker import tracker

_ACTIVE = {"queued", "running", "cancelling"}


def activity_snapshot(session: Session) -> ActivityOut:
    downloads = (
        session.scalar(
            select(func.count())
            .select_from(DownloadTask)
            .where(DownloadTask.status.in_(("queued", "downloading")))
        )
        or 0
    )
    by_owner: dict[str, list[str]] = defaultdict(list)
    syncs = 0
    for owner, status in sync_jobs.activity_snapshot():
        if owner:
            by_owner[owner].append(status)
        elif status in _ACTIVE:
            syncs += 1
    others = 0
    for task in tracker.snapshot():
        if task.status not in _ACTIVE or task.kind == "download":
            continue
        statuses = by_owner.get(task.id, [])
        if task.work_units is not None:
            paused = sync_jobs.paused or (
                "paused" in statuses and not any(status in _ACTIVE for status in statuses)
            )
            if task.status == "cancelling" or not paused:
                syncs += task.work_units
        elif statuses:
            syncs += sum(status in _ACTIVE for status in statuses)
        elif task.status == "queued" or task.progress == 0 or task.kind not in {"scan", "sync"}:
            others += 1  # discovery / metadata / imports with no concrete units yet
    return ActivityOut(
        download_chapters=downloads,
        sync_jobs=syncs,
        other_jobs=others,
        total=downloads + syncs + others,
    )
