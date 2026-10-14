"""Index the operation journal for bounded age-based retention.

Revision ID: 0048_math_ink_retention_index
Revises: 0047_math_ink_pages
"""
from alembic import op

revision = "0048_math_ink_retention_index"
down_revision = "0047_math_ink_pages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_math_ink_operations_created_at_id",
        "math_ink_operations",
        ["created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_math_ink_operations_created_at_id",
        table_name="math_ink_operations",
    )
