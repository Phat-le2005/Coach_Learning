"""Add evaluation_details to question_attempts.

Revision ID: 0022_question_attempt_evaluation_details
Revises: 0021_rag_documents_and_chunks
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0022_question_attempt_evaluation_details"
down_revision: str | Sequence[str] | None = "0021_rag_documents_and_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Alembic creates ``alembic_version.version_num`` as VARCHAR(32) by
    # default. This revision ID (and later revision IDs) are longer than that,
    # so widen the bookkeeping column before Alembic records this revision.
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(length=32),
            type_=sa.String(length=128),
            existing_nullable=False,
        )
    op.add_column(
        "question_attempts",
        sa.Column("evaluation_details", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("question_attempts", "evaluation_details")
