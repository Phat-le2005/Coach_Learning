"""Add teacher analytics composite indexes for evidence and root cause diagnosis.

Revision ID: 0045_teacher_analytics_indexes
Revises: 0044_question_validation
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0045_teacher_analytics_indexes"
down_revision: str | Sequence[str] | None = "0044_question_validation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_learning_evidence_classroom_occurred",
        "learning_evidence_events",
        ["classroom_id", "occurred_at"],
    )
    op.create_index(
        "ix_learning_evidence_classroom_subject_occurred",
        "learning_evidence_events",
        ["classroom_id", "subject_id", "occurred_at"],
    )
    op.create_index(
        "ix_root_cause_classroom_created",
        "root_cause_diagnoses",
        ["classroom_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_root_cause_classroom_created",
        table_name="root_cause_diagnoses",
    )
    op.drop_index(
        "ix_learning_evidence_classroom_subject_occurred",
        table_name="learning_evidence_events",
    )
    op.drop_index(
        "ix_learning_evidence_classroom_occurred",
        table_name="learning_evidence_events",
    )
