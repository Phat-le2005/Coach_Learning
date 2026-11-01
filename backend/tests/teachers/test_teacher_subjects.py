from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.subjects.models import Subject
from app.users.models import Role, User
from tests.classes.conftest import classroom_bearer, classroom_user_factory


def test_teacher_subject_catalog_is_real_and_role_protected(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    classroom_bearer: Callable[[User], dict[str, str]],
) -> None:
    path = "/api/v2/teacher/subjects"
    assert db_client.get(path).status_code == 401
    teacher = classroom_user_factory(Role.TEACHER, "subject-teacher@example.com")
    student = classroom_user_factory(Role.STUDENT, "subject-student@example.com")
    db_session.add_all([
        Subject(code="TEACHER-MATH-12", name="Math 12", grade_level=12, order_index=1),
        Subject(code="TEACHER-MATH-11", name="Math 11", grade_level=11, order_index=0),
    ])
    db_session.commit()
    assert db_client.get(path, headers=classroom_bearer(student)).status_code == 403
    response = db_client.get(path, headers=classroom_bearer(teacher))
    assert response.status_code == 200
    assert [(row["code"], row["grade_level"]) for row in response.json()] == [
        ("TEACHER-MATH-11", 11),
        ("TEACHER-MATH-12", 12),
    ]