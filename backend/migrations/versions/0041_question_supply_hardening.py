"""Harden question bank supply gap invariants and persist reason code.

Revision ID: 0041_question_supply_hardening
Revises: 0040_question_supply_gap
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0041_question_supply_hardening"
down_revision: str | Sequence[str] | None = "0040_question_supply_gap"
branch_labels = None
depends_on = None

QUESTION_SUPPLY_REASON_CODES = (
    "NO_APPROVED_TARGET_QUESTIONS",
    "INSUFFICIENT_APPROVED_TARGET_COUNT",
    "INSUFFICIENT_DIFFICULTY_COVERAGE",
    "NO_AUTO_EVALUABLE_TARGET_QUESTIONS",
    "STUDENT_EXPOSURE_EXHAUSTED",
    "THIN_APPROVED_TARGET_COUNT",
    "THIN_DIFFICULTY_COVERAGE",
)

ORIGINAL_REASON_CODES = (
    "NO_APPROVED_TARGET_QUESTIONS",
    "INSUFFICIENT_APPROVED_TARGET_COUNT",
    "INSUFFICIENT_DIFFICULTY_COVERAGE",
    "NO_AUTO_EVALUABLE_TARGET_QUESTIONS",
    "STUDENT_EXPOSURE_EXHAUSTED",
)


def upgrade() -> None:
    # 1. Update observation reason_code enum constraint to include THIN codes
    with op.batch_alter_table("question_supply_gap_observations") as batch_op:
        batch_op.alter_column(
            "reason_code",
            type_=sa.Enum(
                *QUESTION_SUPPLY_REASON_CODES,
                name="question_supply_obs_reason_code",
                native_enum=False,
            ),
            existing_type=sa.Enum(
                *ORIGINAL_REASON_CODES,
                name="question_supply_obs_reason_code",
                native_enum=False,
            ),
            existing_nullable=False,
        )

    # 2. Add reason_code to question_supply_gaps
    with op.batch_alter_table("question_supply_gaps") as batch_op:
        batch_op.add_column(
            sa.Column(
                "reason_code",
                sa.Enum(
                    *QUESTION_SUPPLY_REASON_CODES,
                    name="question_supply_gap_reason_code",
                    native_enum=False,
                ),
                nullable=True,
            )
        )

    # 3. Backfill existing rows
    op.execute(
        sa.text(
            """
            UPDATE question_supply_gaps
            SET reason_code = CASE
                WHEN approved_eligible_count = 0 THEN 'NO_APPROVED_TARGET_QUESTIONS'
                WHEN approved_eligible_count < minimum_required_count THEN 'INSUFFICIENT_APPROVED_TARGET_COUNT'
                WHEN approved_in_band_count < minimum_required_count THEN 'INSUFFICIENT_DIFFICULTY_COVERAGE'
                ELSE 'THIN_APPROVED_TARGET_COUNT'
            END
            WHERE reason_code IS NULL
            """
        )
    )

    with op.batch_alter_table("question_supply_gaps") as batch_op:
        batch_op.alter_column(
            "reason_code",
            nullable=False,
            existing_type=sa.Enum(
                *QUESTION_SUPPLY_REASON_CODES,
                name="question_supply_gap_reason_code",
                native_enum=False,
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("question_supply_gaps") as batch_op:
        batch_op.drop_column("reason_code")

    with op.batch_alter_table("question_supply_gap_observations") as batch_op:
        batch_op.alter_column(
            "reason_code",
            type_=sa.Enum(
                *ORIGINAL_REASON_CODES,
                name="question_supply_obs_reason_code",
                native_enum=False,
            ),
            existing_type=sa.Enum(
                *QUESTION_SUPPLY_REASON_CODES,
                name="question_supply_obs_reason_code",
                native_enum=False,
            ),
            existing_nullable=False,
        )
