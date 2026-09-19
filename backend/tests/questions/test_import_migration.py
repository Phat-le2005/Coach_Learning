from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.questions.models import (
    ImportFileFormat,
    ImportRowStatus,
    QuestionImportBatch,
    QuestionImportRow,
)
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
