"""Per-page compressed Math Ink storage.

Revision ID: 0047_math_ink_pages
Revises: 0046_math_solutions
"""
from alembic import op
import sqlalchemy as sa
revision = "0047_math_ink_pages"
down_revision = "0046_math_solutions"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("math_ink_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("attempt_id", sa.Uuid(), sa.ForeignKey("math_solution_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.UniqueConstraint("attempt_id", name="uq_math_ink_attempt"))
    op.create_table("math_ink_pages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("math_ink_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_index", sa.Integer(), nullable=False),
        sa.Column("compressed_strokes", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("stroke_count", sa.Integer(), nullable=False),
        sa.Column("point_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("page_index >= 0 AND page_index < 30", name="page_index_limit"),
        sa.CheckConstraint("stroke_count >= 0 AND point_count >= 0", name="counts_nonnegative"),
        sa.UniqueConstraint("document_id", "page_index", name="uq_math_ink_page_index"))
    op.create_table("math_ink_operations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("math_ink_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("client_action_id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("page_index", sa.Integer(), nullable=False),
        sa.Column("result_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "client_action_id", name="uq_math_ink_action"))

def downgrade() -> None:
    op.drop_table("math_ink_operations")
    op.drop_table("math_ink_pages")
    op.drop_table("math_ink_documents")
