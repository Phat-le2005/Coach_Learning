from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile
from app.users.models import Role, User

UserFactory = Callable[[Role, str], User]
BearerFactory = Callable[[User], dict[str, str]]
TeacherProfileFactory = Callable[[User], TeacherProfile]
StudentProfileFactory = Callable[[User], StudentProfile]


def classroom_payload(name: str = "12A1") -> dict[str, object]:
    return {"name": name, "academic_year": "2026-2027", "grade_level": 12}


def create_classroom(client: TestClient, headers: dict[str, str], name: str = "12A1") -> dict[str, object]:
    response = client.post("/teacher/classes", json=classroom_payload(name), headers=headers)
    assert response.status_code == 201
    return response.json()


def test_teacher_creates_classroom_and_owner_assignment_atomically(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: UserFactory,
    classroom_bearer: BearerFactory,
    teacher_profile: TeacherProfileFactory,
) -> None:
    teacher = classroom_user_factory(Role.TEACHER, "creator@example.com")
    created = create_classroom(db_client, classroom_bearer(teacher))
    assert created["name"] == "12A1"
    assert created["academic_year"] == "2026-2027"
    assert created["grade_level"] == 12
    assert created["created_by"] == str(teacher.id)
    assert created["teacher_role"] == "OWNER"
    assert UUID(created["id"]) and created["created_at"]
    db_session.expire_all()
    classroom = db_session.get(Classroom, UUID(created["id"]))
    assert classroom is not None and classroom.created_by == teacher.id
    assignment = db_session.get(TeacherClassroom, (teacher_profile(teacher).id, classroom.id))
    assert assignment is not None and assignment.role == "OWNER"


def test_teacher_lists_and_gets_only_assigned_classrooms(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: UserFactory,
    classroom_bearer: BearerFactory,
    teacher_profile: TeacherProfileFactory,
) -> None:
    first = classroom_user_factory(Role.TEACHER, "first-teacher@example.com")
    second = classroom_user_factory(Role.TEACHER, "second-teacher@example.com")
    first_headers, second_headers = classroom_bearer(first), classroom_bearer(second)
    first_class = create_classroom(db_client, first_headers, "Class A")
    second_class = create_classroom(db_client, second_headers, "Class B")
    shared_class = create_classroom(db_client, first_headers, "Shared")
    db_session.add(TeacherClassroom(
        teacher_id=teacher_profile(second).id,
        classroom_id=UUID(shared_class["id"]),
        role="ASSISTANT",
    ))
    db_session.commit()
    assert {item["id"] for item in db_client.get("/teacher/classes", headers=first_headers).json()} == {
        first_class["id"], shared_class["id"]
    }
    second_list = db_client.get("/teacher/classes", headers=second_headers).json()
    assert {item["id"] for item in second_list} == {second_class["id"], shared_class["id"]}
    assert next(item for item in second_list if item["id"] == shared_class["id"])["teacher_role"] == "ASSISTANT"
    assert db_client.get(f"/teacher/classes/{shared_class['id']}", headers=second_headers).status_code == 200
    denied = db_client.get(f"/teacher/classes/{first_class['id']}", headers=second_headers)
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "CLASSROOM_ACCESS_DENIED"
    missing = db_client.get(f"/teacher/classes/{uuid4()}", headers=second_headers)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "CLASSROOM_NOT_FOUND"


def test_created_by_alone_never_grants_classroom_access(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: UserFactory,
    classroom_bearer: BearerFactory,
    teacher_profile: TeacherProfileFactory,
) -> None:
    creator = classroom_user_factory(Role.TEACHER, "audit-creator@example.com")
    assigned = classroom_user_factory(Role.TEACHER, "assigned@example.com")
    classroom = Classroom(name="Relationship only", academic_year="2026-2027", grade_level=12, created_by=creator.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=teacher_profile(assigned).id, classroom_id=classroom.id, role="TEACHER"))
    db_session.commit()
    creator_headers, assigned_headers = classroom_bearer(creator), classroom_bearer(assigned)
    for suffix in ["", "/students"]:
        denied = db_client.get(f"/teacher/classes/{classroom.id}{suffix}", headers=creator_headers)
        assert denied.status_code == 403 and denied.json()["error"]["code"] == "CLASSROOM_ACCESS_DENIED"
    enrollment = db_client.post(
        f"/teacher/classes/{classroom.id}/students",
        json={"student_id": str(uuid4())},
        headers=creator_headers,
    )
    assert enrollment.status_code == 403
    assert db_client.get(f"/teacher/classes/{classroom.id}", headers=assigned_headers).status_code == 200


def test_teacher_enrolls_student_and_reads_roster(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: UserFactory,
    classroom_bearer: BearerFactory,
    student_profile: StudentProfileFactory,
) -> None:
    teacher = classroom_user_factory(Role.TEACHER, "teacher@example.com")
    student = classroom_user_factory(Role.STUDENT, "student@example.com")
    student_profile_value = student_profile(student)
    student_profile_value.school_name = "THPT Test"
    db_session.commit()
    headers = classroom_bearer(teacher)
    classroom = create_classroom(db_client, headers)
    enrolled = db_client.post(
        f"/teacher/classes/{classroom['id']}/students",
        json={"student_id": str(student_profile_value.id)},
        headers=headers,
    )
    assert enrolled.status_code == 201
    assert enrolled.json() == {
        "student_id": str(student_profile_value.id),
        "user_id": str(student.id),
        "email": student.email,
        "full_name": student.full_name,
        "grade_level": 12,
        "school_name": "THPT Test",
        "date_of_birth": None,
        "is_synthetic": False,
        "synthetic_profile": None,
        "status": "ACTIVE",
        "joined_at": enrolled.json()["joined_at"],
    }
    roster = db_client.get(f"/teacher/classes/{classroom['id']}/students", headers=headers)
    assert roster.status_code == 200 and roster.json() == [enrolled.json()]
    db_session.expire_all()
    stored = db_session.get(StudentEnrollment, (student_profile_value.id, UUID(classroom["id"])))
    assert stored is not None and stored.status == EnrollmentStatus.ACTIVE


@pytest.mark.parametrize("status", list(EnrollmentStatus))
def test_student_sees_only_enrolled_classes_with_status(
    db_client: TestClient,
    classroom_user_factory: UserFactory,
    classroom_bearer: BearerFactory,
    student_profile: StudentProfileFactory,
    status: EnrollmentStatus,
) -> None:
    teacher = classroom_user_factory(Role.TEACHER, "teacher@example.com")
    student = classroom_user_factory(Role.STUDENT, "student@example.com")
    other = classroom_user_factory(Role.STUDENT, "other@example.com")
    teacher_headers = classroom_bearer(teacher)
    expected = create_classroom(db_client, teacher_headers, "Enrolled")
    create_classroom(db_client, teacher_headers, "Not enrolled")
    response = db_client.post(
        f"/teacher/classes/{expected['id']}/students",
        json={"student_id": str(student_profile(student).id), "status": status.value},
        headers=teacher_headers,
    )
    assert response.status_code == 201
    own = db_client.get("/students/me/classes", headers=classroom_bearer(student))
    assert own.status_code == 200 and len(own.json()) == 1
    assert own.json()[0]["id"] == expected["id"]
    assert own.json()[0]["enrollment_status"] == status.value
    assert own.json()[0]["joined_at"] == response.json()["joined_at"]
    assert db_client.get("/students/me/classes", headers=classroom_bearer(other)).json() == []


def test_duplicate_and_missing_student_enrollment_errors_are_stable(
    db_client: TestClient,
    classroom_user_factory: UserFactory,
    classroom_bearer: BearerFactory,
    student_profile: StudentProfileFactory,
) -> None:
    teacher = classroom_user_factory(Role.TEACHER, "teacher@example.com")
    student = classroom_user_factory(Role.STUDENT, "student@example.com")
    headers = classroom_bearer(teacher)
    classroom = create_classroom(db_client, headers)
    payload = {"student_id": str(student_profile(student).id)}
    assert db_client.post(f"/teacher/classes/{classroom['id']}/students", json=payload, headers=headers).status_code == 201
    duplicate = db_client.post(f"/teacher/classes/{classroom['id']}/students", json=payload, headers=headers)
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "STUDENT_ALREADY_ENROLLED"
    missing = db_client.post(
        f"/teacher/classes/{classroom['id']}/students",
        json={"student_id": str(uuid4())},
        headers=headers,
    )
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "STUDENT_NOT_FOUND"


@pytest.mark.parametrize("payload", [
    {"name": "", "academic_year": "2026-2027", "grade_level": 12},
    {"name": "  ", "academic_year": "2026-2027", "grade_level": 12},
    {"name": "X" * 201, "academic_year": "2026-2027", "grade_level": 12},
    {"name": "12A1", "academic_year": " ", "grade_level": 12},
    {"name": "12A1", "academic_year": "X" * 21, "grade_level": 12},
    {"name": "12A1", "academic_year": "2026-2027", "grade_level": 0},
    {"name": "12A1", "academic_year": "2026-2027", "grade_level": 13},
    {"name": "12A1", "academic_year": "2026-2027", "grade_level": "12"},
    {"name": "12A1", "academic_year": "2026-2027", "grade_level": True},
    {"name": "12A1", "academic_year": "2026-2027", "grade_level": 12, "created_by": str(uuid4())},
])
def test_classroom_create_validation(
    db_client: TestClient,
    classroom_user_factory: UserFactory,
    classroom_bearer: BearerFactory,
    payload: dict[str, object],
) -> None:
    teacher = classroom_user_factory(Role.TEACHER, "teacher@example.com")
    response = db_client.post("/teacher/classes", json=payload, headers=classroom_bearer(teacher))
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("payload", [
    {}, {"student_id": "invalid"}, {"student_id": None},
    {"student_id": str(uuid4()), "status": "UNKNOWN"},
    {"student_id": str(uuid4()), "status": None},
    {"student_id": str(uuid4()), "status": "ACTIVE", "joined_at": "2020-01-01T00:00:00Z"},
])
def test_enrollment_validation(
    db_client: TestClient,
    classroom_user_factory: UserFactory,
    classroom_bearer: BearerFactory,
    payload: dict[str, object],
) -> None:
    teacher = classroom_user_factory(Role.TEACHER, "teacher@example.com")
    headers = classroom_bearer(teacher)
    classroom = create_classroom(db_client, headers)
    response = db_client.post(f"/teacher/classes/{classroom['id']}/students", json=payload, headers=headers)
    assert response.status_code == 422


@pytest.mark.parametrize("role", [Role.STUDENT, Role.PARENT, Role.ADMIN])
def test_teacher_classroom_apis_reject_other_roles(
    db_client: TestClient,
    classroom_user_factory: UserFactory,
    classroom_bearer: BearerFactory,
    role: Role,
) -> None:
    headers = classroom_bearer(classroom_user_factory(role, f"{role.value.lower()}@example.com"))
    classroom_id = str(uuid4())
    responses = [
        db_client.post("/teacher/classes", json=classroom_payload(), headers=headers),
        db_client.get("/teacher/classes", headers=headers),
        db_client.get(f"/teacher/classes/{classroom_id}", headers=headers),
        db_client.get(f"/teacher/classes/{classroom_id}/students", headers=headers),
        db_client.post(
            f"/teacher/classes/{classroom_id}/students",
            json={"student_id": str(uuid4())},
            headers=headers,
        ),
    ]
    assert all(response.status_code == 403 for response in responses)


@pytest.mark.parametrize("role", [Role.TEACHER, Role.PARENT, Role.ADMIN])
def test_student_classroom_api_rejects_other_roles(
    db_client: TestClient,
    classroom_user_factory: UserFactory,
    classroom_bearer: BearerFactory,
    role: Role,
) -> None:
    user = classroom_user_factory(role, f"{role.value.lower()}@example.com")
    assert db_client.get("/students/me/classes", headers=classroom_bearer(user)).status_code == 403


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid-token"}])
def test_all_classroom_apis_require_authentication(db_client: TestClient, headers: dict[str, str]) -> None:
    classroom_id = str(uuid4())
    responses = [
        db_client.post("/teacher/classes", json=classroom_payload(), headers=headers),
        db_client.get("/teacher/classes", headers=headers),
        db_client.get(f"/teacher/classes/{classroom_id}", headers=headers),
        db_client.get(f"/teacher/classes/{classroom_id}/students", headers=headers),
        db_client.post(
            f"/teacher/classes/{classroom_id}/students",
            json={"student_id": str(uuid4())},
            headers=headers,
        ),
        db_client.get("/students/me/classes", headers=headers),
    ]
    assert all(response.status_code == 401 for response in responses)


def test_unassigned_teacher_cannot_read_roster_or_enroll(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: UserFactory,
    classroom_bearer: BearerFactory,
    student_profile: StudentProfileFactory,
) -> None:
    owner = classroom_user_factory(Role.TEACHER, "owner@example.com")
    outsider = classroom_user_factory(Role.TEACHER, "outsider@example.com")
    student = classroom_user_factory(Role.STUDENT, "student@example.com")
    classroom = create_classroom(db_client, classroom_bearer(owner))
    outsider_headers = classroom_bearer(outsider)
    assert db_client.get(f"/teacher/classes/{classroom['id']}/students", headers=outsider_headers).status_code == 403
    response = db_client.post(
        f"/teacher/classes/{classroom['id']}/students",
        json={"student_id": str(student_profile(student).id)},
        headers=outsider_headers,
    )
    assert response.status_code == 403 and response.json()["error"]["code"] == "CLASSROOM_ACCESS_DENIED"
    assert db_session.scalar(select(func.count()).select_from(StudentEnrollment)) == 0


def test_missing_role_profile_returns_404_without_creating_data(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: UserFactory,
    classroom_bearer: BearerFactory,
) -> None:
    teacher = classroom_user_factory(Role.TEACHER, "teacher@example.com")
    teacher_headers = classroom_bearer(teacher)
    db_session.execute(delete(TeacherProfile).where(TeacherProfile.user_id == teacher.id))
    db_session.commit()
    response = db_client.post("/teacher/classes", json=classroom_payload(), headers=teacher_headers)
    assert response.status_code == 404 and response.json()["error"]["code"] == "PROFILE_NOT_FOUND"
    assert db_session.scalar(select(func.count()).select_from(Classroom)) == 0
    student = classroom_user_factory(Role.STUDENT, "student@example.com")
    student_headers = classroom_bearer(student)
    db_session.execute(delete(StudentProfile).where(StudentProfile.user_id == student.id))
    db_session.commit()
    response = db_client.get("/students/me/classes", headers=student_headers)
    assert response.status_code == 404 and response.json()["error"]["code"] == "PROFILE_NOT_FOUND"
