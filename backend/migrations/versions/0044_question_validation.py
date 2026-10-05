"""Add reviewed acquisition question validation and draft promotion staging.

Revision ID: 0044_question_validation
Revises: 0043_question_acquisition
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0044_question_validation"
down_revision: str | Sequence[str] | None = "0043_question_acquisition"
branch_labels = None
depends_on = None

BATCH_STATUSES = ("OPEN", "IN_REVIEW", "READY_FOR_PROMOTION", "COMPLETED", "CANCELLED")
CANDIDATE_STATUSES = ("DRAFT", "IN_REVIEW", "VERIFIED", "REJECTED", "PROMOTED")
RIGHTS_DECISIONS = ("PENDING", "ALLOW_DRAFT", "BLOCKED")
QUESTION_TYPES = ("MULTIPLE_CHOICE", "TRUE_FALSE", "SHORT_ANSWER", "OPEN_RESPONSE")
COGNITIVE_LEVELS = ("REMEMBER", "UNDERSTAND", "APPLY", "ANALYZE")
CHECK_TYPES = (
    "STRUCTURE", "ANSWER_INTEGRITY", "TAXONOMY_INTEGRITY", "DUPLICATE",
    "VISUAL_INTEGRITY", "ACADEMIC_REVIEW", "ANSWER_REVIEW", "TAXONOMY_REVIEW",
    "RIGHTS_REVIEW",
)
CHECK_RESULTS = ("PASS", "FAIL", "NEEDS_REVIEW")


def upgrade() -> None:
    op.create_table(
        "question_validation_batches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("acquisition_request_id", sa.Uuid(), sa.ForeignKey("question_acquisition_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum(*BATCH_STATUSES, name="question_validation_batch_status", native_enum=False), nullable=False, server_default="OPEN"),
        sa.Column("target_candidate_count_snapshot", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("acquisition_request_id", "attempt_index", name="uq_question_validation_batches_request_attempt"),
        sa.CheckConstraint("attempt_index >= 1", name="ck_question_validation_batches_attempt"),
        sa.CheckConstraint("target_candidate_count_snapshot > 0", name="ck_question_validation_batches_target_positive"),
    )
    op.create_index("ix_question_validation_batches_request_status", "question_validation_batches", ["acquisition_request_id", "status"])
    op.create_index("ix_question_validation_batches_status_created", "question_validation_batches", ["status", "created_at"])

    op.create_table(
        "question_validation_candidates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("batch_id", sa.Uuid(), sa.ForeignKey("question_validation_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("question_acquisition_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.Enum(*CANDIDATE_STATUSES, name="question_validation_candidate_status", native_enum=False), nullable=False, server_default="DRAFT"),
        sa.Column("subject_id", sa.Uuid(), sa.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("question_type", sa.Enum(*QUESTION_TYPES, name="question_validation_question_type", native_enum=False), nullable=False),
        sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("correct_answer", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("cognitive_level", sa.Enum(*COGNITIVE_LEVELS, name="question_validation_cognitive_level", native_enum=False), nullable=True),
        sa.Column("exam_weight", sa.Float(), nullable=True),
        sa.Column("source_year", sa.Integer(), nullable=True),
        sa.Column("visual_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rights_decision", sa.Enum(*RIGHTS_DECISIONS, name="question_validation_rights_decision", native_enum=False), nullable=False, server_default="PENDING"),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("promoted_question_id", sa.Uuid(), sa.ForeignKey("questions.id", ondelete="RESTRICT"), nullable=True, unique=True),
        sa.Column("promoted_revision", sa.Integer(), nullable=True),
        sa.Column("promoted_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("revision >= 1", name="ck_question_validation_candidates_revision"),
        sa.CheckConstraint("length(trim(content)) > 0", name="ck_question_validation_candidates_content"),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_question_validation_candidates_hash"),
        sa.CheckConstraint("difficulty IS NULL OR difficulty BETWEEN 0.0 AND 1.0", name="ck_question_validation_candidates_difficulty"),
        sa.CheckConstraint("exam_weight IS NULL OR exam_weight BETWEEN 0.0 AND 1.0", name="ck_question_validation_candidates_exam_weight"),
        sa.CheckConstraint("source_year IS NULL OR source_year BETWEEN 1900 AND 2100", name="ck_question_validation_candidates_source_year"),
    )
    op.create_index("ix_question_validation_candidates_batch_status", "question_validation_candidates", ["batch_id", "status"])
    op.create_index("ix_question_validation_candidates_source_status", "question_validation_candidates", ["source_id", "status"])
    op.create_index("ix_question_validation_candidates_content_hash", "question_validation_candidates", ["content_hash"])
    op.create_index("ix_question_validation_candidates_promoted_question", "question_validation_candidates", ["promoted_question_id"])

    op.create_table(
        "question_validation_candidate_spans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("question_validation_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.Uuid(), sa.ForeignKey("question_acquisition_pages.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("excerpt_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("candidate_id", "order_index", name="uq_validation_spans_candidate_order"),
        sa.CheckConstraint("order_index >= 0", name="ck_validation_spans_order"),
        sa.CheckConstraint("start_char >= 0", name="ck_validation_spans_start"),
        sa.CheckConstraint("end_char > start_char", name="ck_validation_spans_range"),
        sa.CheckConstraint("length(trim(excerpt)) > 0", name="ck_validation_spans_excerpt"),
        sa.CheckConstraint("length(excerpt_sha256) = 64", name="ck_validation_spans_hash"),
    )
    op.create_index("ix_validation_spans_page", "question_validation_candidate_spans", ["page_id"])

    op.create_table(
        "question_validation_candidate_options",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("question_validation_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.UniqueConstraint("candidate_id", "label", name="uq_validation_options_candidate_label"),
        sa.UniqueConstraint("candidate_id", "order_index", name="uq_validation_options_candidate_order"),
        sa.CheckConstraint("length(trim(label)) > 0", name="ck_validation_options_label"),
        sa.CheckConstraint("length(trim(content)) > 0", name="ck_validation_options_content"),
        sa.CheckConstraint("order_index >= 0", name="ck_validation_options_order"),
    )
    op.create_table(
        "question_validation_candidate_concepts",
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("question_validation_candidates.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("concept_id", sa.Uuid(), sa.ForeignKey("concepts.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.CheckConstraint("weight > 0.0 AND weight <= 1.0", name="ck_validation_concepts_weight"),
    )
    op.create_table(
        "question_validation_candidate_problem_types",
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("question_validation_candidates.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("problem_type_id", sa.Uuid(), sa.ForeignKey("problem_types.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("weight IS NULL OR (weight > 0.0 AND weight <= 1.0)", name="ck_validation_problem_types_weight"),
    )
    op.create_table(
        "question_validation_candidate_learning_outcomes",
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("question_validation_candidates.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("learning_outcome_id", sa.Uuid(), sa.ForeignKey("learning_outcomes.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.CheckConstraint("weight IS NULL OR (weight > 0.0 AND weight <= 1.0)", name="ck_validation_learning_outcomes_weight"),
    )
    op.create_table(
        "question_validation_checks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("question_validation_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_revision", sa.Integer(), nullable=False),
        sa.Column("check_type", sa.Enum(*CHECK_TYPES, name="question_validation_check_type", native_enum=False), nullable=False),
        sa.Column("result", sa.Enum(*CHECK_RESULTS, name="question_validation_check_result", native_enum=False), nullable=False),
        sa.Column("checked_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("candidate_id", "candidate_revision", "check_type", name="uq_validation_checks_candidate_revision_type"),
        sa.CheckConstraint("candidate_revision >= 1", name="ck_validation_checks_revision"),
    )
    op.create_index("ix_validation_checks_candidate_revision", "question_validation_checks", ["candidate_id", "candidate_revision"])


def downgrade() -> None:
    op.drop_index("ix_validation_checks_candidate_revision", table_name="question_validation_checks")
    op.drop_table("question_validation_checks")
    op.drop_table("question_validation_candidate_learning_outcomes")
    op.drop_table("question_validation_candidate_problem_types")
    op.drop_table("question_validation_candidate_concepts")
    op.drop_table("question_validation_candidate_options")
    op.drop_index("ix_validation_spans_page", table_name="question_validation_candidate_spans")
    op.drop_table("question_validation_candidate_spans")
    op.drop_index("ix_question_validation_candidates_promoted_question", table_name="question_validation_candidates")
    op.drop_index("ix_question_validation_candidates_content_hash", table_name="question_validation_candidates")
    op.drop_index("ix_question_validation_candidates_source_status", table_name="question_validation_candidates")
    op.drop_index("ix_question_validation_candidates_batch_status", table_name="question_validation_candidates")
    op.drop_table("question_validation_candidates")
    op.drop_index("ix_question_validation_batches_status_created", table_name="question_validation_batches")
    op.drop_index("ix_question_validation_batches_request_status", table_name="question_validation_batches")
    op.drop_table("question_validation_batches")
