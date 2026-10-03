"""Harden root cause verification integrity and concurrency.

Revision ID: 0036_root_cause_verification_hardening
Revises: 0035_root_cause_verification
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0036_root_cause_verification_hardening"
down_revision: str | Sequence[str] | None = "0035_root_cause_verification"
branch_labels = None
depends_on = None


def _require_no_historical_duplicates() -> None:
    bind = op.get_bind()
    duplicate_diagnoses = bind.execute(
        sa.text(
            """
            SELECT diagnosis_id
            FROM root_cause_verifications
            GROUP BY diagnosis_id
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if duplicate_diagnoses:
        raise RuntimeError(
            "Cannot add uq_root_cause_verification_diagnosis: "
            "historical duplicate diagnosis_id values must be resolved first."
        )

    duplicate_target_questions = bind.execute(
        sa.text(
            """
            SELECT verification_target_id, question_id
            FROM root_cause_verification_items
            GROUP BY verification_target_id, question_id
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if duplicate_target_questions:
        raise RuntimeError(
            "Cannot add uq_root_cause_verification_target_question: "
            "historical duplicate target/question pairs must be resolved first."
        )


def upgrade() -> None:
    _require_no_historical_duplicates()

    with op.batch_alter_table("root_cause_verifications") as batch_op:
        batch_op.create_unique_constraint(
            "uq_root_cause_verification_diagnosis",
            ["diagnosis_id"],
        )
        batch_op.create_check_constraint(
            "completed_probes_not_exceed_required",
            "completed_probe_count <= required_probe_count",
        )

    with op.batch_alter_table("root_cause_verification_targets") as batch_op:
        batch_op.create_check_constraint(
            "correct_count_not_exceed_probe_count",
            "correct_count <= probe_count",
        )

    with op.batch_alter_table("root_cause_verification_items") as batch_op:
        batch_op.create_unique_constraint(
            "uq_root_cause_verification_target_question",
            ["verification_target_id", "question_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("root_cause_verification_items") as batch_op:
        batch_op.drop_constraint(
            "uq_root_cause_verification_target_question",
            type_="unique",
        )

    with op.batch_alter_table("root_cause_verification_targets") as batch_op:
        batch_op.drop_constraint(
            "ck_root_cause_verification_targets_correct_count_not_exceed_probe_count",
            type_="check",
        )

    with op.batch_alter_table("root_cause_verifications") as batch_op:
        batch_op.drop_constraint(
            "ck_root_cause_verifications_completed_probes_not_exceed_required",
            type_="check",
        )
        batch_op.drop_constraint(
            "uq_root_cause_verification_diagnosis",
            type_="unique",
        )
