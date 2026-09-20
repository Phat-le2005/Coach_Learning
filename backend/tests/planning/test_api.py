from datetime import date, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.classes.models import Classroom, TeacherClassroom
from app.concepts.models import Concept
from app.core.config import Settings
from app.curriculum.models import (
    Chapter,
    LearningOutcome,
    ProblemType,
    ProblemTypeConcept,
    Topic,
)
from app.planning.models import TeachingPlanStatus
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

TEST_PASSWORD = "Teacher-Plan-API-Test-2026!"


def _create_user(session: Session, role: Role, email: str) -> User:
    return UserService(session).create_user(
        UserCreate(email=email, password=TEST_PASSWORD, full_name="Plan API User", role=role)
    )


def _auth_headers(session: Session, settings: Settings, user: User) -> dict[str, str]:
    tokens = AuthService(session, settings).login(
        LoginRequest(email=user.email, password=TEST_PASSWORD)
    )
    return {"Authorization": f"Bearer {tokens.access_token}"}


def _setup_curriculum(
    session: Session, code_prefix: str = "API"
) -> tuple[Subject, ProblemType, Concept, LearningOutcome]:
    subject = Subject(code=f"{code_prefix}-SUB", name=f"{code_prefix} Subject", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(
        subject_id=subject.id,
        code=f"{code_prefix}-CHP",
        name="Chapter",
        order_index=0,
    )
    session.add(chapter)
    session.flush()

    topic = Topic(chapter_id=chapter.id, code=f"{code_prefix}-TOP", name="Topic", order_index=0)
    session.add(topic)
    session.flush()

    pt = ProblemType(
        topic_id=topic.id,
        code=f"{code_prefix}-PT",
        name="Problem Type",
        order_index=0,
        is_active=True,
    )
    session.add(pt)
    session.flush()

    concept = Concept(subject_id=subject.id, code=f"{code_prefix}-CON", name="Concept", order_index=0)
    session.add(concept)
    session.flush()

    session.add(
        ProblemTypeConcept(
            problem_type_id=pt.id,
            concept_id=concept.id,
            weight=1.0,
            is_primary=True,
        )
    )

    lo = LearningOutcome(
        subject_id=subject.id,
        code=f"{code_prefix}-LO",
        description="Learning outcome",
        grade_level=12,
        order_index=0,
    )
    session.add(lo)
    session.commit()
    return subject, pt, concept, lo


def _setup_classroom(session: Session, teacher_user: User) -> Classroom:
    teacher = session.query(TeacherProfile).filter_by(user_id=teacher_user.id).first()
    classroom = Classroom(
        name="12A2",
        academic_year="2025-2026",
        grade_level=12,
        created_by=teacher_user.id,
    )
    classroom.teacher_assignments.append(
        TeacherClassroom(teacher_id=teacher.id, role="OWNER")
    )
    session.add(classroom)
    session.commit()
    session.refresh(classroom)
    return classroom


def test_api_auth_and_role_required(
    db_client: TestClient, db_session: Session, settings: Settings
) -> None:
    random_id = uuid4()
    assert db_client.post(f"/teacher/classes/{random_id}/teaching-plans", json={}).status_code == 401
    assert db_client.get(f"/teacher/classes/{random_id}/teaching-plans").status_code == 401
    assert db_client.get(f"/teacher/teaching-plans/{random_id}").status_code == 401
    assert db_client.patch(f"/teacher/teaching-plans/{random_id}", json={}).status_code == 401
    assert db_client.post(f"/teacher/teaching-plans/{random_id}/activate").status_code == 401
    assert db_client.post(f"/teacher/teaching-plans/{random_id}/complete").status_code == 401

    student = _create_user(db_session, Role.STUDENT, "student.api@example.com")
    headers = _auth_headers(db_session, settings, student)
    assert db_client.post(f"/teacher/classes/{random_id}/teaching-plans", json={}, headers=headers).status_code == 403
    assert db_client.get(f"/teacher/classes/{random_id}/teaching-plans", headers=headers).status_code == 403
    assert db_client.get(f"/teacher/teaching-plans/{random_id}", headers=headers).status_code == 403


def test_api_create_and_list_teaching_plans(
    db_client: TestClient, db_session: Session, settings: Settings
) -> None:
    teacher_user = _create_user(db_session, Role.TEACHER, "teacher.create@example.com")
    headers = _auth_headers(db_session, settings, teacher_user)
    classroom = _setup_classroom(db_session, teacher_user)
    subject, pt, concept, lo = _setup_curriculum(db_session, "CRT")

    payload = {
        "subject_id": str(subject.id),
        "start_date": str(date.today()),
        "target_end_date": str(date.today() + timedelta(days=7)),
        "status": "PLANNED",
        "items": [
            {
                "problem_type_id": str(pt.id),
                "learning_outcome_id": str(lo.id),
                "priority": 2,
                "order_index": 0,
            }
        ],
    }

    create_resp = db_client.post(
        f"/teacher/classes/{classroom.id}/teaching-plans",
        json=payload,
        headers=headers,
    )
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    assert created_data["classroom_id"] == str(classroom.id)
    assert created_data["subject_id"] == str(subject.id)
    assert created_data["status"] == "PLANNED"
    assert len(created_data["items"]) == 1
    assert created_data["items"][0]["problem_type_id"] == str(pt.id)
    assert created_data["items"][0]["derived_concept_ids"] == [str(concept.id)]

    list_resp = db_client.get(
        f"/teacher/classes/{classroom.id}/teaching-plans",
        headers=headers,
    )
    assert list_resp.status_code == 200
    assert list_resp.headers.get("Cache-Control") == "no-store"
    list_data = list_resp.json()
    assert len(list_data) == 1
    assert list_data[0]["id"] == created_data["id"]

    filter_resp = db_client.get(
        f"/teacher/classes/{classroom.id}/teaching-plans?status=ACTIVE",
        headers=headers,
    )
    assert filter_resp.status_code == 200
    assert len(filter_resp.json()) == 0


def test_api_get_patch_activate_complete_workflow(
    db_client: TestClient, db_session: Session, settings: Settings
) -> None:
    t1 = _create_user(db_session, Role.TEACHER, "teacher.flow@example.com")
    t2 = _create_user(db_session, Role.TEACHER, "teacher.other@example.com")
    h1 = _auth_headers(db_session, settings, t1)
    h2 = _auth_headers(db_session, settings, t2)

    classroom = _setup_classroom(db_session, t1)
    subject, pt, _, lo = _setup_curriculum(db_session, "FLW")

    create_resp = db_client.post(
        f"/teacher/classes/{classroom.id}/teaching-plans",
        json={
            "subject_id": str(subject.id),
            "start_date": str(date.today()),
            "status": "PLANNED",
            "items": [{"problem_type_id": str(pt.id), "priority": 1}],
        },
        headers=h1,
    )
    plan_id = create_resp.json()["id"]

    get_other = db_client.get(f"/teacher/teaching-plans/{plan_id}", headers=h2)
    assert get_other.status_code == 403

    get_resp = db_client.get(f"/teacher/teaching-plans/{plan_id}", headers=h1)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == plan_id

    patch_resp = db_client.patch(
        f"/teacher/teaching-plans/{plan_id}",
        json={"target_end_date": str(date.today() + timedelta(days=14))},
        headers=h1,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["target_end_date"] == str(date.today() + timedelta(days=14))

    act_resp = db_client.post(f"/teacher/teaching-plans/{plan_id}/activate", headers=h1)
    assert act_resp.status_code == 200
    assert act_resp.json()["status"] == "ACTIVE"

    act_again = db_client.post(f"/teacher/teaching-plans/{plan_id}/activate", headers=h1)
    assert act_again.status_code == 200
    assert act_again.json()["status"] == "ACTIVE"

    comp_resp = db_client.post(f"/teacher/teaching-plans/{plan_id}/complete", headers=h1)
    assert comp_resp.status_code == 200
    assert comp_resp.json()["status"] == "COMPLETED"

    comp_again = db_client.post(f"/teacher/teaching-plans/{plan_id}/complete", headers=h1)
    assert comp_again.status_code == 200
    assert comp_again.json()["status"] == "COMPLETED"
