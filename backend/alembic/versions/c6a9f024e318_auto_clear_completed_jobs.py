"""Persist independent download and sync auto-clear preferences.

Revision ID: c6a9f024e318
Revises: a4b9d7e6c201
"""

from alembic import op
import sqlalchemy as sa

revision = "c6a9f024e318"
down_revision = "a4b9d7e6c201"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("task_queue_config", sa.Column("download_auto_clear_completed", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("task_queue_config", sa.Column("sync_auto_clear_completed", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("task_queue_config") as batch:
        batch.drop_column("sync_auto_clear_completed")
        batch.drop_column("download_auto_clear_completed")
