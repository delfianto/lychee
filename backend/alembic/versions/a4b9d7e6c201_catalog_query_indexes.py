"""Cover catalog ordering, publication, and read-state lookups.

Revision ID: a4b9d7e6c201
Revises: f3a82c65e190
"""

from alembic import op

revision = "a4b9d7e6c201"
down_revision = "f3a82c65e190"
branch_labels = None
depends_on = None

_INDEXES = (
    ("ix_series_kind_added", "series", ["kind", "created_at", "id"]),
    ("ix_series_kind_title", "series", ["kind", "sort_title", "id"]),
    ("ix_series_kind_rating", "series", ["kind", "rating", "id"]),
    (
        "ix_chapter_series_read",
        "chapter",
        ["series_id", "provider_chapter_id", "id", "number_sort"],
    ),
    ("ix_chapter_series_created", "chapter", ["series_id", "created_at"]),
    ("ix_chapter_series_uploaded", "chapter", ["series_id", "source_uploaded_at"]),
    (
        "ix_provider_chapter_published",
        "provider_chapter",
        ["series_id", "provider", "published_at"],
    ),
    ("ix_reading_progress_read", "reading_progress", ["chapter_id", "completed"]),
)


def upgrade() -> None:
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
