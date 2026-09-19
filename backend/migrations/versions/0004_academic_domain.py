"""Relational subjects, concepts and typed concept graph edges.

Revision ID: 0004_academic_domain
Revises: 0003_profiles
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_academic_domain"
down_revision: str | Sequence[str] | None = "0003_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("grade_level", sa.SmallInteger(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name=op.f("ck_subjects_code_normalized")),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_subjects_name_not_blank")),
        sa.CheckConstraint("grade_level BETWEEN 1 AND 12", name=op.f("ck_subjects_grade_level_range")),
        sa.CheckConstraint("description IS NULL OR length(trim(description)) > 0", name=op.f("ck_subjects_description_not_blank")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subjects")),
        sa.UniqueConstraint("code", name=op.f("uq_subjects_code")),
    )
    op.create_table(
        "concepts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("grade_level", sa.SmallInteger(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name=op.f("ck_concepts_code_normalized")),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_concepts_name_not_blank")),
        sa.CheckConstraint("length(trim(description)) > 0", name=op.f("ck_concepts_description_not_blank")),
        sa.CheckConstraint("grade_level BETWEEN 1 AND 12", name=op.f("ck_concepts_grade_level_range")),
        sa.CheckConstraint("order_index >= 0", name=op.f("ck_concepts_order_index_nonnegative")),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], name=op.f("fk_concepts_subject_id_subjects"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concepts")),
        sa.UniqueConstraint("subject_id", "code", name=op.f("uq_concepts_subject_code")),
    )
    op.create_index(op.f("ix_concepts_subject_order"), "concepts", ["subject_id", "order_index", "code"])
    op.create_table(
        "concept_relations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_concept_id", sa.Uuid(), nullable=False),
        sa.Column("target_concept_id", sa.Uuid(), nullable=False),
        sa.Column("relation_type", sa.Enum("PREREQUISITE", "PART_OF", "RELATED_TO", native_enum=False, create_constraint=True, name="concept_relation_type"), nullable=False),
        sa.CheckConstraint("source_concept_id <> target_concept_id", name=op.f("ck_concept_relations_no_self_relation")),
        sa.CheckConstraint("relation_type <> 'RELATED_TO' OR source_concept_id < target_concept_id", name=op.f("ck_concept_relations_related_canonical_order")),
        sa.ForeignKeyConstraint(["source_concept_id"], ["concepts.id"], name=op.f("fk_concept_relations_source_concept_id_concepts"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_concept_id"], ["concepts.id"], name=op.f("fk_concept_relations_target_concept_id_concepts"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concept_relations")),
        sa.UniqueConstraint("source_concept_id", "target_concept_id", "relation_type", name=op.f("uq_concept_relations_edge")),
    )
    op.create_index(op.f("ix_concept_relations_type_source"), "concept_relations", ["relation_type", "source_concept_id"])
    op.create_index(op.f("ix_concept_relations_type_target"), "concept_relations", ["relation_type", "target_concept_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_concept_relations_type_target"), table_name="concept_relations")
    op.drop_index(op.f("ix_concept_relations_type_source"), table_name="concept_relations")
    op.drop_table("concept_relations")
    op.drop_index(op.f("ix_concepts_subject_order"), table_name="concepts")
    op.drop_table("concepts")
    op.drop_table("subjects")
