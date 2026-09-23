"""Add admission import history table and link to admission rules.

Revision ID: 0028_admission_import
Revises: 0027_admission_domain
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0028_admission_import"
down_revision: str | Sequence[str] | None = "0027_admission_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. admission_import_histories
    op.create_table(
        "admission_import_histories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column(
            "file_format",
            sa.Enum(
                "CSV",
                "JSON",
                "DIRECT_FEED",
                name="admission_import_format",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PREVIEWED",
                "COMPLETED",
                "FAILED",
                name="admission_import_status",
                native_enum=False,
            ),
            server_default="PREVIEWED",
            nullable=False,
        ),
        sa.Column("total_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("valid_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("imported_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("updated_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("skipped_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("preview_data", sa.JSON(), nullable=True),
        sa.Column("target_year", sa.Integer(), nullable=True),
        sa.Column("data_source_id", sa.Uuid(), nullable=True),
        sa.Column("data_source_name", sa.String(length=300), nullable=True),
        sa.Column("source_reference", sa.String(length=1000), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("import_metadata", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(trim(file_name)) > 0", name=op.f("ck_admission_import_histories_file_name_not_blank")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_admission_import_histories_created_by_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["data_source_id"], ["admission_data_sources.id"], name=op.f("fk_admission_import_histories_data_source_id_admission_data_sources"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admission_import_histories")),
    )
    op.create_index(
        op.f("ix_admission_import_histories_status"),
        "admission_import_histories",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admission_import_histories_created_at"),
        "admission_import_histories",
        ["created_at"],
        unique=False,
    )

    # 2. Add import_history_id to admission_rules
    with op.batch_alter_table("admission_rules") as batch_op:
        batch_op.add_column(
            sa.Column("import_history_id", sa.Uuid(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_admission_rules_import_history_id_admission_import_histories",
            "admission_import_histories",
            ["import_history_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_admission_rules_import_history",
            ["import_history_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("admission_rules") as batch_op:
        batch_op.drop_index("ix_admission_rules_import_history")
        batch_op.drop_constraint("fk_admission_rules_import_history_id_admission_import_histories", type_="foreignkey")
        batch_op.drop_column("import_history_id")

    op.drop_index(op.f("ix_admission_import_histories_created_at"), table_name="admission_import_histories")
    op.drop_index(op.f("ix_admission_import_histories_status"), table_name="admission_import_histories")
    op.drop_table("admission_import_histories")
