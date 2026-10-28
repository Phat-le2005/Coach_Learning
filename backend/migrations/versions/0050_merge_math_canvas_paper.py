"""Merge the Math Canvas and paper attachment migration branches.

Both feature migrations extend 0048. Preserve either already-applied branch
and let Alembic apply the other before recording one deployable head.
"""

revision = "0050_merge_math_canvas_paper"
down_revision = ("0049_math_canvas", "0049_math_paper_attachments")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
