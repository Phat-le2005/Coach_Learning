"""Staged CSV and JSON question import pipeline.

Revision ID: 0007_question_import
Revises: 0006_question_bank
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0007_question_import"
down_revision: str | Sequence[str] | None = "0006_question_bank"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "question_import_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column(
            "file_format",
            sa.Enum(
                "CSV", "JSON", native_enum=False, create_constraint=True,
                name="question_import_file_format",
            ),
            nullable=False,
        ),
        sa.Column("trusted_seed_data", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PREVIEWED", "IMPORTED", native_enum=False, create_constraint=True,
                name="question_import_batch_status",
            ),
            server_default="PREVIEWED",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(trim(file_name)) > 0",
            name=op.f("ck_question_import_batches_file_name_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            name=op.f("fk_question_import_batches_created_by_users"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_import_batches")),
    )
    op.create_index(
        "ix_question_import_batches_created_by_status",
        "question_import_batches",
        ["created_by", "status"],
    )

    op.create_table(
        "question_import_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "VALID", "INVALID", "DUPLICATE", "IMPORTED",
                native_enum=False, create_constraint=True,
                name="question_import_row_status",
            ),
            nullable=False,
        ),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("normalized_data", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("imported_question_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "row_number > 0", name=op.f("ck_question_import_rows_row_number_positive")
        ),
        sa.CheckConstraint(
            "content_hash IS NULL OR length(content_hash) = 64",
            name=op.f("ck_question_import_rows_content_hash_length"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["question_import_batches.id"],
            name=op.f("fk_question_import_rows_batch_id_question_import_batches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["imported_question_id"], ["questions.id"],
            name=op.f("fk_question_import_rows_imported_question_id_questions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_import_rows")),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_question_import_rows_batch_row"),
    )
    op.create_index(
        "ix_question_import_rows_batch_status",
        "question_import_rows",
        ["batch_id", "status", "row_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_question_import_rows_batch_status", table_name="question_import_rows")
    op.drop_table("question_import_rows")
    op.drop_index(
        "ix_question_import_batches_created_by_status", table_name="question_import_batches"
    )
    op.drop_table("question_import_batches")
