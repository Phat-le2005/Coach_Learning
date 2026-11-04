"""Join the Math Canvas and theory library migration branches.

Both branches may already be deployed independently. This revision only joins
 their history; Alembic applies missing ancestors without rewriting data.
"""

revision = "0054_merge_canvas_theory"
down_revision = ("0050_merge_math_canvas_paper", "0053_theory_source_library")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
