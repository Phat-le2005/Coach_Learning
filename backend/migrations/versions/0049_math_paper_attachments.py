"""Private paper attachments for student math solutions.

Revision ID: 0049_math_paper_attachments
Revises: 0048_math_ink_retention_index
"""
from alembic import op
import sqlalchemy as sa

revision = "0049_math_paper_attachments"
down_revision = "0048_math_ink_retention_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "math_paper_attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("attempt_id", sa.Uuid(), sa.ForeignKey("math_solution_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(30), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(160), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("attempt_id", "sha256", name="uq_math_paper_attempt_sha"),
        sa.CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="math_paper_size"),
        sa.CheckConstraint("content_type IN ('image/png','image/jpeg','application/pdf')", name="math_paper_type"),
    )


def downgrade() -> None:
    op.drop_table("math_paper_attachments")
