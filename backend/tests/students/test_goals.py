from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.core.config import Settings
from app.students.goal_models import AcademicGoalStatus
from app.subjects.models import Subject
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

TEST_PASSWORD = "Student-Goal-Test-2026!"


def create_user(session: Session, role: Role, email: str) -> User:
    return UserService(session).create_user(
        UserCreate(email=email, password=TEST_PASSWORD, full_name="Goal Test User", role=role)
    )


def auth_headers(session: Session, settings: Settings, user: User) -> dict[str, str]:
    pair = AuthService(session, settings).login(
        LoginRequest(email=user.email, password=TEST_PASSWORD)
    )
    return {"Authorization": f"Bearer {pair.access_token}"}


def create_subject(session: Session, code: str, name: str) -> Subject:
    subject = Subject(code=code, name=name, grade_level=12)
    session.add(subject)
    session.commit()
    return subject


def test_goals_require_authentication(db_client: TestClient) -> None:
    goal_id = uuid4()
    assert db_client.get("/students/me/goals").status_code == 401
    assert db_client.post("/students/me/goals", json={}).status_code == 401
    assert db_client.patch(f"/students/me/goals/{goal_id}", json={}).status_code == 401


def test_goals_require_student_role(
    db_client: TestClient, db_session: Session, settings: Settings
) -> None:
    teacher = create_user(db_session, Role.TEACHER, "teacher.goals@example.com")
    headers = auth_headers(db_session, settings, teacher)
    assert db_client.get("/students/me/goals", headers=headers).status_code == 403
    assert db_client.post("/students/me/goals", json={}, headers=headers).status_code == 403


def test_list_goals_empty(
    db_client: TestClient, db_session: Session, settings: Settings
) -> None:
    student = create_user(db_session, Role.STUDENT, "student.empty@example.com")
    headers = auth_headers(db_session, settings, student)

    response = db_client.get("/students/me/goals", headers=headers)
    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["cache-control"] == "no-store"


def test_create_academic_goal_full(
    db_client: TestClient, db_session: Session, settings: Settings
) -> None:
    student = create_user(db_session, Role.STUDENT, "student.create@example.com")
    headers = auth_headers(db_session, settings, student)

    math = create_subject(db_session, "GOAL-MATH", "Toán học 12")
    phys = create_subject(db_session, "GOAL-PHYS", "Vật lý 12")

    exam_date = (date.today() + timedelta(days=90)).isoformat()
    payload = {
        "target_exam": "TN_THPT",
        "exam_date": exam_date,
        "available_daily_minutes": 180,
        "status": "ACTIVE",
        "target_university": "Đại học Bách Khoa Hà Nội",
        "target_major": "Khoa học máy tính",
        "subject_goals": [
            {
                "subject_id": str(math.id),
                "current_score": 7.5,
                "target_score": 9.0,
                "priority": 1,
            },
            {
                "subject_id": str(phys.id),
                "current_score": None,
                "target_score": 8.5,
                "priority": 2,
            },
        ],
    }

    response = db_client.post("/students/me/goals", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()

    assert UUID(data["id"])
    assert data["target_exam"] == "TN_THPT"
    assert data["exam_date"] == exam_date
    assert data["available_daily_minutes"] == 180
    assert data["status"] == "ACTIVE"
    assert data["target_university"] == "Đại học Bách Khoa Hà Nội"
    assert data["target_major"] == "Khoa học máy tính"
    assert len(data["subject_goals"]) == 2

    # Check subject goals
    sub1 = next(sg for sg in data["subject_goals"] if sg["subject_id"] == str(math.id))
    assert sub1["current_score"] == 7.5
    assert sub1["target_score"] == 9.0
    assert sub1["priority"] == 1

    sub2 = next(sg for sg in data["subject_goals"] if sg["subject_id"] == str(phys.id))
    assert sub2["current_score"] is None
    assert sub2["target_score"] == 8.5
    assert sub2["priority"] == 2


def test_create_goal_exam_date_validation(
    db_client: TestClient, db_session: Session, settings: Settings
) -> None:
    student = create_user(db_session, Role.STUDENT, "student.examdate@example.com")
    headers = auth_headers(db_session, settings, student)

    # Past date
    past_date = (date.today() - timedelta(days=1)).isoformat()
    res_past = db_client.post(
        "/students/me/goals",
        json={"target_exam": "TN_THPT", "exam_date": past_date, "available_daily_minutes": 60},
        headers=headers,
    )
    assert res_past.status_code == 422
    assert res_past.json()["error"]["code"] == "INVALID_EXAM_DATE"

    # Too far in the future (> 5 years)
    future_date = (date.today() + timedelta(days=365 * 6)).isoformat()
    res_far = db_client.post(
        "/students/me/goals",
        json={"target_exam": "TN_THPT", "exam_date": future_date, "available_daily_minutes": 60},
        headers=headers,
    )
    assert res_far.status_code == 422
    assert res_far.json()["error"]["code"] == "INVALID_EXAM_DATE"


def test_create_goal_daily_minutes_validation(
    db_client: TestClient, db_session: Session, settings: Settings
) -> None:
    student = create_user(db_session, Role.STUDENT, "student.minutes@example.com")
    headers = auth_headers(db_session, settings, student)
    valid_date = (date.today() + timedelta(days=30)).isoformat()

    # Zero or negative minutes
    res_zero = db_client.post(
        "/students/me/goals",
        json={"target_exam": "TN_THPT", "exam_date": valid_date, "available_daily_minutes": 0},
        headers=headers,
    )
    assert res_zero.status_code == 422

    res_neg = db_client.post(
        "/students/me/goals",
        json={"target_exam": "TN_THPT", "exam_date": valid_date, "available_daily_minutes": -30},
        headers=headers,
    )
    assert res_neg.status_code == 422

    # Greater than 1440 minutes
    res_large = db_client.post(
        "/students/me/goals",
        json={"target_exam": "TN_THPT", "exam_date": valid_date, "available_daily_minutes": 1500},
        headers=headers,
    )
    assert res_large.status_code == 422


def test_create_goal_score_scale_validation(
    db_client: TestClient, db_session: Session, settings: Settings
) -> None:
    student = create_user(db_session, Role.STUDENT, "student.scores@example.com")
    headers = auth_headers(db_session, settings, student)
    valid_date = (date.today() + timedelta(days=60)).isoformat()
    chem = create_subject(db_session, "GOAL-CHEM", "Hóa học 12")

    # Score > 10.0 for TN_THPT
    res_high = db_client.post(
        "/students/me/goals",
        json={
            "target_exam": "TN_THPT",
            "exam_date": valid_date,
            "available_daily_minutes": 60,
            "subject_goals": [{"subject_id": str(chem.id), "target_score": 10.5}],
        },
        headers=headers,
    )
    assert res_high.status_code == 422
    assert res_high.json()["error"]["code"] == "SCORE_OUT_OF_RANGE"

    # Score < 0.0
    res_low = db_client.post(
        "/students/me/goals",
        json={
            "target_exam": "TN_THPT",
            "exam_date": valid_date,
            "available_daily_minutes": 60,
            "subject_goals": [{"subject_id": str(chem.id), "target_score": -1.0}],
        },
        headers=headers,
    )
    assert res_low.status_code == 422
    assert res_low.json()["error"]["code"] == "SCORE_OUT_OF_RANGE"

    # Target score < current score
    res_inv = db_client.post(
        "/students/me/goals",
        json={
            "target_exam": "TN_THPT",
            "exam_date": valid_date,
            "available_daily_minutes": 60,
            "subject_goals": [
                {"subject_id": str(chem.id), "current_score": 8.0, "target_score": 6.0}
            ],
        },
        headers=headers,
    )
    assert res_inv.status_code == 422
    assert res_inv.json()["error"]["code"] == "INVALID_TARGET_SCORE"

    # Configured scale for DGNL_VNU_HCM (0 - 1200)
    res_dgnl = db_client.post(
        "/students/me/goals",
        json={
            "target_exam": "DGNL_VNU_HCM",
            "exam_date": valid_date,
            "available_daily_minutes": 60,
            "subject_goals": [
                {"subject_id": str(chem.id), "current_score": 600.0, "target_score": 950.0}
            ],
        },
        headers=headers,
    )
    assert res_dgnl.status_code == 201
    assert res_dgnl.json()["subject_goals"][0]["target_score"] == 950.0


def test_create_goal_subject_validation(
    db_client: TestClient, db_session: Session, settings: Settings
) -> None:
    student = create_user(db_session, Role.STUDENT, "student.subval@example.com")
    headers = auth_headers(db_session, settings, student)
    valid_date = (date.today() + timedelta(days=60)).isoformat()
    bio = create_subject(db_session, "GOAL-BIO", "Sinh học 12")

    # Missing subject
    fake_id = str(uuid4())
    res_missing = db_client.post(
        "/students/me/goals",
        json={
            "target_exam": "TN_THPT",
            "exam_date": valid_date,
            "available_daily_minutes": 60,
            "subject_goals": [{"subject_id": fake_id, "target_score": 8.0}],
        },
        headers=headers,
    )
    assert res_missing.status_code == 422
    assert res_missing.json()["error"]["code"] == "SUBJECT_NOT_FOUND"

    # Duplicate subject
    res_dup = db_client.post(
        "/students/me/goals",
        json={
            "target_exam": "TN_THPT",
            "exam_date": valid_date,
            "available_daily_minutes": 60,
            "subject_goals": [
                {"subject_id": str(bio.id), "target_score": 8.0},
                {"subject_id": str(bio.id), "target_score": 9.0},
            ],
        },
        headers=headers,
    )
    assert res_dup.status_code == 422
    assert res_dup.json()["error"]["code"] == "DUPLICATE_SUBJECT_GOAL"


def test_active_goal_policy(
    db_client: TestClient, db_session: Session, settings: Settings
) -> None:
    student = create_user(db_session, Role.STUDENT, "student.policy@example.com")
    headers = auth_headers(db_session, settings, student)
    valid_date = (date.today() + timedelta(days=60)).isoformat()

    # Create 1st active goal
    res1 = db_client.post(
        "/students/me/goals",
        json={"target_exam": "TN_THPT", "exam_date": valid_date, "available_daily_minutes": 60},
        headers=headers,
    )
    assert res1.status_code == 201
    assert res1.json()["status"] == "ACTIVE"

    # Attempt to create 2nd active goal -> 409
    res2 = db_client.post(
        "/students/me/goals",
        json={
            "target_exam": "DGNL_VNU_HN",
            "exam_date": valid_date,
            "available_daily_minutes": 90,
            "status": "ACTIVE",
        },
        headers=headers,
    )
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "ACTIVE_GOAL_LIMIT_EXCEEDED"

    # Creating an ARCHIVED or COMPLETED goal while an ACTIVE goal exists is allowed
    res_archived = db_client.post(
        "/students/me/goals",
        json={
            "target_exam": "HISTORICAL_EXAM",
            "exam_date": valid_date,
            "available_daily_minutes": 90,
            "status": "ARCHIVED",
        },
        headers=headers,
    )
    assert res_archived.status_code == 201
    assert res_archived.json()["status"] == "ARCHIVED"


def test_list_goals_and_filter_by_status(
    db_client: TestClient, db_session: Session, settings: Settings
) -> None:
    student = create_user(db_session, Role.STUDENT, "student.listgoals@example.com")
    headers = auth_headers(db_session, settings, student)
    valid_date = (date.today() + timedelta(days=45)).isoformat()

    db_client.post(
        "/students/me/goals",
        json={"target_exam": "EXAM_ACTIVE", "exam_date": valid_date, "available_daily_minutes": 60, "status": "ACTIVE"},
        headers=headers,
    )
    db_client.post(
        "/students/me/goals",
        json={"target_exam": "EXAM_COMPLETED", "exam_date": valid_date, "available_daily_minutes": 60, "status": "COMPLETED"},
        headers=headers,
    )
    db_client.post(
        "/students/me/goals",
        json={"target_exam": "EXAM_ARCHIVED", "exam_date": valid_date, "available_daily_minutes": 60, "status": "ARCHIVED"},
        headers=headers,
    )

    # All goals
    all_res = db_client.get("/students/me/goals", headers=headers)
    assert all_res.status_code == 200
    assert len(all_res.json()) == 3

    # Filter by ACTIVE
    active_res = db_client.get("/students/me/goals?status=ACTIVE", headers=headers)
    assert active_res.status_code == 200
    assert len(active_res.json()) == 1
    assert active_res.json()[0]["target_exam"] == "EXAM_ACTIVE"

    # Filter by COMPLETED
    comp_res = db_client.get("/students/me/goals?status=COMPLETED", headers=headers)
    assert comp_res.status_code == 200
    assert len(comp_res.json()) == 1
    assert comp_res.json()[0]["target_exam"] == "EXAM_COMPLETED"

    # Filter by ABANDONED (none)
    aban_res = db_client.get("/students/me/goals?status=ABANDONED", headers=headers)
    assert aban_res.status_code == 200
    assert aban_res.json() == []


def test_patch_goal_and_status_transitions(
    db_client: TestClient, db_session: Session, settings: Settings
) -> None:
    student = create_user(db_session, Role.STUDENT, "student.patch@example.com")
    headers = auth_headers(db_session, settings, student)
    valid_date = (date.today() + timedelta(days=30)).isoformat()
    lit = create_subject(db_session, "GOAL-LIT", "Ngữ văn 12")
    history = create_subject(db_session, "GOAL-HIST", "Lịch sử 12")

    # Create Goal 1 (ACTIVE)
    res1 = db_client.post(
        "/students/me/goals",
        json={
            "target_exam": "TN_THPT",
            "exam_date": valid_date,
            "available_daily_minutes": 60,
            "status": "ACTIVE",
            "subject_goals": [{"subject_id": str(lit.id), "target_score": 8.0}],
        },
        headers=headers,
    )
    goal1_id = res1.json()["id"]

    # Patch Goal 1 properties
    new_date = (date.today() + timedelta(days=40)).isoformat()
    patch_res = db_client.patch(
        f"/students/me/goals/{goal1_id}",
        json={
            "available_daily_minutes": 120,
            "exam_date": new_date,
            "target_university": "Đại học Luật",
            "target_major": "Luật kinh tế",
            "subject_goals": [
                {"subject_id": str(lit.id), "current_score": 7.0, "target_score": 8.5},
                {"subject_id": str(history.id), "current_score": 6.5, "target_score": 9.0},
            ],
        },
        headers=headers,
    )
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["available_daily_minutes"] == 120
    assert data["exam_date"] == new_date
    assert data["target_university"] == "Đại học Luật"
    assert len(data["subject_goals"]) == 2

    # Complete Goal 1
    comp_res = db_client.patch(
        f"/students/me/goals/{goal1_id}",
        json={"status": "COMPLETED"},
        headers=headers,
    )
    assert comp_res.status_code == 200
    assert comp_res.json()["status"] == "COMPLETED"

    # Create Goal 2 (ACTIVE) - allowed because Goal 1 is COMPLETED
    res2 = db_client.post(
        "/students/me/goals",
        json={"target_exam": "DGTD_HUST", "exam_date": valid_date, "available_daily_minutes": 90},
        headers=headers,
    )
    assert res2.status_code == 201
    goal2_id = res2.json()["id"]

    # Try to reactivate Goal 1 while Goal 2 is ACTIVE -> 409
    reactivate_fail = db_client.patch(
        f"/students/me/goals/{goal1_id}",
        json={"status": "ACTIVE"},
        headers=headers,
    )
    assert reactivate_fail.status_code == 409
    assert reactivate_fail.json()["error"]["code"] == "ACTIVE_GOAL_LIMIT_EXCEEDED"

    # Archive Goal 2, then Goal 1 can be reactivated
    db_client.patch(f"/students/me/goals/{goal2_id}", json={"status": "ARCHIVED"}, headers=headers)
    reactivate_ok = db_client.patch(
        f"/students/me/goals/{goal1_id}",
        json={"status": "ACTIVE"},
        headers=headers,
    )
    assert reactivate_ok.status_code == 200
    assert reactivate_ok.json()["status"] == "ACTIVE"


def test_goal_isolation_between_students(
    db_client: TestClient, db_session: Session, settings: Settings
) -> None:
    student_a = create_user(db_session, Role.STUDENT, "student.a@example.com")
    student_b = create_user(db_session, Role.STUDENT, "student.b@example.com")
    headers_a = auth_headers(db_session, settings, student_a)
    headers_b = auth_headers(db_session, settings, student_b)

    valid_date = (date.today() + timedelta(days=30)).isoformat()
    res_a = db_client.post(
        "/students/me/goals",
        json={"target_exam": "TN_THPT", "exam_date": valid_date, "available_daily_minutes": 60},
        headers=headers_a,
    )
    goal_a_id = res_a.json()["id"]

    # Student B cannot patch Student A's goal -> 404
    res_b_patch = db_client.patch(
        f"/students/me/goals/{goal_a_id}",
        json={"available_daily_minutes": 100},
        headers=headers_b,
    )
    assert res_b_patch.status_code == 404
    assert res_b_patch.json()["error"]["code"] == "GOAL_NOT_FOUND"

    # Student B's goal list does not include Student A's goal
    res_b_list = db_client.get("/students/me/goals", headers=headers_b)
    assert res_b_list.status_code == 200
    assert res_b_list.json() == []
