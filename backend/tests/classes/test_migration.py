from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService
from tests.migrations import load_migration


def test_classroom_revision_downgrade_preserves_previous_tables(db_engine: Engine) -> None:
    migration = load_migration("0005_classrooms")
    with db_engine.begin() as connection:
        before = set(inspect(connection).get_table_names())
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert set(inspect(connection).get_table_names()) == before - {
                "classrooms", "teacher_classrooms", "student_enrollments"
            }
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == before


@pytest.mark.parametrize("kind,updates", [
    ("classroom", {"name": " "}),
    ("classroom", {"academic_year": " "}),
    ("classroom", {"grade_level": 0}),
    ("classroom", {"grade_level": 13}),
    ("classroom", {"created_by": uuid4()}),
    ("teacher", {"teacher_id": uuid4()}),
    ("teacher", {"classroom_id": uuid4()}),
    ("teacher", {"role": " "}),
    ("student", {"student_id": uuid4()}),
    ("student", {"classroom_id": uuid4()}),
    ("student", {"status": "UNKNOWN"}),
])
def test_database_enforces_classroom_constraints(
    db_session: Session, kind: str, updates: dict[str, object]
) -> None:
    password = "Synthetic-Migration-Test-Password-2026!"
    teacher_user = UserService(db_session).create_user(UserCreate(
        email="teacher@example.com", password=password, full_name="Teacher", role=Role.TEACHER
    ))
    student_user = UserService(db_session).create_user(UserCreate(
        email="student@example.com", password=password, full_name="Student", role=Role.STUDENT
    ))
    teacher = db_session.query(TeacherProfile).filter_by(user_id=teacher_user.id).one()
    student = db_session.query(StudentProfile).filter_by(user_id=student_user.id).one()
    classroom = Classroom(
        name="Classroom", academic_year="2026-2027", grade_level=12, created_by=teacher_user.id
    )
    db_session.add(classroom)
    db_session.commit()
    if kind == "classroom":
        entity = Classroom(**{
            "name": "Other", "academic_year": "2026-2027", "grade_level": 12,
            "created_by": teacher_user.id, **updates,
        })
    elif kind == "teacher":
        entity = TeacherClassroom(**{
            "teacher_id": teacher.id, "classroom_id": classroom.id, "role": "OWNER", **updates,
        })
    else:
        entity = StudentEnrollment(**{
            "student_id": student.id, "classroom_id": classroom.id,
            "status": EnrollmentStatus.ACTIVE, **updates,
        })
    db_session.add(entity)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_database_rejects_duplicate_assignments_and_enrollments(db_session: Session) -> None:
    password = "Synthetic-Migration-Test-Password-2026!"
    teacher_user = UserService(db_session).create_user(UserCreate(
        email="teacher@example.com", password=password, full_name="Teacher", role=Role.TEACHER
    ))
    student_user = UserService(db_session).create_user(UserCreate(
        email="student@example.com", password=password, full_name="Student", role=Role.STUDENT
    ))
    teacher = db_session.query(TeacherProfile).filter_by(user_id=teacher_user.id).one()
    student = db_session.query(StudentProfile).filter_by(user_id=student_user.id).one()
    classroom = Classroom(name="Classroom", academic_year="2026-2027", grade_level=12, created_by=teacher_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add_all([
        TeacherClassroom(teacher_id=teacher.id, classroom_id=classroom.id, role="OWNER"),
        StudentEnrollment(student_id=student.id, classroom_id=classroom.id),
    ])
    db_session.commit()
    for duplicate in [
        TeacherClassroom(teacher_id=teacher.id, classroom_id=classroom.id, role="ASSISTANT"),
        StudentEnrollment(student_id=student.id, classroom_id=classroom.id),
    ]:
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
