"""series_fts full-text search index

Creates the FTS5 trigram virtual table over series title / alt-titles / authors
plus the triggers that keep it in sync, and backfills existing series. DDL is
shared with the app/test harness — see src/catalog/search_index.py.

Revision ID: b6cabeb7578d
Revises: 7cb0d1378b76
Create Date: 2026-07-25 13:09:09.481461

"""
from alembic import op

from src.catalog.search_index import SEARCH_INDEX_DROP_STATEMENTS, SEARCH_INDEX_STATEMENTS

# revision identifiers, used by Alembic.
revision = 'b6cabeb7578d'
down_revision = '7cb0d1378b76'
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in SEARCH_INDEX_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in SEARCH_INDEX_DROP_STATEMENTS:
        op.execute(statement)
