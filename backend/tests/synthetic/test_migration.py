from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.attempts.models import StudentAttempt, StudySession
from app.concepts.models import Concept
from app.students.models import StudentProfile, SyntheticProfile
from app.subjects.models import Subject
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService
from tests.migrations import load_migration


def test_synthetic_revision_downgrade_preserves_previous_tables(db_engine: Engine) -> None:
    migration = load_migration("0008_synthetic_students")
    with db_engine.begin() as connection:
        before = set(inspect(connection).get_table_names())
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert set(inspect(connection).get_table_names()) == before - {
                "study_sessions", "student_attempts"
            }
            columns = {column["name"] for column in inspect(connection).get_columns("student_profiles")}
            assert "is_synthetic" not in columns and "synthetic_profile" not in columns
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == before


def test_database_enforces_synthetic_profile_consistency(db_session: Session) -> None:
    user = UserService(db_session).create_user(UserCreate(
        email="real-student@example.com",
        password="Synthetic-Migration-Password-2026!",
        full_name="Real Student",
        role=Role.STUDENT,
    ))
    profile = db_session.query(StudentProfile).filter_by(user_id=user.id).one()
    profile.synthetic_profile = SyntheticProfile.STRONG
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_database_enforces_attempt_and_session_ranges(db_session: Session) -> None:
    user = UserService(db_session).create_user(UserCreate(
        email="attempt-student@example.com",
        password="Synthetic-Migration-Password-2026!",
        full_name="Attempt Student",
        role=Role.STUDENT,
    ))
    profile = db_session.query(StudentProfile).filter_by(user_id=user.id).one()
    subject = Subject(code="ATTEMPT-MATH", name="Attempt Math", grade_level=12)
    db_session.add(subject)
    db_session.flush()
    concept = Concept(
        subject_id=subject.id,
        code="ATTEMPT-CONCEPT",
        name="Attempt Concept",
        description="Attempt concept",
        grade_level=12,
        order_index=0,
    )
    db_session.add(concept)
    db_session.commit()
    now = datetime.now(UTC)
    db_session.add(StudySession(
        student_id=profile.id,
        started_at=now,
        ended_at=now - timedelta(minutes=1),
        is_synthetic=True,
    ))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    db_session.add(StudentAttempt(
        id=uuid4(),
        student_id=profile.id,
        concept_id=concept.id,
        is_correct=True,
        response_time_ms=0,
        attempted_at=now,
        is_synthetic=True,
    ))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
