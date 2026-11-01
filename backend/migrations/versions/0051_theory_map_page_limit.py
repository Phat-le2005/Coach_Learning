"""Allow up to 50 pages in teacher theory-map PDFs.

Revision ID: 0051_theory_map_page_limit
Revises: 0050_theory_maps
"""

from alembic import op
import sqlalchemy as sa

revision = "0051_theory_map_page_limit"
down_revision = "0050_theory_maps"
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
    _replace_page_limit(50)


def downgrade() -> None:
    existing = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM theory_documents WHERE page_count > 30")
    ).scalar_one()
    if existing:
        raise RuntimeError("Cannot restore the 30-page limit while longer theory documents exist")
    _replace_page_limit(30)
