"""Optional PostgreSQL concurrency coverage for classroom enrollment."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.classes.models import StudentEnrollment
from app.classes.schemas import ClassroomCreate, StudentEnrollmentCreate
from app.classes.service import ClassroomService
from app.core.exceptions import ApplicationError
from app.students.models import StudentProfile
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService


def test_concurrent_duplicate_enrollment_creates_one_row(postgres_engine: Engine) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False, autoflush=False)
    password = "Synthetic-PostgreSQL-Classroom-Test-2026!"
    with factory() as session:
        teacher = UserService(session).create_user(UserCreate(
            email="teacher@example.com", password=password, full_name="Teacher", role=Role.TEACHER
        ))
        student = UserService(session).create_user(UserCreate(
            email="student@example.com", password=password, full_name="Student", role=Role.STUDENT
        ))
        student_profile = session.scalar(select(StudentProfile).where(StudentProfile.user_id == student.id))
        assert student_profile is not None
        classroom = ClassroomService(session).create_for_teacher(
            teacher.id,
            ClassroomCreate(name="Concurrent enrollment", academic_year="2026-2027", grade_level=12),
        )
        teacher_id, student_id, classroom_id = teacher.id, student_profile.id, classroom.id
    barrier = Barrier(2)

    def enroll() -> tuple[int, str]:
        with factory() as session:
            barrier.wait(timeout=10)
            try:
                ClassroomService(session).enroll_student(
                    teacher_id, classroom_id, StudentEnrollmentCreate(student_id=student_id)
                )
                return 201, "CREATED"
            except ApplicationError as error:
                session.rollback()
                return error.status_code, error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(enroll), pool.submit(enroll)]
        assert sorted(result.result(timeout=20) for result in results) == [
            (201, "CREATED"),
            (409, "STUDENT_ALREADY_ENROLLED"),
        ]
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(StudentEnrollment)) == 1
