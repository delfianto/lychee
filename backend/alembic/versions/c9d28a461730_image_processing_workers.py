"""Persist independent conversion and thumbnail worker limits.

Revision ID: c9d28a461730
Revises: b7e819d4c602
"""

from alembic import op
import sqlalchemy as sa

revision = "c9d28a461730"
down_revision = "b7e819d4c602"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "image_processing_config",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("conversion_workers", sa.Integer(), nullable=False),
        sa.Column("thumbnail_workers", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "conversion_workers BETWEEN 1 AND 64", name="ck_image_conversion_workers"
        ),
        sa.CheckConstraint("thumbnail_workers BETWEEN 1 AND 64", name="ck_image_thumbnail_workers"),
    )


def downgrade() -> None:
    op.drop_table("image_processing_config")
