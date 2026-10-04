"""Separate question pipeline inventory from runtime eligibility.

Revision ID: 0042_question_supply_pipeline_semantics
Revises: 0041_question_supply_hardening
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0042_question_supply_pipeline_semantics"
down_revision: str | Sequence[str] | None = "0041_question_supply_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("question_supply_gaps") as batch_op:
        batch_op.add_column(
            sa.Column(
                "pipeline_runtime_eligible_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.create_check_constraint(
            "ck_supply_gaps_pipeline_runtime_eligible",
            "pipeline_runtime_eligible_count >= 0 AND pipeline_runtime_eligible_count <= pipeline_candidate_count",
        )


def downgrade() -> None:
    with op.batch_alter_table("question_supply_gaps") as batch_op:
        batch_op.drop_constraint(
            "ck_question_supply_gaps_ck_supply_gaps_pipeline_runtime_eligible",
            type_="check",
        )
        batch_op.drop_column("pipeline_runtime_eligible_count")
