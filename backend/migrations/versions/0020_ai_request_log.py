"""AI Observability: AIRequestLog table for monitoring, telemetry, and cost tracking.

Revision ID: 0020_ai_request_log
Revises: 0019_study_planning_core
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0020_ai_request_log"
down_revision: str | Sequence[str] | None = "0019_study_planning_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_request_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("task", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_name", sa.String(length=100), server_default="default", nullable=False),
        sa.Column("prompt_version", sa.String(length=50), server_default="v1", nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_ai_request_logs_created_at", "ai_request_logs", ["created_at"])
    op.create_index("ix_ai_request_logs_task", "ai_request_logs", ["task"])
    op.create_index("ix_ai_request_logs_user_id", "ai_request_logs", ["user_id"])
    op.create_index("ix_ai_request_logs_provider_model", "ai_request_logs", ["provider", "model"])
    op.create_index("ix_ai_request_logs_success", "ai_request_logs", ["success"])


def downgrade() -> None:
    op.drop_index("ix_ai_request_logs_success", table_name="ai_request_logs")
    op.drop_index("ix_ai_request_logs_provider_model", table_name="ai_request_logs")
    op.drop_index("ix_ai_request_logs_user_id", table_name="ai_request_logs")
    op.drop_index("ix_ai_request_logs_task", table_name="ai_request_logs")
    op.drop_index("ix_ai_request_logs_created_at", table_name="ai_request_logs")
    op.drop_table("ai_request_logs")
