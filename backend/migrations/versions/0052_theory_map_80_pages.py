"""Allow up to 80 pages in teacher theory-map PDFs.

Revision ID: 0052_theory_map_80_pages
Revises: 0051_theory_map_page_limit
"""

from alembic import op
import sqlalchemy as sa

revision = "0052_theory_map_80_pages"
down_revision = "0051_theory_map_page_limit"
branch_labels = None
depends_on = None


def _replace_page_limit(max_pages: int) -> None:
    with op.batch_alter_table("theory_documents") as batch_op:
        batch_op.drop_constraint(op.f("ck_theory_documents_theory_page_count_range"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_theory_documents_theory_page_count_range"),
            f"page_count > 0 AND page_count <= {max_pages}",
        )


def upgrade() -> None:
    _replace_page_limit(80)


def downgrade() -> None:
    existing = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM theory_documents WHERE page_count > 50")
    ).scalar_one()
    if existing:
        raise RuntimeError("Cannot restore the 50-page limit while longer theory documents exist")
    _replace_page_limit(50)
