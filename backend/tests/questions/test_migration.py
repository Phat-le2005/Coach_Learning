from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.questions.models import Question, QuestionConcept, QuestionStatus, QuestionType
from app.subjects.models import Subject
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService
from tests.migrations import load_migration


def test_question_revision_downgrade_preserves_previous_tables(db_engine: Engine) -> None:
    migration = load_migration("0006_question_bank")
    with db_engine.begin() as connection:
        before = set(inspect(connection).get_table_names())
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert set(inspect(connection).get_table_names()) == before - {
                "questions", "question_options", "question_concepts"
            }
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == before


@pytest.mark.parametrize("field,value", [
    ("difficulty", -0.1), ("difficulty", 1.1),
    ("exam_weight", -0.1), ("exam_weight", 1.1),
    ("content", " "), ("source_type", " "),
])
def test_database_enforces_question_constraints(
    db_session: Session, field: str, value: object
) -> None:
    teacher = UserService(db_session).create_user(UserCreate(
        email=f"constraint-{uuid4().hex}@example.com",
        password="Synthetic-Question-Migration-Password-2026!",
        full_name="Teacher",
        role=Role.TEACHER,
    ))
    subject = Subject(code=f"M-{uuid4().hex[:8].upper()}", name="Mathematics", grade_level=12)
    db_session.add(subject)
    db_session.flush()
    values = {
        "subject_id": subject.id,
        "content": "Valid question",
        "question_type": QuestionType.TRUE_FALSE,
        "difficulty": 0.5,
        "correct_answer": "TRUE",
        "source_type": "TEACHER",
        "exam_weight": 0.5,
        "status": QuestionStatus.DRAFT,
        "created_by": teacher.id,
        field: value,
    }
    db_session.add(Question(**values))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_database_enforces_concept_weight_and_foreign_keys(db_session: Session) -> None:
    teacher = UserService(db_session).create_user(UserCreate(
        email="question-fk@example.com",
        password="Synthetic-Question-Migration-Password-2026!",
        full_name="Teacher",
        role=Role.TEACHER,
    ))
    subject = Subject(code="QUESTION-FK", name="Mathematics", grade_level=12)
    db_session.add(subject)
    db_session.flush()
    concept = Concept(
        subject_id=subject.id, code="QUESTION-FK-C", name="Concept",
        description="Concept description", grade_level=12, order_index=0,
    )
    question = Question(
        subject_id=subject.id, content="Valid question", question_type=QuestionType.OPEN_RESPONSE,
        difficulty=0.5, source_type="TEACHER", exam_weight=0.5, created_by=teacher.id,
    )
    db_session.add_all([concept, question])
    db_session.commit()
    db_session.add(QuestionConcept(question_id=question.id, concept_id=concept.id, weight=0.0))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    db_session.add(QuestionConcept(question_id=question.id, concept_id=uuid4(), weight=0.5))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
