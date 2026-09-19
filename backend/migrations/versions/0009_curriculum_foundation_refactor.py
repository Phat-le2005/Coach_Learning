"""Versioned curriculum hierarchy and question classification mappings.

Revision ID: 0009_curriculum_refactor
Revises: 0008_synthetic_students
"""
from collections.abc import Sequence
from uuid import UUID

from alembic import op
import sqlalchemy as sa

revision: str = "0009_curriculum_refactor"
down_revision: str | Sequence[str] | None = "0008_synthetic_students"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_CURRICULUM_ID = UUID("c65a10e9-9850-5ad9-afeb-8448634b4a8f")
LEGACY_VERSION_ID = UUID("a8ee8b78-f064-54d9-9e2b-586543c9682d")


def upgrade() -> None:
    op.create_table(
        "curricula",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name=op.f("ck_curricula_code_normalized")),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_curricula_name_not_blank")),
        sa.CheckConstraint("description IS NULL OR length(trim(description)) > 0", name=op.f("ck_curricula_description_not_blank")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_curricula")),
        sa.UniqueConstraint("code", name=op.f("uq_curricula_code")),
    )
    op.create_table(
        "curriculum_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("curriculum_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_reference", sa.String(1000), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name=op.f("ck_curriculum_versions_code_normalized")),
        sa.CheckConstraint("length(trim(version)) > 0", name=op.f("ck_curriculum_versions_version_not_blank")),
        sa.CheckConstraint("effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from", name=op.f("ck_curriculum_versions_effective_range")),
        sa.CheckConstraint("source_reference IS NULL OR length(trim(source_reference)) > 0", name=op.f("ck_curriculum_versions_source_reference_not_blank")),
        sa.ForeignKeyConstraint(["curriculum_id"], ["curricula.id"], name=op.f("fk_curriculum_versions_curriculum_id_curricula"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_curriculum_versions")),
        sa.UniqueConstraint("curriculum_id", "code", name=op.f("uq_curriculum_versions_curriculum_code")),
    )
    op.create_index("ix_curriculum_versions_curriculum_active", "curriculum_versions", ["curriculum_id", "is_active"])

    curricula = sa.table(
        "curricula",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
    )
    versions = sa.table(
        "curriculum_versions",
        sa.column("id", sa.Uuid()),
        sa.column("curriculum_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("version", sa.String()),
        sa.column("source_reference", sa.String()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(curricula, [{
        "id": LEGACY_CURRICULUM_ID,
        "code": "LEGACY",
        "name": "Legacy unversioned curriculum",
        "description": "Compatibility owner for subjects created before curriculum versioning.",
    }])
    op.bulk_insert(versions, [{
        "id": LEGACY_VERSION_ID,
        "curriculum_id": LEGACY_CURRICULUM_ID,
        "code": "V1",
        "version": "legacy-v1",
        "source_reference": None,
        "is_active": True,
    }])

    with op.batch_alter_table("subjects") as batch_op:
        batch_op.add_column(sa.Column(
            "curriculum_version_id",
            sa.Uuid(),
            nullable=True,
        ))
        batch_op.add_column(sa.Column("order_index", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    legacy_subjects = sa.table(
        "subjects",
        sa.column("curriculum_version_id", sa.Uuid()),
    )
    op.execute(
        legacy_subjects.update().values(curriculum_version_id=LEGACY_VERSION_ID)
    )
    with op.batch_alter_table("subjects") as batch_op:
        batch_op.alter_column(
            "curriculum_version_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
        batch_op.drop_constraint(op.f("uq_subjects_code"), type_="unique")
        batch_op.create_unique_constraint("uq_subjects_version_code", ["curriculum_version_id", "code"])
        batch_op.create_foreign_key(
            op.f("fk_subjects_curriculum_version_id_curriculum_versions"),
            "curriculum_versions",
            ["curriculum_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_check_constraint(
            op.f("ck_subjects_order_index_nonnegative"),
            "order_index IS NULL OR order_index >= 0",
        )

    with op.batch_alter_table("concepts") as batch_op:
        batch_op.drop_constraint(op.f("ck_concepts_description_not_blank"), type_="check")
        batch_op.drop_constraint(op.f("ck_concepts_grade_level_range"), type_="check")
        batch_op.drop_constraint(op.f("ck_concepts_order_index_nonnegative"), type_="check")
        batch_op.alter_column("description", existing_type=sa.Text(), nullable=True)
        batch_op.alter_column("grade_level", existing_type=sa.SmallInteger(), nullable=True)
        batch_op.alter_column("order_index", existing_type=sa.Integer(), nullable=True)
        batch_op.create_check_constraint(
            op.f("ck_concepts_description_not_blank"),
            "description IS NULL OR length(trim(description)) > 0",
        )
        batch_op.create_check_constraint(
            op.f("ck_concepts_grade_level_range"),
            "grade_level IS NULL OR grade_level BETWEEN 1 AND 12",
        )
        batch_op.create_check_constraint(
            op.f("ck_concepts_order_index_nonnegative"),
            "order_index IS NULL OR order_index >= 0",
        )

    with op.batch_alter_table("concept_relations") as batch_op:
        batch_op.drop_constraint(
            op.f("fk_concept_relations_source_concept_id_concepts"), type_="foreignkey"
        )
        batch_op.drop_constraint(
            op.f("fk_concept_relations_target_concept_id_concepts"), type_="foreignkey"
        )
        batch_op.create_foreign_key(
            op.f("fk_concept_relations_source_concept_id_concepts"),
            "concepts", ["source_concept_id"], ["id"], ondelete="RESTRICT"
        )
        batch_op.create_foreign_key(
            op.f("fk_concept_relations_target_concept_id_concepts"),
            "concepts", ["target_concept_id"], ["id"], ondelete="RESTRICT"
        )

    _create_curriculum_hierarchy()
    _extend_questions()

    with op.batch_alter_table("student_attempts") as batch_op:
        batch_op.add_column(sa.Column("problem_type_id", sa.Uuid(), nullable=True))
    with op.batch_alter_table("student_attempts") as batch_op:
        batch_op.create_foreign_key(
            op.f("fk_student_attempts_problem_type_id_problem_types"),
            "problem_types", ["problem_type_id"], ["id"], ondelete="SET NULL"
        )
    op.create_index(
        "ix_student_attempts_problem_type_student",
        "student_attempts",
        ["problem_type_id", "student_id"],
    )


def _create_curriculum_hierarchy() -> None:
    op.create_table(
        "chapters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name=op.f("ck_chapters_code_normalized")),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_chapters_name_not_blank")),
        sa.CheckConstraint("order_index >= 0", name=op.f("ck_chapters_order_index_nonnegative")),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], name=op.f("fk_chapters_subject_id_subjects"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chapters")),
        sa.UniqueConstraint("subject_id", "code", name=op.f("uq_chapters_subject_code")),
    )
    op.create_index("ix_chapters_subject_order", "chapters", ["subject_id", "order_index", "code"])
    op.create_table(
        "topics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chapter_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name=op.f("ck_topics_code_normalized")),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_topics_name_not_blank")),
        sa.CheckConstraint("order_index >= 0", name=op.f("ck_topics_order_index_nonnegative")),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], name=op.f("fk_topics_chapter_id_chapters"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_topics")),
        sa.UniqueConstraint("chapter_id", "code", name=op.f("uq_topics_chapter_code")),
    )
    op.create_index("ix_topics_chapter_order", "topics", ["chapter_id", "order_index", "code"])
    op.create_table(
        "problem_types",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("default_difficulty", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name=op.f("ck_problem_types_code_normalized")),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_problem_types_name_not_blank")),
        sa.CheckConstraint("order_index >= 0", name=op.f("ck_problem_types_order_index_nonnegative")),
        sa.CheckConstraint("default_difficulty IS NULL OR default_difficulty BETWEEN 0.0 AND 1.0", name=op.f("ck_problem_types_default_difficulty_range")),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], name=op.f("fk_problem_types_topic_id_topics"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_problem_types")),
        sa.UniqueConstraint("topic_id", "code", name=op.f("uq_problem_types_topic_code")),
    )
    op.create_index("ix_problem_types_topic_order", "problem_types", ["topic_id", "order_index", "code"])
    op.create_table(
        "learning_outcomes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("grade_level", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=True),
        sa.Column("source_reference", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name=op.f("ck_learning_outcomes_code_normalized")),
        sa.CheckConstraint("length(trim(description)) > 0", name=op.f("ck_learning_outcomes_description_not_blank")),
        sa.CheckConstraint("grade_level BETWEEN 1 AND 12", name=op.f("ck_learning_outcomes_grade_level_range")),
        sa.CheckConstraint("order_index IS NULL OR order_index >= 0", name=op.f("ck_learning_outcomes_order_index_nonnegative")),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], name=op.f("fk_learning_outcomes_subject_id_subjects"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learning_outcomes")),
        sa.UniqueConstraint("subject_id", "code", name=op.f("uq_learning_outcomes_subject_code")),
    )
    op.create_index("ix_learning_outcomes_subject_order", "learning_outcomes", ["subject_id", "order_index", "code"])
    op.create_table(
        "problem_type_concepts",
        sa.Column("problem_type_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.CheckConstraint("weight > 0.0 AND weight <= 1.0", name=op.f("ck_problem_type_concepts_weight_range")),
        sa.ForeignKeyConstraint(["concept_id"], ["concepts.id"], name=op.f("fk_problem_type_concepts_concept_id_concepts"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["problem_type_id"], ["problem_types.id"], name=op.f("fk_problem_type_concepts_problem_type_id_problem_types"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("problem_type_id", "concept_id", name=op.f("pk_problem_type_concepts")),
    )
    op.create_index("ix_problem_type_concepts_concept_problem_type", "problem_type_concepts", ["concept_id", "problem_type_id"])
    op.create_table(
        "problem_type_learning_outcomes",
        sa.Column("problem_type_id", sa.Uuid(), nullable=False),
        sa.Column("learning_outcome_id", sa.Uuid(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.CheckConstraint("weight IS NULL OR (weight > 0.0 AND weight <= 1.0)", name=op.f("ck_problem_type_learning_outcomes_weight_range")),
        sa.ForeignKeyConstraint(["learning_outcome_id"], ["learning_outcomes.id"], name=op.f("fk_problem_type_learning_outcomes_learning_outcome_id_learning_outcomes"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["problem_type_id"], ["problem_types.id"], name=op.f("fk_problem_type_learning_outcomes_problem_type_id_problem_types"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("problem_type_id", "learning_outcome_id", name=op.f("pk_problem_type_learning_outcomes")),
    )
    op.create_index("ix_problem_type_learning_outcomes_outcome_problem_type", "problem_type_learning_outcomes", ["learning_outcome_id", "problem_type_id"])
    op.create_table(
        "curriculum_import_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_code", sa.String(150), nullable=False),
        sa.Column("dataset_version", sa.String(100), nullable=False),
        sa.Column("curriculum_version_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(content_hash) = 64", name=op.f("ck_curriculum_import_history_content_hash_length")),
        sa.ForeignKeyConstraint(["curriculum_version_id"], ["curriculum_versions.id"], name=op.f("fk_curriculum_import_history_curriculum_version_id_curriculum_versions"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_curriculum_import_history")),
        sa.UniqueConstraint("dataset_code", "dataset_version", "content_hash", name=op.f("uq_curriculum_import_history_dataset_version_hash")),
    )
    op.create_index("ix_curriculum_import_history_version_time", "curriculum_import_history", ["curriculum_version_id", "imported_at"])


def _extend_questions() -> None:
    with op.batch_alter_table("questions") as batch_op:
        batch_op.add_column(sa.Column("source_year", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column(
            "cognitive_level",
            sa.Enum(
                "REMEMBER", "UNDERSTAND", "APPLY", "ANALYZE",
                native_enum=False,
                create_constraint=False,
                name="question_cognitive_level",
            ),
            nullable=True,
        ))
    with op.batch_alter_table("questions") as batch_op:
        batch_op.create_check_constraint(
            op.f("ck_questions_source_year_range"),
            "source_year IS NULL OR source_year BETWEEN 1900 AND 2100",
        )
        batch_op.create_check_constraint(
            op.f("ck_questions_question_cognitive_level"),
            "cognitive_level IN ('REMEMBER', 'UNDERSTAND', 'APPLY', 'ANALYZE')",
        )
    op.create_table(
        "question_problem_types",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("problem_type_id", sa.Uuid(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.CheckConstraint("weight IS NULL OR (weight > 0.0 AND weight <= 1.0)", name=op.f("ck_question_problem_types_weight_range")),
        sa.ForeignKeyConstraint(["problem_type_id"], ["problem_types.id"], name=op.f("fk_question_problem_types_problem_type_id_problem_types"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], name=op.f("fk_question_problem_types_question_id_questions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("question_id", "problem_type_id", name=op.f("pk_question_problem_types")),
    )
    op.create_index("ix_question_problem_types_problem_type_question", "question_problem_types", ["problem_type_id", "question_id"])
    op.create_table(
        "question_learning_outcomes",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("learning_outcome_id", sa.Uuid(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.CheckConstraint("weight IS NULL OR (weight > 0.0 AND weight <= 1.0)", name=op.f("ck_question_learning_outcomes_weight_range")),
        sa.ForeignKeyConstraint(["learning_outcome_id"], ["learning_outcomes.id"], name=op.f("fk_question_learning_outcomes_learning_outcome_id_learning_outcomes"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], name=op.f("fk_question_learning_outcomes_question_id_questions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("question_id", "learning_outcome_id", name=op.f("pk_question_learning_outcomes")),
    )
    op.create_index("ix_question_learning_outcomes_outcome_question", "question_learning_outcomes", ["learning_outcome_id", "question_id"])


def downgrade() -> None:
    op.drop_index("ix_student_attempts_problem_type_student", table_name="student_attempts")
    with op.batch_alter_table("student_attempts") as batch_op:
        batch_op.drop_constraint(
            op.f("fk_student_attempts_problem_type_id_problem_types"), type_="foreignkey"
        )
        batch_op.drop_column("problem_type_id")
    op.drop_index("ix_question_learning_outcomes_outcome_question", table_name="question_learning_outcomes")
    op.drop_table("question_learning_outcomes")
    op.drop_index("ix_question_problem_types_problem_type_question", table_name="question_problem_types")
    op.drop_table("question_problem_types")
    with op.batch_alter_table("questions") as batch_op:
        batch_op.drop_constraint(op.f("ck_questions_question_cognitive_level"), type_="check")
        batch_op.drop_constraint(op.f("ck_questions_source_year_range"), type_="check")
        batch_op.drop_column("cognitive_level")
        batch_op.drop_column("source_year")
    op.drop_index("ix_curriculum_import_history_version_time", table_name="curriculum_import_history")
    op.drop_table("curriculum_import_history")
    op.drop_index("ix_problem_type_learning_outcomes_outcome_problem_type", table_name="problem_type_learning_outcomes")
    op.drop_table("problem_type_learning_outcomes")
    op.drop_index("ix_problem_type_concepts_concept_problem_type", table_name="problem_type_concepts")
    op.drop_table("problem_type_concepts")
    op.drop_index("ix_learning_outcomes_subject_order", table_name="learning_outcomes")
    op.drop_table("learning_outcomes")
    op.drop_index("ix_problem_types_topic_order", table_name="problem_types")
    op.drop_table("problem_types")
    op.drop_index("ix_topics_chapter_order", table_name="topics")
    op.drop_table("topics")
    op.drop_index("ix_chapters_subject_order", table_name="chapters")
    op.drop_table("chapters")

    with op.batch_alter_table("concept_relations") as batch_op:
        batch_op.drop_constraint(op.f("fk_concept_relations_source_concept_id_concepts"), type_="foreignkey")
        batch_op.drop_constraint(op.f("fk_concept_relations_target_concept_id_concepts"), type_="foreignkey")
        batch_op.create_foreign_key(op.f("fk_concept_relations_source_concept_id_concepts"), "concepts", ["source_concept_id"], ["id"], ondelete="CASCADE")
        batch_op.create_foreign_key(op.f("fk_concept_relations_target_concept_id_concepts"), "concepts", ["target_concept_id"], ["id"], ondelete="CASCADE")
    with op.batch_alter_table("concepts") as batch_op:
        batch_op.drop_constraint(op.f("ck_concepts_description_not_blank"), type_="check")
        batch_op.drop_constraint(op.f("ck_concepts_grade_level_range"), type_="check")
        batch_op.drop_constraint(op.f("ck_concepts_order_index_nonnegative"), type_="check")
        batch_op.alter_column("description", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("grade_level", existing_type=sa.SmallInteger(), nullable=False)
        batch_op.alter_column("order_index", existing_type=sa.Integer(), nullable=False)
        batch_op.create_check_constraint(
            op.f("ck_concepts_description_not_blank"),
            "length(trim(description)) > 0",
        )
        batch_op.create_check_constraint(
            op.f("ck_concepts_grade_level_range"), "grade_level BETWEEN 1 AND 12"
        )
        batch_op.create_check_constraint(
            op.f("ck_concepts_order_index_nonnegative"), "order_index >= 0"
        )
    with op.batch_alter_table("subjects") as batch_op:
        batch_op.drop_constraint(op.f("fk_subjects_curriculum_version_id_curriculum_versions"), type_="foreignkey")
        batch_op.drop_constraint(op.f("uq_subjects_version_code"), type_="unique")
        batch_op.drop_constraint(op.f("ck_subjects_order_index_nonnegative"), type_="check")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
        batch_op.drop_column("order_index")
        batch_op.drop_column("curriculum_version_id")
        batch_op.create_unique_constraint(op.f("uq_subjects_code"), ["code"])
    op.drop_index("ix_curriculum_versions_curriculum_active", table_name="curriculum_versions")
    op.drop_table("curriculum_versions")
    op.drop_table("curricula")
