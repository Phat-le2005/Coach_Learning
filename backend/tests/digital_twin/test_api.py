from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classes.models import Classroom, StudentEnrollment, TeacherClassroom
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from tests.practice.conftest import PracticeContent

BearerFactory = Callable[[User], dict[str, str]]
UserFactory = Callable[[Role, str], User]


def test_student_and_related_teacher_can_read_twin_but_unrelated_teacher_cannot(
    db_client: TestClient,
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory: UserFactory,
    practice_bearer: BearerFactory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    profile = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    )
    assert profile is not None
    own = db_client.get(
        "/students/me/digital-twin", headers=practice_bearer(student)
    )
    assert own.status_code == 200, own.text
    assert own.headers["cache-control"] == "no-store"
    assert own.json()["basic_profile"]["student_id"] == str(profile.id)

    teacher = practice_user_factory(Role.TEACHER, "digital-twin-teacher@example.com")
    unrelated = practice_user_factory(Role.TEACHER, "digital-twin-unrelated@example.com")
    teacher_profile = db_session.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == teacher.id)
    )
    assert teacher_profile is not None
    classroom = Classroom(
        name="Digital Twin Classroom",
        academic_year="2026-2027",
        grade_level=12,
        created_by=teacher.id,
    )
    db_session.add(classroom)
    db_session.flush()
    db_session.add_all(
        [
            TeacherClassroom(
                teacher_id=teacher_profile.id,
                classroom_id=classroom.id,
                role="OWNER",
            ),
            StudentEnrollment(student_id=profile.id, classroom_id=classroom.id),
        ]
    )
    db_session.commit()

    allowed = db_client.get(
        f"/teacher/students/{profile.id}/digital-twin",
        headers=practice_bearer(teacher),
    )
    assert allowed.status_code == 200, allowed.text
    denied = db_client.get(
        f"/teacher/students/{profile.id}/digital-twin",
        headers=practice_bearer(unrelated),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "STUDENT_ACCESS_DENIED"

