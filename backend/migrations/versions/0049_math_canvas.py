"""Persist exploratory graphs and their server-generated explanations."""
from alembic import op
import sqlalchemy as sa

revision = "0049_math_canvas"
down_revision = "0048_math_ink_retention_index"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("math_canvas_explanations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("attempt_id", sa.Uuid(), sa.ForeignKey("math_solution_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("spec_hash", sa.String(64), nullable=False), sa.Column("text", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False), sa.Column("model", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_math_canvas_explanations_attempt_id", "math_canvas_explanations", ["attempt_id"])
    op.create_table("math_canvas_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("attempt_id", sa.Uuid(), sa.ForeignKey("math_solution_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("student_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("client_action_id", sa.Uuid(), nullable=False), sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("expression", sa.String(500), nullable=False), sa.Column("dimension", sa.String(2), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False), sa.Column("camera", sa.JSON(), nullable=False),
        sa.Column("page_index", sa.Integer(), nullable=False), sa.Column("source_latex", sa.String(500), nullable=False),
        sa.Column("source_strokes", sa.JSON(), nullable=False), sa.Column("source_ink_revision", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("explanation_id", sa.Uuid(), sa.ForeignKey("math_canvas_explanations.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("attempt_id", "client_action_id", name="uq_math_canvas_action"))
    op.create_index("ix_math_canvas_snapshots_attempt_id", "math_canvas_snapshots", ["attempt_id"])
    op.create_index("ix_math_canvas_student_created", "math_canvas_snapshots", ["student_id", "created_at"])


def downgrade():
    op.drop_table("math_canvas_snapshots")
    op.drop_table("math_canvas_explanations")
