"""Class-scoped, teacher-reviewed PDF theory maps.

Revision ID: 0050_theory_maps
Revises: 0049_math_paper_attachments
"""
from alembic import op
import sqlalchemy as sa

revision = "0050_theory_maps"
down_revision = "0049_math_paper_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "theory_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("classroom_id", sa.Uuid(), sa.ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_id", sa.Uuid(), sa.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("page_texts", sa.JSON(), nullable=False),
        sa.Column("nodes", sa.JSON(), nullable=False),
        sa.Column("status", sa.Enum("DRAFT", "PUBLISHED", native_enum=False, name="theory_map_status"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("ai_model", sa.String(100)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("classroom_id", "sha256", name="uq_theory_classroom_sha"),
        sa.CheckConstraint("page_count > 0 AND page_count <= 30", name="theory_page_count_range"),
        sa.CheckConstraint("revision > 0", name="theory_revision_positive"),
    )
    op.create_index("ix_theory_documents_classroom_status", "theory_documents", ["classroom_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_theory_documents_classroom_status", table_name="theory_documents")
    op.drop_table("theory_documents")
