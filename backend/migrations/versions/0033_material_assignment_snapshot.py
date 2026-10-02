"""Freeze teacher material assignment content and support audited grading.

Revision ID: 0033_material_assignment_snapshot
Revises: 0032_teacher_materials_evidence

Existing assignment links are backfilled from the source's current state. Historical
source edits before this migration cannot be reconstructed; future publishes freeze
the source at publish time.
"""
from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "0033_material_assignment_snapshot"
down_revision: str | Sequence[str] | None = "0032_teacher_materials_evidence"
branch_labels = None
depends_on = None


def _mapping_table(name: str, target_table: str, target_column: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "assignment_material_item_id",
            sa.Uuid(),
            sa.ForeignKey("assignment_material_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            target_column,
            sa.Uuid(),
            sa.ForeignKey(f"{target_table}.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("assignment_material_item_id", target_column),
    )


def upgrade() -> None:
    with op.batch_alter_table("assignment_material_items") as batch:
        batch.add_column(sa.Column("teacher_material_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("source_content_hash", sa.String(64), nullable=True))
        batch.add_column(sa.Column("content", sa.Text(), nullable=True))
        batch.add_column(sa.Column("question_type", sa.Enum(
            "MULTIPLE_CHOICE", "TRUE_FALSE", "SHORT_ANSWER", "OPEN_RESPONSE",
            native_enum=False, name="assignment_material_question_type",
        ), nullable=True))
        batch.add_column(sa.Column("correct_answer", sa.Text(), nullable=True))
        batch.add_column(sa.Column("explanation", sa.Text(), nullable=True))
        batch.add_column(sa.Column("difficulty", sa.Float(), nullable=True))
        batch.add_column(sa.Column("evaluation_mode", sa.Enum(
            "OBJECTIVE_AUTO", "OPEN_RESPONSE", "TEACHER_REVIEW",
            native_enum=False, name="assignment_material_evaluation_mode",
        ), nullable=True))
        batch.add_column(sa.Column("snapshotted_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_assignment_material_items_teacher_material_id",
            "teacher_materials", ["teacher_material_id"], ["id"], ondelete="RESTRICT",
        )

    op.create_table(
        "assignment_material_item_options",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("assignment_material_item_id", sa.Uuid(), sa.ForeignKey(
            "assignment_material_items.id", ondelete="CASCADE",
        ), nullable=False),
        sa.Column("label", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.UniqueConstraint("assignment_material_item_id", "label"),
        sa.UniqueConstraint("assignment_material_item_id", "order_index"),
    )
    _mapping_table("assignment_material_item_concepts", "concepts", "concept_id")
    _mapping_table("assignment_material_item_problem_types", "problem_types", "problem_type_id")
    _mapping_table("assignment_material_item_learning_outcomes", "learning_outcomes", "learning_outcome_id")

    with op.batch_alter_table("student_assignment_material_items") as batch:
        batch.add_column(sa.Column("assignment_material_item_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("graded_by", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("teacher_feedback", sa.Text(), nullable=True))
        batch.create_foreign_key(
            "fk_student_assignment_material_items_snapshot",
            "assignment_material_items", ["assignment_material_item_id"], ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_student_assignment_material_items_graded_by",
            "users", ["graded_by"], ["id"], ondelete="RESTRICT",
        )
        batch.create_unique_constraint(
            "uq_student_assignment_material_snapshot",
            ["student_assignment_id", "assignment_material_item_id"],
        )

    connection = op.get_bind()
    metadata = sa.MetaData()
    names = (
        "assignment_material_items", "teacher_material_items",
        "teacher_material_item_options", "teacher_material_item_concepts",
        "teacher_material_item_problem_types", "teacher_material_item_learning_outcomes",
        "assignment_material_item_options", "assignment_material_item_concepts",
        "assignment_material_item_problem_types", "assignment_material_item_learning_outcomes",
        "student_assignment_material_items", "student_assignments",
        "assignment_student_questions", "assignments",
    )
    tables = {
        name: sa.Table(name, metadata, autoload_with=connection)
        for name in names
    }
    links = tables["assignment_material_items"]
    source_items = tables["teacher_material_items"]
    snapshot_by_assignment_source = {}
    for link in connection.execute(sa.select(links)).mappings():
        assignment_status = connection.execute(
            sa.select(tables["assignments"].c.status).where(
                tables["assignments"].c.id == link["assignment_id"]
            )
        ).scalar_one()
        if assignment_status == "DRAFT":
            continue
        source = connection.execute(
            sa.select(source_items).where(source_items.c.id == link["teacher_material_item_id"])
        ).mappings().one()
        connection.execute(
            links.update().where(links.c.id == link["id"]).values(
                teacher_material_id=source["teacher_material_id"],
                source_content_hash=source["content_hash"],
                content=source["content"],
                question_type=source["question_type"],
                correct_answer=source["correct_answer"],
                explanation=source["explanation"],
                difficulty=source["difficulty"],
                evaluation_mode=source["evaluation_mode"],
                snapshotted_at=datetime.now(timezone.utc),
            )
        )
        snapshot_by_assignment_source[
            (link["assignment_id"], link["teacher_material_item_id"])
        ] = link["id"]
        for source_name, snapshot_name, target_column in (
            ("teacher_material_item_concepts", "assignment_material_item_concepts", "concept_id"),
            ("teacher_material_item_problem_types", "assignment_material_item_problem_types", "problem_type_id"),
            ("teacher_material_item_learning_outcomes", "assignment_material_item_learning_outcomes", "learning_outcome_id"),
        ):
            source_table = tables[source_name]
            snapshot_table = tables[snapshot_name]
            mappings = connection.execute(
                sa.select(source_table).where(
                    source_table.c.item_id == link["teacher_material_item_id"],
                    source_table.c.status == "CONFIRMED",
                )
            ).mappings()
            for mapping in mappings:
                connection.execute(snapshot_table.insert().values(
                    id=uuid4().hex,
                    assignment_material_item_id=link["id"],
                    **{target_column: mapping[target_column]},
                    weight=mapping["weight"],
                    confidence=mapping["confidence"],
                    is_primary=mapping["is_primary"],
                ))
        option_source = tables["teacher_material_item_options"]
        option_snapshot = tables["assignment_material_item_options"]
        options = connection.execute(
            sa.select(option_source).where(
                option_source.c.item_id == link["teacher_material_item_id"]
            )
        ).mappings()
        for option in options:
            connection.execute(option_snapshot.insert().values(
                id=uuid4().hex,
                assignment_material_item_id=link["id"],
                label=option["label"],
                content=option["content"],
                order_index=option["order_index"],
            ))

    student_items = tables["student_assignment_material_items"]
    student_assignments = tables["student_assignments"]
    existing_student_items = list(connection.execute(sa.select(student_items)).mappings())
    # Move material display orders out of the way before applying the canonical offset.
    for index, item in enumerate(existing_student_items):
        connection.execute(
            student_items.update().where(student_items.c.id == item["id"]).values(
                order_index=-(index + 1)
            )
        )
    for item in existing_student_items:
        assignment_id = connection.execute(
            sa.select(student_assignments.c.assignment_id).where(
                student_assignments.c.id == item["student_assignment_id"]
            )
        ).scalar_one()
        snapshot_id = snapshot_by_assignment_source.get(
            (assignment_id, item["teacher_material_item_id"])
        )
        if snapshot_id is None:
            raise RuntimeError("Existing student material item has no assignment link")
        canonical_count = connection.execute(
            sa.select(sa.func.count()).select_from(
                tables["assignment_student_questions"]
            ).where(
                tables["assignment_student_questions"].c.student_assignment_id
                == item["student_assignment_id"]
            )
        ).scalar_one()
        local_order = connection.execute(
            sa.select(links.c.order_index).where(links.c.id == snapshot_id)
        ).scalar_one()
        connection.execute(
            student_items.update().where(student_items.c.id == item["id"]).values(
                assignment_material_item_id=snapshot_id,
                order_index=canonical_count + local_order,
            )
        )


    with op.batch_alter_table("student_assignment_material_items") as batch:
        batch.alter_column(
            "assignment_material_item_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("student_assignment_material_items") as batch:
        batch.drop_constraint("uq_student_assignment_material_snapshot", type_="unique")
        batch.drop_constraint("fk_student_assignment_material_items_graded_by", type_="foreignkey")
        batch.drop_constraint("fk_student_assignment_material_items_snapshot", type_="foreignkey")
        for column in (
            "teacher_feedback", "graded_at", "graded_by", "assignment_material_item_id",
        ):
            batch.drop_column(column)
    for name in (
        "assignment_material_item_learning_outcomes",
        "assignment_material_item_problem_types",
        "assignment_material_item_concepts",
        "assignment_material_item_options",
    ):
        op.drop_table(name)
    with op.batch_alter_table("assignment_material_items") as batch:
        batch.drop_constraint("fk_assignment_material_items_teacher_material_id", type_="foreignkey")
        for column in (
            "snapshotted_at", "evaluation_mode", "difficulty", "explanation",
            "correct_answer", "question_type", "content",
            "source_content_hash", "teacher_material_id",
        ):
            batch.drop_column(column)
