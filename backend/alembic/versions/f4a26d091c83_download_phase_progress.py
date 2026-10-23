"""Persist independent download, conversion and thumbnail counters.

Revision ID: f4a26d091c83
Revises: e3c19a7b4d20
"""
from alembic import op
import sqlalchemy as sa

revision = "f4a26d091c83"
down_revision = "e3c19a7b4d20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("download_task", sa.Column("phases_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("download_task", "phases_json")
