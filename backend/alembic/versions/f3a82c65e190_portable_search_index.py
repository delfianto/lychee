"""Create the trigger-maintained search index for SQLite and local Turso.

Revision ID: f3a82c65e190
Revises: e2f61a9c4708
"""
from alembic import op
from src.catalog.search_index import create_search_index, drop_search_index

revision = "f3a82c65e190"
down_revision = "e2f61a9c4708"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_search_index(op.get_bind())


def downgrade() -> None:
    drop_search_index(op.get_bind())
