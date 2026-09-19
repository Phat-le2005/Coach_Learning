"""Persist and index normalized question content hashes.

Revision ID: 0012_question_content_hash
Revises: 0011_mastery_engine
"""
from collections.abc import Sequence
import hashlib
import re
import unicodedata

from alembic import op
import sqlalchemy as sa

revision: str = "0012_question_content_hash"
down_revision: str | Sequence[str] | None = "0011_mastery_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WHITESPACE = re.compile(r"\s+")


def _fingerprint(content: str) -> str:
    normalized = unicodedata.normalize("NFKC", content)
    normalized = _WHITESPACE.sub(" ", normalized).strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    connection = op.get_bind()
    questions = sa.table(
        "questions",
        sa.column("id", sa.Uuid()),
        sa.column("content", sa.Text()),
        sa.column("content_hash", sa.String(length=64)),
    )
    result = connection.execute(sa.select(questions.c.id, questions.c.content))
    for partition in result.partitions(500):
        updates = [
            {
                "question_id": row.id,
                "question_hash": _fingerprint(row.content),
            }
            for row in partition
        ]
        if updates:
            connection.execute(
                sa.update(questions)
                .where(questions.c.id == sa.bindparam("question_id"))
                .values(content_hash=sa.bindparam("question_hash")),
                updates,
            )
    with op.batch_alter_table("questions") as batch_op:
        batch_op.alter_column(
            "content_hash",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch_op.create_check_constraint(
            op.f("ck_questions_content_hash_length"),
            "length(content_hash) = 64",
        )
    op.create_index(
        "ix_questions_content_hash",
        "questions",
        ["content_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_questions_content_hash", table_name="questions")
    with op.batch_alter_table("questions") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_questions_content_hash_length"),
            type_="check",
        )
        batch_op.drop_column("content_hash")
