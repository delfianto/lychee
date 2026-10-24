"""Persist download and sync concurrency preferences.

Revision ID: e2f61a9c4708
Revises: c9d28a461730
"""

from alembic import op
import sqlalchemy as sa

revision = "e2f61a9c4708"
down_revision = "c9d28a461730"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_queue_config",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("download_workers", sa.Integer(), nullable=False),
        sa.Column("sync_workers", sa.Integer(), nullable=False),
        sa.CheckConstraint("download_workers BETWEEN 1 AND 10", name="ck_task_download_workers"),
        sa.CheckConstraint("sync_workers BETWEEN 1 AND 10", name="ck_task_sync_workers"),
    )


def downgrade() -> None:
    op.drop_table("task_queue_config")
