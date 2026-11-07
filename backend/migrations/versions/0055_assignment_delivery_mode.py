"""Add delivery_mode column to assignments table.

Revision ID: 0055_assignment_delivery_mode
Revises: 0054_merge_canvas_theory
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0055_assignment_delivery_mode"
down_revision: str | Sequence[str] | None = "0054_merge_canvas_theory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assignments",
        sa.Column(
            "delivery_mode",
            sa.Enum(
                "PRACTICE",
                "EXAM",
                name="assignment_delivery_mode",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="PRACTICE",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("assignments", "delivery_mode")
