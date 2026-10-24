"""Persist list type independently of membership.

Revision ID: a5c731d9e204
Revises: f4a26d091c83
"""
from alembic import op
import sqlalchemy as sa

revision = "a5c731d9e204"
down_revision = "f4a26d091c83"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("collection", sa.Column("kind", sa.String(16), nullable=False, server_default="manga"))
    # Preserve existing membership. Legacy mixed lists remain visible and can be
    # repaired by removal; new lists and all new memberships enforce one kind.
    op.execute("""
        UPDATE collection SET kind = CASE
          WHEN provider = 'mangadex' THEN 'manga'
          WHEN (SELECT COUNT(DISTINCT s.kind) FROM collection_series cs
                JOIN series s ON s.id = cs.series_id WHERE cs.collection_id = collection.id) > 1 THEN 'mixed'
          ELSE COALESCE((SELECT MIN(s.kind) FROM collection_series cs
                JOIN series s ON s.id = cs.series_id WHERE cs.collection_id = collection.id), 'manga') END
    """)


def downgrade() -> None:
    op.drop_column("collection", "kind")
