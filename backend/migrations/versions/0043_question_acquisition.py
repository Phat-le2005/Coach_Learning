"""Add question acquisition planning, sources, and staging artifacts.

Revision ID: 0043_question_acquisition
Revises: 0042_question_supply_pipeline_semantics
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0043_question_acquisition"
down_revision: str | Sequence[str] | None = "0042_question_supply_pipeline_semantics"
branch_labels = None
depends_on = None

ACQUISITION_STRATEGIES = (
    "REVIEW_EXISTING_PIPELINE",
    "MIXED",
    "EXTERNAL_SOURCE_REQUIRED",
)

ACQUISITION_REQUEST_STATUSES = (
    "PLANNED",
    "AWAITING_SOURCE",
    "ACQUIRING",
    "STAGED",
    "READY_FOR_REVIEW",
    "FAILED",
    "CANCELLED",
)

ACQUISITION_SOURCE_KINDS = (
    "PDF_URL",
    "MANUAL_PDF_UPLOAD",
    "GOOGLE_DRIVE_REFERENCE",
    "OTHER_REFERENCE",
)

ACQUISITION_DISCOVERY_METHODS = (
    "ADMIN_URL",
    "ADMIN_UPLOAD",
    "KNOWN_SOURCE_REGISTRY",
    "EXTERNAL_DISCOVERY_PROVIDER",
)

ACQUISITION_RIGHTS_STATUSES = (
    "REVIEW_REQUIRED",
    "BLOCKED",
)

ACQUISITION_SOURCE_STATUSES = (
    "REGISTERED",
    "FETCHING",
    "FETCHED",
    "FAILED",
    "BLOCKED",
)

ACQUISITION_EXTRACTION_STATUSES = (
    "PENDING",
    "COMPLETE",
    "PARTIAL",
    "FAILED",
)

QUESTION_SUPPLY_USE_CASES = (
    "ROOT_CAUSE_VERIFICATION",
    "ADAPTIVE_REPAIR",
    "REVIEW",
    "CURRENT_LEARNING",
)

QUESTION_SUPPLY_TARGET_TYPES = (
    "CONCEPT",
    "PROBLEM_TYPE",
    "MISCONCEPTION",
)

QUESTION_SUPPLY_REASON_CODES = (
    "NO_APPROVED_TARGET_QUESTIONS",
    "INSUFFICIENT_APPROVED_TARGET_COUNT",
    "INSUFFICIENT_DIFFICULTY_COVERAGE",
    "NO_AUTO_EVALUABLE_TARGET_QUESTIONS",
    "STUDENT_EXPOSURE_EXHAUSTED",
    "THIN_APPROVED_TARGET_COUNT",
    "THIN_DIFFICULTY_COVERAGE",
)


def upgrade() -> None:
    # 1. question_acquisition_requests
    op.create_table(
        "question_acquisition_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "gap_id",
            sa.Uuid(),
            sa.ForeignKey("question_supply_gaps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "strategy",
            sa.Enum(
                *ACQUISITION_STRATEGIES,
                name="question_acquisition_strategy",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                *ACQUISITION_REQUEST_STATUSES,
                name="question_acquisition_request_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="PLANNED",
        ),
        sa.Column(
            "subject_id",
            sa.Uuid(),
            sa.ForeignKey("subjects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "use_case",
            sa.Enum(
                *QUESTION_SUPPLY_USE_CASES,
                name="question_supply_use_case",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "target_type",
            sa.Enum(
                *QUESTION_SUPPLY_TARGET_TYPES,
                name="question_supply_target_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "concept_id",
            sa.Uuid(),
            sa.ForeignKey("concepts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "problem_type_id",
            sa.Uuid(),
            sa.ForeignKey("problem_types.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "misconception_definition_id",
            sa.Uuid(),
            sa.ForeignKey("misconception_definitions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("difficulty_min", sa.Float(), nullable=False),
        sa.Column("difficulty_max", sa.Float(), nullable=False),
        sa.Column("desired_difficulty", sa.Float(), nullable=True),
        sa.Column("minimum_required_count", sa.Integer(), nullable=False),
        sa.Column("preferred_count", sa.Integer(), nullable=False),
        sa.Column(
            "shortage_reason_code",
            sa.Enum(
                *QUESTION_SUPPLY_REASON_CODES,
                name="question_supply_gap_reason_code",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "approved_eligible_count_snapshot",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "approved_in_band_count_snapshot",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "pipeline_candidate_count_snapshot",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "pipeline_runtime_eligible_count_snapshot",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "required_new_candidate_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "existing_candidate_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "external_candidate_target_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.UniqueConstraint("gap_id", "attempt_index", name="uq_acquisition_requests_gap_attempt"),
        sa.CheckConstraint("attempt_index >= 1", name="ck_acquisition_requests_attempt_positive"),
        sa.CheckConstraint(
            "minimum_required_count > 0 AND preferred_count >= minimum_required_count",
            name="ck_acquisition_requests_counts",
        ),
        sa.CheckConstraint(
            "required_new_candidate_count >= 0 AND existing_candidate_count >= 0 AND external_candidate_target_count >= 0",
            name="ck_acquisition_requests_candidate_counts",
        ),
        sa.CheckConstraint(
            "difficulty_min >= 0.0 AND difficulty_min <= difficulty_max AND difficulty_max <= 1.0",
            name="ck_acquisition_requests_difficulty_range",
        ),
    )
    op.create_index(
        "ix_acquisition_requests_gap_status",
        "question_acquisition_requests",
        ["gap_id", "status"],
    )
    op.create_index(
        "ix_acquisition_requests_status_created",
        "question_acquisition_requests",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_acquisition_requests_subject_status",
        "question_acquisition_requests",
        ["subject_id", "status"],
    )

    # 2. question_acquisition_existing_candidates
    op.create_table(
        "question_acquisition_existing_candidates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "request_id",
            sa.Uuid(),
            sa.ForeignKey("question_acquisition_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.Uuid(),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("difficulty_in_band", sa.Boolean(), nullable=False),
        sa.Column("runtime_eligible", sa.Boolean(), nullable=False),
        sa.Column("selection_rank", sa.Integer(), nullable=False),
        sa.Column("selection_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "request_id", "question_id", name="uq_acquisition_existing_candidates_req_q"
        ),
        sa.CheckConstraint(
            "selection_rank >= 1", name="ck_acquisition_existing_candidates_rank_positive"
        ),
    )
    op.create_index(
        "ix_acquisition_existing_candidates_req_rank",
        "question_acquisition_existing_candidates",
        ["request_id", "selection_rank"],
    )

    # 3. question_acquisition_sources
    op.create_table(
        "question_acquisition_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "request_id",
            sa.Uuid(),
            sa.ForeignKey("question_acquisition_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_kind",
            sa.Enum(
                *ACQUISITION_SOURCE_KINDS,
                name="question_acquisition_source_kind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "discovery_method",
            sa.Enum(
                *ACQUISITION_DISCOVERY_METHODS,
                name="question_acquisition_discovery_method",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("original_url", sa.Text(), nullable=True),
        sa.Column("normalized_url", sa.Text(), nullable=True),
        sa.Column("url_hash", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("publisher", sa.String(length=255), nullable=True),
        sa.Column("source_year", sa.Integer(), nullable=True),
        sa.Column(
            "rights_status",
            sa.Enum(
                *ACQUISITION_RIGHTS_STATUSES,
                name="question_acquisition_rights_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="REVIEW_REQUIRED",
        ),
        sa.Column(
            "status",
            sa.Enum(
                *ACQUISITION_SOURCE_STATUSES,
                name="question_acquisition_source_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="REGISTERED",
        ),
        sa.Column("provenance_note", sa.Text(), nullable=False),
        sa.Column(
            "registered_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_detail", sa.Text(), nullable=True),
        sa.UniqueConstraint("request_id", "url_hash", name="uq_acquisition_sources_req_url_hash"),
    )
    op.create_index(
        "ix_acquisition_sources_request_status",
        "question_acquisition_sources",
        ["request_id", "status"],
    )
    op.create_index(
        "ix_acquisition_sources_url_hash",
        "question_acquisition_sources",
        ["url_hash"],
    )

    # 4. question_acquisition_artifacts
    op.create_table(
        "question_acquisition_artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sha256", sa.String(length=64), unique=True, nullable=False),
        sa.Column(
            "mime_type",
            sa.String(length=100),
            nullable=False,
            server_default="application/pdf",
        ),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column(
            "extraction_status",
            sa.Enum(
                *ACQUISITION_EXTRACTION_STATUSES,
                name="question_acquisition_extraction_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("sha256", name="uq_acquisition_artifacts_sha256"),
        sa.CheckConstraint(
            "file_size_bytes > 0", name="ck_acquisition_artifacts_file_size_positive"
        ),
        sa.CheckConstraint(
            "length(sha256) = 64", name="ck_acquisition_artifacts_sha256_length"
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count > 0",
            name="ck_acquisition_artifacts_page_count_positive",
        ),
    )
    op.create_index(
        "ix_acquisition_artifacts_sha256",
        "question_acquisition_artifacts",
        ["sha256"],
    )

    # 5. question_acquisition_source_artifacts
    op.create_table(
        "question_acquisition_source_artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("question_acquisition_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "artifact_id",
            sa.Uuid(),
            sa.ForeignKey("question_acquisition_artifacts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "source_id", "artifact_id", name="uq_acquisition_source_artifacts"
        ),
    )
    op.create_index(
        "ix_acquisition_source_artifacts_source",
        "question_acquisition_source_artifacts",
        ["source_id"],
    )
    op.create_index(
        "ix_acquisition_source_artifacts_artifact",
        "question_acquisition_source_artifacts",
        ["artifact_id"],
    )

    # 6. question_acquisition_pages
    op.create_table(
        "question_acquisition_pages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "artifact_id",
            sa.Uuid(),
            sa.ForeignKey("question_acquisition_artifacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "artifact_id", "page_number", name="uq_acquisition_pages_artifact_page"
        ),
        sa.CheckConstraint("page_number >= 1", name="ck_acquisition_pages_page_positive"),
        sa.CheckConstraint(
            "char_count >= 0", name="ck_acquisition_pages_char_count_nonnegative"
        ),
        sa.CheckConstraint(
            "length(text_sha256) = 64", name="ck_acquisition_pages_text_sha256_length"
        ),
    )
    op.create_index(
        "ix_acquisition_pages_artifact_page",
        "question_acquisition_pages",
        ["artifact_id", "page_number"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_acquisition_pages_artifact_page", table_name="question_acquisition_pages"
    )
    op.drop_table("question_acquisition_pages")

    op.drop_index(
        "ix_acquisition_source_artifacts_artifact",
        table_name="question_acquisition_source_artifacts",
    )
    op.drop_index(
        "ix_acquisition_source_artifacts_source",
        table_name="question_acquisition_source_artifacts",
    )
    op.drop_table("question_acquisition_source_artifacts")

    op.drop_index(
        "ix_acquisition_artifacts_sha256", table_name="question_acquisition_artifacts"
    )
    op.drop_table("question_acquisition_artifacts")

    op.drop_index(
        "ix_acquisition_sources_url_hash", table_name="question_acquisition_sources"
    )
    op.drop_index(
        "ix_acquisition_sources_request_status",
        table_name="question_acquisition_sources",
    )
    op.drop_table("question_acquisition_sources")

    op.drop_index(
        "ix_acquisition_existing_candidates_req_rank",
        table_name="question_acquisition_existing_candidates",
    )
    op.drop_table("question_acquisition_existing_candidates")

    op.drop_index(
        "ix_acquisition_requests_subject_status",
        table_name="question_acquisition_requests",
    )
    op.drop_index(
        "ix_acquisition_requests_status_created",
        table_name="question_acquisition_requests",
    )
    op.drop_index(
        "ix_acquisition_requests_gap_status",
        table_name="question_acquisition_requests",
    )
    op.drop_table("question_acquisition_requests")
