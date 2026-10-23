"""Persist MDList metadata and language-aware chapter availability.

Revision ID: e3c19a7b4d20
Revises: bda512341597
"""
from alembic import op
import sqlalchemy as sa

revision = "e3c19a7b4d20"
down_revision = "bda512341597"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("collection", sa.Column("provider_owner_id", sa.String(64), nullable=True))
    op.add_column("collection", sa.Column("visibility", sa.String(16), nullable=True))
    op.add_column("collection", sa.Column("provider_version", sa.Integer(), nullable=True))
    op.add_column("collection", sa.Column("owned", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("collection", sa.Column("followed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("collection", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("series", sa.Column("chapter_index_language", sa.String(16), nullable=True))
    op.add_column("series", sa.Column("chapter_availability_json", sa.JSON(), nullable=True))
    # Defaults are needed for existing rows as well as the ORM's own insert defaults.


def downgrade() -> None:
    op.drop_column("series", "chapter_availability_json")
    op.drop_column("series", "chapter_index_language")
    for name in ("last_synced_at", "followed", "owned", "provider_version", "visibility", "provider_owner_id"):
        op.drop_column("collection", name)
