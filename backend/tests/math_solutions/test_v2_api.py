from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignments.models import (
    Assignment,
    AssignmentStatus,
    AssignmentType,
    StudentAssignment,
    StudentAssignmentStatus,
)
from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment
from app.core.config import Settings
from app.learning_evidence.models import LearningEvidenceEvent
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.math_solutions.models import EvaluationDecision, SolutionAttempt, StepEvaluation
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.questions.models import Question, QuestionStatus, QuestionType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

PASSWORD = "Math-Workspace-API-Test-2026!"


@dataclass(frozen=True)
class V2Domain:
    student: User
    outsider: User
    teacher: User
    student_profile: StudentProfile
    outsider_profile: StudentProfile
    subject: Subject
    question: Question
    practice: PracticeSession


@pytest.fixture
def v2_domain(db_session: Session) -> V2Domain:
    users = UserService(db_session)

    def create_user(role: Role, local_part: str) -> User:
        return users.create_user(
            UserCreate(
                email=f"{local_part}@example.com",
                password=PASSWORD,
                full_name=f"{role.value.title()} Workspace User",
                role=role,
            )
        )

    student = create_user(Role.STUDENT, "v2-student")
    outsider = create_user(Role.STUDENT, "v2-outsider")
    teacher = create_user(Role.TEACHER, "v2-teacher")
    student_profile = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    )
    outsider_profile = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == outsider.id)
    )
    assert student_profile is not None
    assert outsider_profile is not None

    subject = Subject(code="MATH-V2-TEST", name="Mathematics v2 test", grade_level=12)
    db_session.add(subject)
    db_session.flush()
    question = Question(
        subject_id=subject.id,
        content="Analyze the monotonicity of the given function.",
        question_type=QuestionType.OPEN_RESPONSE,
        difficulty=0.6,
        correct_answer="This answer must never be exposed through workspace APIs.",
        explanation="Teacher-only test explanation.",
        source_type="TEST",
        source_reference="v2-api-suite",
        exam_weight=0.5,
        status=QuestionStatus.APPROVED,
        created_by=teacher.id,
    )
    db_session.add(question)
    db_session.flush()
    practice = PracticeSession(
        student_id=student_profile.id,
        subject_id=subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    db_session.add(practice)
    db_session.commit()
    return V2Domain(
        student=student,
        outsider=outsider,
        teacher=teacher,
        student_profile=student_profile,
        outsider_profile=outsider_profile,
        subject=subject,
        question=question,
        practice=practice,
    )


@pytest.fixture
def auth_headers(db_session: Session, settings: Settings):
    def build(user: User) -> dict[str, str]:
        pair = AuthService(db_session, settings).login(
            LoginRequest(email=user.email, password=PASSWORD)
        )
        return {"Authorization": f"Bearer {pair.access_token}"}

    return build


def create_payload(domain: V2Domain, *, key: str = "workspace-create-1") -> dict[str, str]:
    return {
        "source_kind": "CANONICAL",
        "context_type": "SELF_PRACTICE",
        "mode": "INDEPENDENT_SOLUTION",
        "create_idempotency_key": key,
        "question_id": str(domain.question.id),
        "practice_session_id": str(domain.practice.id),
    }


def mutation(revision: int, **fields: object) -> dict[str, object]:
    return {
        "expected_attempt_revision": revision,
        "client_action_id": str(uuid4()),
        **fields,
    }


def test_v2_openapi_docs_routes_and_cors_are_isolated(db_client: TestClient) -> None:
    docs = db_client.get("/api/v2/docs")
    schema_response = db_client.get("/api/v2/openapi.json")
    assert docs.status_code == 200
    assert schema_response.status_code == 200
    paths = schema_response.json()["paths"]
    assert len(paths) == 10
    assert "/math-solutions/attempts" in paths
    assert all(not path.startswith("/api/v2") for path in paths)
    assert db_client.get("/api/v2/api/v2/openapi.json").status_code == 404
    assert all(
        not path.startswith("/api/v2/math-solutions")
        for path in db_client.get("/openapi.json").json()["paths"]
    )

    preflight = db_client.options(
        "/api/v2/math-solutions/attempts",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_v2_requires_student_authentication_and_uses_error_envelope(
    db_client: TestClient,
    v2_domain: V2Domain,
    auth_headers,
) -> None:
    anonymous = db_client.post(
        "/api/v2/math-solutions/attempts", json=create_payload(v2_domain)
    )
    teacher = db_client.post(
        "/api/v2/math-solutions/attempts",
        json=create_payload(v2_domain, key="teacher-create"),
        headers=auth_headers(v2_domain.teacher),
    )
    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "INVALID_TOKEN"
    assert teacher.status_code == 403
    assert teacher.json()["error"]["code"] == "FORBIDDEN"


def test_complete_workspace_lifecycle_is_owned_no_store_and_does_not_emit_evidence(
    db_client: TestClient,
    db_session: Session,
    v2_domain: V2Domain,
    auth_headers,
) -> None:
    headers = auth_headers(v2_domain.student)
    created = db_client.post(
        "/api/v2/math-solutions/attempts",
        json=create_payload(v2_domain),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.headers["cache-control"] == "no-store"
    current = created.json()
    attempt_id = current["id"]
    assert current["status"] == "DRAFT"
    assert current["question_id"] == str(v2_domain.question.id)
    assert current["practice_session_id"] == str(v2_domain.practice.id)
    assert current["steps"] == []
    serialized = created.text.casefold()
    assert "correct_answer" not in serialized
    assert "teacher-only test explanation" not in serialized
    assert "rubric" not in serialized

    opened = db_client.get(
        f"/api/v2/math-solutions/attempts/{attempt_id}", headers=headers
    )
    assert opened.status_code == 200
    assert opened.headers["cache-control"] == "no-store"
    assert opened.json() == current

    step_payloads = [
        {
            "step_type": "DERIVATIVE_CALCULATION",
            "content_latex": "f'(x)=3x^2-3",
        },
        {
            "step_type": "SIGN_TABLE",
            "explanation_text": "Record the derivative signs on each interval.",
            "artifact": {
                "artifact_type": "SIGN_TABLE",
                "payload": {"critical_points": [-1, 1], "signs": ["+", "-", "+"]},
            },
        },
    ]
    for step_payload in step_payloads:
        response = db_client.post(
            f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
            json=mutation(current["attempt_revision_number"], **step_payload),
            headers=headers,
        )
        assert response.status_code == 201, response.text
        current = response.json()

    first_id = current["steps"][0]["id"]
    second_id = current["steps"][1]["id"]
    updated = db_client.patch(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps/{first_id}",
        json=mutation(
            current["attempt_revision_number"],
            step_type="DERIVATIVE_CALCULATION",
            content_latex="f'(x)=3(x-1)(x+1)",
        ),
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    current = updated.json()

    reordered = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/reorder",
        json=mutation(
            current["attempt_revision_number"], step_ids=[second_id, first_id]
        ),
        headers=headers,
    )
    assert reordered.status_code == 200, reordered.text
    current = reordered.json()
    assert [step["id"] for step in current["steps"]] == [second_id, first_id]

    deleted = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps/{second_id}/delete",
        json=mutation(current["attempt_revision_number"]),
        headers=headers,
    )
    assert deleted.status_code == 200, deleted.text
    current = deleted.json()
    assert [step["id"] for step in current["steps"]] == [first_id]

    restored = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps/{second_id}/restore",
        json=mutation(current["attempt_revision_number"]),
        headers=headers,
    )
    assert restored.status_code == 200, restored.text
    current = restored.json()
    assert {step["id"] for step in current["steps"]} == {first_id, second_id}

    revisions = db_client.get(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps/{first_id}/revisions",
        headers=headers,
    )
    assert revisions.status_code == 200, revisions.text
    assert len(revisions.json()) >= 3
    assert all("created_at" in revision for revision in revisions.json())

    rolled_back = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps/{first_id}/rollback",
        json=mutation(current["attempt_revision_number"], to_revision=1),
        headers=headers,
    )
    assert rolled_back.status_code == 200, rolled_back.text
    current = rolled_back.json()
    first = next(step for step in current["steps"] if step["id"] == first_id)
    assert first["content_latex"] == "f'(x)=3x^2-3"

    submitted = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/submit",
        json=mutation(current["attempt_revision_number"]),
        headers=headers,
    )
    assert submitted.status_code == 200, submitted.text
    current = submitted.json()
    assert current["status"] == "SUBMITTED"
    assert current["submitted_at"] is not None

    locked = db_client.patch(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps/{first_id}",
        json=mutation(
            current["attempt_revision_number"],
            step_type="CUSTOM",
            content_latex="post-submit edit",
        ),
        headers=headers,
    )
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "SOLUTION_LOCKED"

    assert db_session.scalar(select(StepEvaluation)) is None
    assert db_session.scalar(select(EvaluationDecision)) is None
    assert db_session.scalar(select(LearningEvidenceEvent)) is None
    assert db_session.scalar(select(StudentConceptMastery)) is None
    assert db_session.scalar(select(StudentProblemTypeMastery)) is None


def test_v2_ownership_idempotency_concurrency_and_atomic_validation(
    db_client: TestClient,
    v2_domain: V2Domain,
    auth_headers,
) -> None:
    owner_headers = auth_headers(v2_domain.student)
    outsider_headers = auth_headers(v2_domain.outsider)
    payload = create_payload(v2_domain, key="idempotent-create")
    first_create = db_client.post(
        "/api/v2/math-solutions/attempts", json=payload, headers=owner_headers
    )
    replay_create = db_client.post(
        "/api/v2/math-solutions/attempts", json=payload, headers=owner_headers
    )
    assert first_create.status_code == replay_create.status_code == 201
    assert first_create.json()["id"] == replay_create.json()["id"]
    attempt_id = first_create.json()["id"]

    conflicting_create = db_client.post(
        "/api/v2/math-solutions/attempts",
        json={**payload, "mode": "GUIDED_LEARNING"},
        headers=owner_headers,
    )
    assert conflicting_create.status_code == 409
    assert conflicting_create.json()["error"]["code"] == "CREATE_KEY_REUSED"

    hidden = db_client.get(
        f"/api/v2/math-solutions/attempts/{attempt_id}", headers=outsider_headers
    )
    assert hidden.status_code == 404

    action_id = str(uuid4())
    action = {
        "expected_attempt_revision": 1,
        "client_action_id": action_id,
        "step_type": "CUSTOM",
        "content_latex": "x=1",
    }
    first = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
        json=action,
        headers=owner_headers,
    )
    retry = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
        json=action,
        headers=owner_headers,
    )
    assert first.status_code == retry.status_code == 201
    assert first.json() == retry.json()

    conflicting_action = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
        json={**action, "content_latex": "x=2"},
        headers=owner_headers,
    )
    assert conflicting_action.status_code == 409
    assert conflicting_action.json()["error"]["code"] == "ACTION_KEY_REUSED"

    stale = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
        json=mutation(1, step_type="CUSTOM", content_latex="stale"),
        headers=owner_headers,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "SOLUTION_REVISION_CONFLICT"

    current = first.json()
    invalid_reorder = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/reorder",
        json=mutation(current["attempt_revision_number"], step_ids=[str(uuid4())]),
        headers=owner_headers,
    )
    assert invalid_reorder.status_code == 422
    after = db_client.get(
        f"/api/v2/math-solutions/attempts/{attempt_id}", headers=owner_headers
    ).json()
    assert after["attempt_revision_number"] == current["attempt_revision_number"]
    assert after["steps"] == current["steps"]


def test_cross_class_teacher_material_attempt_is_rejected_at_api_boundary(
    db_client: TestClient,
    db_session: Session,
    v2_domain: V2Domain,
    auth_headers,
) -> None:
    now = datetime.now(timezone.utc)
    room_a = Classroom(
        name="Workspace class A",
        academic_year="2026-2027",
        grade_level=12,
        created_by=v2_domain.teacher.id,
    )
    room_b = Classroom(
        name="Workspace class B",
        academic_year="2026-2027",
        grade_level=12,
        created_by=v2_domain.teacher.id,
    )
    db_session.add_all([room_a, room_b])
    db_session.flush()
    db_session.add_all(
        [
            StudentEnrollment(
                student_id=v2_domain.student_profile.id,
                classroom_id=room_a.id,
                status=EnrollmentStatus.ACTIVE,
            ),
            StudentEnrollment(
                student_id=v2_domain.outsider_profile.id,
                classroom_id=room_b.id,
                status=EnrollmentStatus.ACTIVE,
            ),
        ]
    )
    assignments = [
        Assignment(
            classroom_id=room.id,
            subject_id=v2_domain.subject.id,
            title=f"PDF assignment {label}",
            assignment_type=AssignmentType.SAME_SET,
            status=AssignmentStatus.PUBLISHED,
            question_count=1,
            start_at=now - timedelta(hours=1),
            due_at=now + timedelta(days=1),
            created_by=v2_domain.teacher.id,
        )
        for room, label in ((room_a, "A"), (room_b, "B"))
    ]
    db_session.add_all(assignments)
    db_session.flush()
    foreign_assignment = StudentAssignment(
        assignment_id=assignments[1].id,
        student_id=v2_domain.outsider_profile.id,
        status=StudentAssignmentStatus.NOT_STARTED,
    )
    db_session.add(foreign_assignment)
    db_session.commit()

    response = db_client.post(
        "/api/v2/math-solutions/attempts",
        headers=auth_headers(v2_domain.student),
        json={
            "source_kind": "TEACHER_MATERIAL",
            "context_type": "CLASSROOM_ASSIGNMENT",
            "mode": "INDEPENDENT_SOLUTION",
            "create_idempotency_key": "cross-class-pdf",
            "student_assignment_id": str(foreign_assignment.id),
            "student_assignment_material_item_id": str(uuid4()),
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ASSIGNMENT_NOT_ACCESSIBLE"
    assert db_session.scalar(
        select(SolutionAttempt).where(
            SolutionAttempt.student_id == v2_domain.student_profile.id,
            SolutionAttempt.create_idempotency_key == "cross-class-pdf",
        )
    ) is None