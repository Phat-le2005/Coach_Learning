from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.questions.models import (
    ImportFileFormat,
    ImportRowStatus,
    QuestionImportBatch,
    QuestionImportRow,
    Question,
    QuestionStatus,
    QuestionType,
)
from app.questions.fingerprint import question_content_hash
from app.subjects.models import Subject
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService
from tests.migrations import load_migration


def test_import_revision_downgrade_preserves_question_bank_tables(db_engine: Engine) -> None:
    migration = load_migration("0007_question_import")
    with db_engine.begin() as connection:
        before = set(inspect(connection).get_table_names())
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert set(inspect(connection).get_table_names()) == before - {
                "question_import_batches", "question_import_rows"
            }
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == before


@pytest.mark.parametrize(
    "row_number,content_hash",
    [(0, "a" * 64), (1, "short")],
)
def test_database_enforces_staging_row_constraints(
    db_session: Session, row_number: int, content_hash: str
) -> None:
    teacher = UserService(db_session).create_user(UserCreate(
        email=f"staging-{uuid4()}@example.com",
        password="Synthetic-Import-Migration-Password-2026!",
        full_name="Teacher",
        role=Role.TEACHER,
    ))
    batch = QuestionImportBatch(
        created_by=teacher.id,
        file_name="questions.json",
        file_format=ImportFileFormat.JSON,
    )
    batch.rows.append(QuestionImportRow(
        row_number=row_number,
        status=ImportRowStatus.VALID,
        raw_data={"content": "Question"},
        content_hash=content_hash,
        errors=[],
    ))
    db_session.add(batch)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_content_hash_revision_backfills_existing_questions_and_adds_index(
    db_session: Session, db_engine: Engine
) -> None:
    teacher = UserService(db_session).create_user(
        UserCreate(
            email="content-hash-migration@example.com",
            password="Synthetic-Import-Migration-Password-2026!",
            full_name="Content Hash Teacher",
            role=Role.TEACHER,
        )
    )
    subject = Subject(code="HASH-MIGRATION", name="Hash migration", grade_level=12)
    db_session.add(subject)
    db_session.flush()
    question = Question(
        subject_id=subject.id,
        content="  Normalized   CONTENT  ",
        question_type=QuestionType.TRUE_FALSE,
        difficulty=0.5,
        correct_answer="TRUE",
        source_type="TEST",
        exam_weight=0.5,
        status=QuestionStatus.DRAFT,
        created_by=teacher.id,
    )
    db_session.add(question)
    db_session.commit()
    question_id = question.id
    expected = question_content_hash(question.content)
    db_session.close()

    migration = load_migration("0012_question_content_hash")
    with db_engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert "content_hash" not in {
                column["name"] for column in inspect(connection).get_columns("questions")
            }
            migration.upgrade()
        columns = {column["name"]: column for column in inspect(connection).get_columns("questions")}
        indexes = {index["name"] for index in inspect(connection).get_indexes("questions")}
        stored_hash = connection.scalar(
            select(Question.__table__.c.content_hash).where(Question.__table__.c.id == question_id)
        )

    assert columns["content_hash"]["nullable"] is False
    assert "ix_questions_content_hash" in indexes
    assert stored_hash == expected
