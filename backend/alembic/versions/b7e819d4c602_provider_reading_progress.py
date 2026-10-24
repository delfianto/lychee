"""Persist provider-only chapter progress independently of downloaded files.

Revision ID: b7e819d4c602
Revises: a5c731d9e204
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from nanoid import generate

revision = "b7e819d4c602"
down_revision = "a5c731d9e204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = op.create_table(
        "provider_reading_progress",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "series_id",
            sa.String(12),
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_chapter_id", sa.String(64), nullable=False),
        sa.Column("current_page", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("series_id", "provider", "provider_chapter_id"),
    )
    op.create_index(
        "ix_provider_reading_progress_series_id", "provider_reading_progress", ["series_id"]
    )
    # Preserve existing provider-linked reads when their local download is removed.
    rows = (
        op.get_bind()
        .execute(
            sa.text("""
        SELECT rp.series_id, COALESCE(c.provider,s.provider) AS provider, c.provider_chapter_id,
               MAX(rp.current_page) AS current_page, MAX(rp.completed) AS completed,
               MIN(rp.created_at) AS created_at, MAX(rp.updated_at) AS updated_at
        FROM reading_progress rp JOIN chapter c ON c.id=rp.chapter_id JOIN series s ON s.id=rp.series_id
        WHERE c.provider_chapter_id IS NOT NULL AND COALESCE(c.provider,s.provider) IS NOT NULL
        GROUP BY rp.series_id, COALESCE(c.provider,s.provider), c.provider_chapter_id
    """)
        )
        .mappings()
    )
    for row in rows:
        op.bulk_insert(
            table,
            [
                {
                    **row,
                    "id": generate(size=12),
                    "completed": bool(row["completed"]),
                    "created_at": datetime.fromisoformat(row["created_at"]),
                    "updated_at": datetime.fromisoformat(row["updated_at"]),
                }
            ],
        )


def downgrade() -> None:
    op.drop_index("ix_provider_reading_progress_series_id", table_name="provider_reading_progress")
    op.drop_table("provider_reading_progress")
