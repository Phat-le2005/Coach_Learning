"""Allow a teacher to share the original PDF independently of its reviewed map.

Revision ID: 0053_theory_source_library
Revises: 0052_theory_map_80_pages
"""
from alembic import op
import sqlalchemy as sa

revision = "0053_theory_source_library"
down_revision = "0052_theory_map_80_pages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("theory_documents", sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("theory_documents", "source_published_at")
