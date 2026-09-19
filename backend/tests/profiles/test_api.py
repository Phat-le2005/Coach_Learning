from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth.security import as_utc
from app.parents.models import ParentProfile
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from tests.profiles.conftest import PROFILE_TEST_PASSWORD

PROFILE_DOMAINS = [
    (Role.STUDENT, "/students/me", StudentProfile),
    (Role.TEACHER, "/teachers/me", TeacherProfile),
    (Role.PARENT, "/parents/me", ParentProfile),
]


@pytest.mark.parametrize("role", list(Role))
def test_profile_api_role_matrix(
    db_client: TestClient,
    profile_user_factory: Callable[[Role, str], User],
    profile_bearer: Callable[[User], dict[str, str]],
    role: Role,
) -> None:
    user = profile_user_factory(role, f"{role.value.lower()}@example.com")
    headers = profile_bearer(user)
    for required, path, model in PROFILE_DOMAINS:
        for response in [db_client.get(path, headers=headers), db_client.patch(path, json={}, headers=headers)]:
            assert response.status_code == (200 if role == required else 403)
            if role == required:
                assert response.json()["user_id"] == str(user.id)
                assert UUID(response.json()["id"])
                assert response.headers["cache-control"] == "no-store"
                assert not {"password", "password_hash", "email", "role"}.intersection(response.json())
            else:
                assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("path", ["/students/me", "/teachers/me", "/parents/me"])
def test_profile_apis_require_valid_authentication(db_client: TestClient, path: str) -> None:
    for headers in [{}, {"Authorization": "Bearer invalid-token"}]:
        assert db_client.get(path, headers=headers).status_code == 401
        assert db_client.patch(path, json={}, headers=headers).status_code == 401


def test_registration_provisions_student_profile(db_client: TestClient) -> None:
    registration = {"email": "newstudent@example.com", "password": PROFILE_TEST_PASSWORD, "full_name": "New Student"}
    registered = db_client.post("/auth/register", json=registration)
    assert registered.status_code == 201
    login = db_client.post("/auth/login", json={"email": registration["email"], "password": registration["password"]})
    response = db_client.get("/students/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert response.status_code == 200
    assert response.json()["user_id"] == registered.json()["id"]
    assert response.json()["grade_level"] == 12
    assert response.json()["school_name"] is None and response.json()["date_of_birth"] is None


def test_student_partial_update_and_explicit_null(
    db_client: TestClient, db_session: Session,
    profile_user_factory: Callable[[Role, str], User], profile_bearer: Callable[[User], dict[str, str]],
) -> None:
    user = profile_user_factory(Role.STUDENT, "student@example.com")
    headers = profile_bearer(user)
    original = db_client.get("/students/me", headers=headers).json()
    updated = db_client.patch(
        "/students/me", headers=headers,
        json={"grade_level": 11, "school_name": "  THPT Nguyễn Trãi  ", "date_of_birth": "2008-06-15"},
    )
    assert updated.status_code == 200
    assert updated.json()["school_name"] == "THPT Nguyễn Trãi"
    assert updated.json()["date_of_birth"] == "2008-06-15"
    partial = db_client.patch("/students/me", json={"school_name": "THPT Lê Lợi"}, headers=headers)
    assert partial.json()["grade_level"] == 11 and partial.json()["date_of_birth"] == "2008-06-15"
    cleared = db_client.patch("/students/me", json={"school_name": None, "date_of_birth": None}, headers=headers)
    assert cleared.status_code == 200
    assert cleared.json()["school_name"] is None and cleared.json()["date_of_birth"] is None
    assert cleared.json()["created_at"] == original["created_at"] and cleared.json()["id"] == original["id"]
    db_session.expire_all()
    stored = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    assert stored is not None and stored.grade_level == 11 and stored.school_name is None
    assert db_client.get("/students/me", headers=headers).json() == cleared.json()


@pytest.mark.parametrize(
    "updates",
    [
        {"grade_level": None}, {"grade_level": 0}, {"grade_level": 13}, {"grade_level": 1.5},
        {"grade_level": True}, {"grade_level": "12"}, {"school_name": " "}, {"school_name": "x" * 201},
        {"date_of_birth": "invalid-date"}, {"date_of_birth": (date.today() + timedelta(days=2)).isoformat()},
    ],
)
def test_student_validation(
    db_client: TestClient, profile_user_factory: Callable[[Role, str], User],
    profile_bearer: Callable[[User], dict[str, str]], updates: dict[str, object],
) -> None:
    user = profile_user_factory(Role.STUDENT, "student@example.com")
    headers = profile_bearer(user)
    response = db_client.patch("/students/me", json=updates, headers=headers)
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert db_client.get("/students/me", headers=headers).json()["grade_level"] == 12


def test_teacher_specialization_update_clear_and_noop(
    db_client: TestClient, profile_user_factory: Callable[[Role, str], User],
    profile_bearer: Callable[[User], dict[str, str]],
) -> None:
    user = profile_user_factory(Role.TEACHER, "teacher@example.com")
    headers = profile_bearer(user)
    updated = db_client.patch("/teachers/me", json={"specialization": "  Toán học  "}, headers=headers)
    assert updated.status_code == 200 and updated.json()["specialization"] == "Toán học"
    assert db_client.patch("/teachers/me", json={}, headers=headers).json() == updated.json()
    cleared = db_client.patch("/teachers/me", json={"specialization": None}, headers=headers)
    assert cleared.status_code == 200 and cleared.json()["specialization"] is None
    assert db_client.get("/teachers/me", headers=headers).json() == cleared.json()


@pytest.mark.parametrize("specialization", ["  ", "x" * 201, 123])
def test_teacher_validation(
    db_client: TestClient, profile_user_factory: Callable[[Role, str], User],
    profile_bearer: Callable[[User], dict[str, str]], specialization: object,
) -> None:
    user = profile_user_factory(Role.TEACHER, "teacher@example.com")
    response = db_client.patch("/teachers/me", json={"specialization": specialization}, headers=profile_bearer(user))
    assert response.status_code == 422


@pytest.mark.parametrize("role,path,model", PROFILE_DOMAINS)
def test_patch_protects_identity_and_user_fields(
    db_client: TestClient, profile_user_factory: Callable[[Role, str], User],
    profile_bearer: Callable[[User], dict[str, str]], role: Role, path: str,
    model: type[StudentProfile] | type[TeacherProfile] | type[ParentProfile],
) -> None:
    user = profile_user_factory(role, "owner@example.com")
    headers = profile_bearer(user)
    original = db_client.get(path, headers=headers).json()
    for field, value in [
        ("id", str(uuid4())), ("user_id", str(uuid4())), ("created_at", "2000-01-01T00:00:00Z"),
        ("updated_at", "2000-01-01T00:00:00Z"), ("role", "ADMIN"), ("is_active", False),
        ("email", "other@example.com"), ("password_hash", "invalid-hash"), ("full_name", "Other User"),
    ]:
        response = db_client.patch(path, json={field: value}, headers=headers)
        assert response.status_code == 422
    assert db_client.get(path, headers=headers).json() == original


def test_parent_patch_is_empty_and_cannot_self_link_students(
    db_client: TestClient, profile_user_factory: Callable[[Role, str], User],
    profile_bearer: Callable[[User], dict[str, str]],
) -> None:
    user = profile_user_factory(Role.PARENT, "parent@example.com")
    headers = profile_bearer(user)
    original = db_client.get("/parents/me", headers=headers).json()
    assert db_client.patch("/parents/me", json={}, headers=headers).json() == original
    for data in [{"student_id": str(uuid4())}, {"students": [str(uuid4())]}, {"relationship_type": "FATHER"}]:
        assert db_client.patch("/parents/me", json=data, headers=headers).status_code == 422


@pytest.mark.parametrize("role,path,model", PROFILE_DOMAINS)
def test_profiles_are_owned_by_current_user(
    db_client: TestClient, profile_user_factory: Callable[[Role, str], User],
    profile_bearer: Callable[[User], dict[str, str]], role: Role, path: str,
    model: type[StudentProfile] | type[TeacherProfile] | type[ParentProfile],
) -> None:
    first = profile_user_factory(role, "first@example.com")
    second = profile_user_factory(role, "second@example.com")
    first_headers, second_headers = profile_bearer(first), profile_bearer(second)
    original = db_client.get(path, headers=first_headers).json()
    second_profile = db_client.get(path, headers=second_headers).json()
    assert second_profile["user_id"] == str(second.id) and second_profile["id"] != original["id"]
    changes = {Role.STUDENT: {"school_name": "Second School"}, Role.TEACHER: {"specialization": "Physics"}, Role.PARENT: {}}[role]
    assert db_client.patch(path, json=changes, headers=second_headers).status_code == 200
    assert db_client.get(path, headers=first_headers).json() == original
    assert db_client.patch(path, json={"user_id": str(first.id)}, headers=second_headers).status_code == 422


@pytest.mark.parametrize("role,path,model", PROFILE_DOMAINS)
def test_missing_profile_returns_404_without_creating_data(
    db_client: TestClient, db_session: Session, profile_user_factory: Callable[[Role, str], User],
    profile_bearer: Callable[[User], dict[str, str]], role: Role, path: str,
    model: type[StudentProfile] | type[TeacherProfile] | type[ParentProfile],
) -> None:
    user = profile_user_factory(role, "missingprofile@example.com")
    headers = profile_bearer(user)
    db_session.execute(delete(model).where(model.user_id == user.id))
    db_session.commit()
    for response in [db_client.get(path, headers=headers), db_client.patch(path, json={}, headers=headers)]:
        assert response.status_code == 404 and response.json()["error"]["code"] == "PROFILE_NOT_FOUND"
    assert db_session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("role,path,model", PROFILE_DOMAINS)
def test_inactive_users_cannot_access_profiles(
    db_client: TestClient, db_session: Session, profile_user_factory: Callable[[Role, str], User],
    profile_bearer: Callable[[User], dict[str, str]], role: Role, path: str,
    model: type[StudentProfile] | type[TeacherProfile] | type[ParentProfile],
) -> None:
    user = profile_user_factory(role, "inactive@example.com")
    headers = profile_bearer(user)
    user.is_active = False
    db_session.commit()
    assert db_client.get(path, headers=headers).status_code == 401
    assert db_client.patch(path, json={}, headers=headers).status_code == 401


def test_actual_updates_advance_timestamp_and_empty_patch_does_not(
    db_client: TestClient, db_session: Session, profile_user_factory: Callable[[Role, str], User],
    profile_bearer: Callable[[User], dict[str, str]],
) -> None:
    user = profile_user_factory(Role.STUDENT, "timestamp@example.com")
    headers = profile_bearer(user)
    profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    assert profile is not None
    profile.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
    db_session.commit()
    original = db_client.get("/students/me", headers=headers).json()
    assert db_client.patch("/students/me", json={}, headers=headers).json() == original
    updated = db_client.patch("/students/me", json={"school_name": "Updated School"}, headers=headers).json()
    assert as_utc(datetime.fromisoformat(updated["updated_at"])) > as_utc(datetime.fromisoformat(original["updated_at"]))
    assert updated["created_at"] == original["created_at"]


def test_profile_cors_accepts_patch(db_client: TestClient) -> None:
    response = db_client.options(
        "/students/me",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "PATCH", "Access-Control-Request-Headers": "authorization,content-type"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
