"""Reversible student attempt history visibility.

Revision ID: 0056_student_attempt_history_visibility
Revises: 0055_assignment_delivery_mode
"""
from alembic import op
import sqlalchemy as sa

revision = "0056_student_attempt_history_visibility"
down_revision = "0055_assignment_delivery_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "math_solution_attempts",
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("math_solution_attempts", "hidden_at")
