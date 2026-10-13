from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assignments.models import (
    Assignment,
    AssignmentMaterialItem,
    AssignmentStatus,
    AssignmentType,
    StudentAssignment,
    StudentAssignmentMaterialItem,
    StudentAssignmentStatus,
)
from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment
from app.core.config import Settings
from app.learning_evidence.models import LearningEvidenceEvent
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.math_solutions.models import (
    EvaluationDecision,
    MathArtifact,
    SolutionAttempt,
    SolutionOperation,
    SolutionRubric,
    SolutionStep,
    StepEvaluation,
    StepRevision,
)
from app.math_solutions.service import MathSolutionService
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.questions.models import Question, QuestionStatus, QuestionType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teacher_materials.models import (
    MaterialEvaluationMode,
    MaterialItemExtractionStatus,
    TeacherMaterial,
    TeacherMaterialItem,
    TeacherMaterialStatus,
)
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
    assert len(paths) == 14
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
    assert created.headers["pragma"] == "no-cache"
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
    assert opened.headers["pragma"] == "no-cache"
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


def test_v2_cache_control_and_error_envelope_on_all_error_codes(
    db_client: TestClient,
    v2_domain: V2Domain,
    auth_headers,
) -> None:
    student_headers = auth_headers(v2_domain.student)
    teacher_headers = auth_headers(v2_domain.teacher)

    # 1. Success 201 Created and 200 OK
    res_201 = db_client.post(
        "/api/v2/math-solutions/attempts",
        json=create_payload(v2_domain, key="cache-hdr-create"),
        headers=student_headers,
    )
    assert res_201.status_code == 201
    assert res_201.headers.get("cache-control") == "no-store"
    assert res_201.headers.get("pragma") == "no-cache"
    attempt_id = res_201.json()["id"]

    res_200 = db_client.get(
        f"/api/v2/math-solutions/attempts/{attempt_id}",
        headers=student_headers,
    )
    assert res_200.status_code == 200
    assert res_200.headers.get("cache-control") == "no-store"
    assert res_200.headers.get("pragma") == "no-cache"

    # 2. 401 Unauthorized (Anonymous)
    res_401 = db_client.post(
        "/api/v2/math-solutions/attempts",
        json=create_payload(v2_domain, key="anon-key"),
    )
    assert res_401.status_code == 401
    assert res_401.headers.get("cache-control") == "no-store"
    assert res_401.headers.get("pragma") == "no-cache"
    data_401 = res_401.json()
    assert "error" in data_401
    assert data_401["error"]["code"] == "INVALID_TOKEN"
    assert "message" in data_401["error"]

    # 3. 403 Forbidden (Role.TEACHER)
    res_403 = db_client.get(
        f"/api/v2/math-solutions/attempts/{attempt_id}",
        headers=teacher_headers,
    )
    assert res_403.status_code == 403
    assert res_403.headers.get("cache-control") == "no-store"
    assert res_403.headers.get("pragma") == "no-cache"
    data_403 = res_403.json()
    assert "error" in data_403
    assert data_403["error"]["code"] == "FORBIDDEN"
    assert "message" in data_403["error"]

    # 4. 404 Not Found (Non-existent attempt)
    non_existent = str(uuid4())
    res_404 = db_client.get(
        f"/api/v2/math-solutions/attempts/{non_existent}",
        headers=student_headers,
    )
    assert res_404.status_code == 404
    assert res_404.headers.get("cache-control") == "no-store"
    assert res_404.headers.get("pragma") == "no-cache"
    data_404 = res_404.json()
    assert "error" in data_404
    assert data_404["error"]["code"] == "SOLUTION_ATTEMPT_NOT_FOUND"
    assert "message" in data_404["error"]

    # 5. 409 Conflict (Revision conflict)
    res_409 = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
        json=mutation(999, step_type="CUSTOM", content_latex="invalid"),
        headers=student_headers,
    )
    assert res_409.status_code == 409
    assert res_409.headers.get("cache-control") == "no-store"
    assert res_409.headers.get("pragma") == "no-cache"
    data_409 = res_409.json()
    assert "error" in data_409
    assert data_409["error"]["code"] == "SOLUTION_REVISION_CONFLICT"
    assert "message" in data_409["error"]

    # 6. 422 Unprocessable Entity (Validation error)
    res_422 = db_client.post(
        "/api/v2/math-solutions/attempts",
        json={},
        headers=student_headers,
    )
    assert res_422.status_code == 422
    assert res_422.headers.get("cache-control") == "no-store"
    assert res_422.headers.get("pragma") == "no-cache"
    data_422 = res_422.json()
    assert "error" in data_422
    assert data_422["error"]["code"] == "VALIDATION_ERROR"
    assert "message" in data_422["error"]

    # Check that none of the responses leak sensitive information
    responses = [res_201, res_200, res_401, res_403, res_404, res_409, res_422]
    for r in responses:
        body_lower = r.text.casefold()
        assert "correct_answer" not in body_lower
        assert "teacher-only test explanation" not in body_lower
        assert "password" not in body_lower

    # Verify CORS preflight OPTIONS still works and keeps standard CORS behavior
    options = db_client.options(
        "/api/v2/math-solutions/attempts",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert options.status_code == 200
    assert options.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_v2_unhandled_500_keeps_private_cache_policy_and_cors(
    db_app: FastAPI,
    v2_domain: V2Domain,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    internal_detail = "database-password-or-rubric-must-not-leak"

    def raise_unexpected_error(*args: object, **kwargs: object) -> None:
        raise RuntimeError(internal_detail)

    monkeypatch.setattr(MathSolutionService, "get", raise_unexpected_error)
    with TestClient(db_app, raise_server_exceptions=False) as client:
        response = client.get(
            f"/api/v2/math-solutions/attempts/{uuid4()}",
            headers={
                **auth_headers(v2_domain.student),
                "Origin": "http://localhost:3000",
            },
        )
        docs_response = client.get("/api/v2/docs")
        preflight = client.options(
            "/api/v2/math-solutions/attempts",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred.",
        }
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert internal_detail not in response.text

    assert docs_response.status_code == 200
    assert docs_response.headers.get("cache-control") != "no-store"
    assert docs_response.headers.get("pragma") != "no-cache"
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert preflight.headers.get("cache-control") != "no-store"
    assert preflight.headers.get("pragma") != "no-cache"


def test_v2_all_endpoints_reject_teacher_and_anonymous(
    db_client: TestClient,
    v2_domain: V2Domain,
    auth_headers,
) -> None:
    teacher_headers = auth_headers(v2_domain.teacher)
    dummy_attempt_id = str(uuid4())
    dummy_step_id = str(uuid4())

    endpoints = [
        ("POST", "/api/v2/math-solutions/attempts", create_payload(v2_domain, key=f"auth-test-{uuid4().hex[:8]}")),
        ("GET", f"/api/v2/math-solutions/attempts/{dummy_attempt_id}", None),
        ("POST", f"/api/v2/math-solutions/attempts/{dummy_attempt_id}/steps", mutation(1, step_type="CUSTOM", content_latex="x=1")),
        ("PATCH", f"/api/v2/math-solutions/attempts/{dummy_attempt_id}/steps/{dummy_step_id}", mutation(1, step_type="CUSTOM", content_latex="x=2")),
        ("POST", f"/api/v2/math-solutions/attempts/{dummy_attempt_id}/steps/{dummy_step_id}/delete", mutation(1)),
        ("POST", f"/api/v2/math-solutions/attempts/{dummy_attempt_id}/steps/{dummy_step_id}/restore", mutation(1)),
        ("POST", f"/api/v2/math-solutions/attempts/{dummy_attempt_id}/reorder", mutation(1, step_ids=[dummy_step_id])),
        ("GET", f"/api/v2/math-solutions/attempts/{dummy_attempt_id}/steps/{dummy_step_id}/revisions", None),
        ("POST", f"/api/v2/math-solutions/attempts/{dummy_attempt_id}/steps/{dummy_step_id}/rollback", mutation(1, to_revision=1)),
        ("POST", f"/api/v2/math-solutions/attempts/{dummy_attempt_id}/submit", mutation(1)),
    ]
    assert len(endpoints) == 10

    for method, path, json_data in endpoints:
        # Anonymous -> 401
        res_anon = db_client.request(method, path, json=json_data)
        assert res_anon.status_code == 401, f"{method} {path} anon failed: {res_anon.status_code}"
        assert res_anon.headers.get("cache-control") == "no-store"
        assert res_anon.headers.get("pragma") == "no-cache"
        assert res_anon.json()["error"]["code"] == "INVALID_TOKEN"

        # Teacher -> 403
        res_teacher = db_client.request(method, path, json=json_data, headers=teacher_headers)
        assert res_teacher.status_code == 403, f"{method} {path} teacher failed: {res_teacher.status_code}"
        assert res_teacher.headers.get("cache-control") == "no-store"
        assert res_teacher.headers.get("pragma") == "no-cache"
        assert res_teacher.json()["error"]["code"] == "FORBIDDEN"


def test_v2_student_b_cannot_access_or_mutate_student_a_attempt(
    db_client: TestClient,
    v2_domain: V2Domain,
    auth_headers,
) -> None:
    owner_headers = auth_headers(v2_domain.student)
    outsider_headers = auth_headers(v2_domain.outsider)

    # Student A creates attempt and adds a step
    created = db_client.post(
        "/api/v2/math-solutions/attempts",
        json=create_payload(v2_domain, key="student-a-isolation-attempt"),
        headers=owner_headers,
    )
    assert created.status_code == 201
    attempt_id = created.json()["id"]

    step_res = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
        json=mutation(1, step_type="DERIVATIVE_CALCULATION", content_latex="f'(x)=2x"),
        headers=owner_headers,
    )
    assert step_res.status_code == 201
    step_id = step_res.json()["steps"][0]["id"]
    baseline = step_res.json()

    # Student B attempts all 9 attempt/step read and mutate endpoints
    endpoints_to_test = [
        ("GET", f"/api/v2/math-solutions/attempts/{attempt_id}", None),
        ("POST", f"/api/v2/math-solutions/attempts/{attempt_id}/steps", mutation(2, step_type="CUSTOM", content_latex="hack")),
        ("PATCH", f"/api/v2/math-solutions/attempts/{attempt_id}/steps/{step_id}", mutation(2, step_type="CUSTOM", content_latex="hack")),
        ("POST", f"/api/v2/math-solutions/attempts/{attempt_id}/steps/{step_id}/delete", mutation(2)),
        ("POST", f"/api/v2/math-solutions/attempts/{attempt_id}/steps/{step_id}/restore", mutation(2)),
        ("POST", f"/api/v2/math-solutions/attempts/{attempt_id}/reorder", mutation(2, step_ids=[step_id])),
        ("GET", f"/api/v2/math-solutions/attempts/{attempt_id}/steps/{step_id}/revisions", None),
        ("POST", f"/api/v2/math-solutions/attempts/{attempt_id}/steps/{step_id}/rollback", mutation(2, to_revision=1)),
        ("POST", f"/api/v2/math-solutions/attempts/{attempt_id}/submit", mutation(2)),
    ]

    for method, path, json_data in endpoints_to_test:
        res = db_client.request(method, path, json=json_data, headers=outsider_headers)
        assert res.status_code == 404, f"{method} {path} outsider unexpectedly allowed: {res.status_code}"
        assert res.headers.get("cache-control") == "no-store"
        assert res.headers.get("pragma") == "no-cache"
        assert res.json()["error"]["code"] == "SOLUTION_ATTEMPT_NOT_FOUND"

    # Confirm Student A's state is completely unpolluted
    check_res = db_client.get(
        f"/api/v2/math-solutions/attempts/{attempt_id}",
        headers=owner_headers,
    )
    assert check_res.status_code == 200
    assert check_res.json() == baseline


def test_v2_valid_teacher_pdf_snapshot_lifecycle_and_cross_boundary_rejection(
    db_client: TestClient,
    db_session: Session,
    v2_domain: V2Domain,
    auth_headers,
) -> None:
    now = datetime.now(timezone.utc)
    room_a = Classroom(
        name="PDF Workspace class A",
        academic_year="2026-2027",
        grade_level=12,
        created_by=v2_domain.teacher.id,
    )
    room_b = Classroom(
        name="PDF Workspace class B",
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
            title=f"Valid PDF assignment {tag}",
            assignment_type=AssignmentType.SAME_SET,
            status=AssignmentStatus.PUBLISHED,
            question_count=1,
            start_at=now - timedelta(hours=1),
            due_at=now + timedelta(days=2),
            created_by=v2_domain.teacher.id,
        )
        for room, tag in ((room_a, "A"), (room_b, "B"))
    ]
    db_session.add_all(assignments)
    db_session.flush()

    materials = [
        TeacherMaterial(
            classroom_id=room.id,
            subject_id=v2_domain.subject.id,
            uploaded_by=v2_domain.teacher.id,
            title=f"Material {tag}",
            original_file_name=f"{tag}.pdf",
            mime_type="application/pdf",
            storage_key=f"test/{uuid4().hex}.pdf",
            sha256=tag.lower() * 64,
            file_size_bytes=256,
            page_count=1,
            status=TeacherMaterialStatus.READY,
        )
        for room, tag in ((room_a, "A"), (room_b, "B"))
    ]
    db_session.add_all(materials)
    db_session.flush()

    material_items = [
        TeacherMaterialItem(
            teacher_material_id=material.id,
            order_index=0,
            page_start=1,
            page_end=1,
            content=f"Teacher PDF Problem {tag}",
            content_hash=tag.lower() * 64,
            question_type=QuestionType.OPEN_RESPONSE,
            extraction_status=MaterialItemExtractionStatus.READY,
            evaluation_mode=MaterialEvaluationMode.TEACHER_REVIEW,
            raw_metadata={},
        )
        for material, tag in zip(materials, ("A", "B"))
    ]
    db_session.add_all(material_items)
    db_session.flush()

    snapshots = [
        AssignmentMaterialItem(
            assignment_id=assignment.id,
            teacher_material_item_id=source.id,
            teacher_material_id=material.id,
            source_content_hash=tag.lower() * 64,
            content=f"Immutable PDF snapshot {tag}",
            order_index=0,
            snapshotted_at=now,
            question_type=QuestionType.OPEN_RESPONSE,
            evaluation_mode=MaterialEvaluationMode.TEACHER_REVIEW,
        )
        for assignment, source, material, tag in zip(assignments, material_items, materials, ("A", "B"))
    ]
    db_session.add_all(snapshots)
    db_session.flush()

    student_assignments = [
        StudentAssignment(
            assignment_id=assignment.id,
            student_id=profile.id,
            status=StudentAssignmentStatus.NOT_STARTED,
        )
        for assignment, profile in zip(assignments, (v2_domain.student_profile, v2_domain.outsider_profile))
    ]
    db_session.add_all(student_assignments)
    db_session.flush()

    assigned_items = [
        StudentAssignmentMaterialItem(
            student_assignment_id=sa.id,
            teacher_material_item_id=source.id,
            assignment_material_item_id=snap.id,
            order_index=0,
            evaluation_status="NEEDS_EVALUATION",
        )
        for sa, source, snap in zip(student_assignments, material_items, snapshots)
    ]
    db_session.add_all(assigned_items)
    db_session.commit()

    student_a_headers = auth_headers(v2_domain.student)
    student_b_headers = auth_headers(v2_domain.outsider)

    # 1. Valid PDF snapshot attempt lifecycle for Student A
    create_valid = db_client.post(
        "/api/v2/math-solutions/attempts",
        headers=student_a_headers,
        json={
            "source_kind": "TEACHER_MATERIAL",
            "context_type": "CLASSROOM_ASSIGNMENT",
            "mode": "INDEPENDENT_SOLUTION",
            "create_idempotency_key": "valid-pdf-attempt-01",
            "student_assignment_id": str(student_assignments[0].id),
            "student_assignment_material_item_id": str(assigned_items[0].id),
        },
    )
    assert create_valid.status_code == 201, create_valid.text
    assert create_valid.headers.get("cache-control") == "no-store"
    assert create_valid.headers.get("pragma") == "no-cache"
    attempt = create_valid.json()
    assert attempt["source_kind"] == "TEACHER_MATERIAL"
    assert attempt["context_type"] == "CLASSROOM_ASSIGNMENT"
    assert attempt["student_assignment_id"] == str(student_assignments[0].id)
    assert attempt["student_assignment_material_item_id"] == str(assigned_items[0].id)
    attempt_id = attempt["id"]

    # Student A can add step
    step_res = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
        json=mutation(1, step_type="DERIVATIVE_CALCULATION", content_latex="y'=6x-2"),
        headers=student_a_headers,
    )
    assert step_res.status_code == 201
    assert step_res.headers.get("cache-control") == "no-store"
    assert step_res.headers.get("pragma") == "no-cache"

    # Student A can submit
    submit_res = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/submit",
        json=mutation(2),
        headers=student_a_headers,
    )
    assert submit_res.status_code == 200
    assert submit_res.headers.get("cache-control") == "no-store"
    assert submit_res.headers.get("pragma") == "no-cache"
    assert submit_res.json()["status"] == "SUBMITTED"

    # 2. Student B tries to access Student A's assignment -> 403 ASSIGNMENT_NOT_ACCESSIBLE
    cross_sa = db_client.post(
        "/api/v2/math-solutions/attempts",
        headers=student_b_headers,
        json={
            "source_kind": "TEACHER_MATERIAL",
            "context_type": "CLASSROOM_ASSIGNMENT",
            "mode": "INDEPENDENT_SOLUTION",
            "create_idempotency_key": "cross-sa-key",
            "student_assignment_id": str(student_assignments[0].id),
            "student_assignment_material_item_id": str(assigned_items[0].id),
        },
    )
    assert cross_sa.status_code == 403
    assert cross_sa.headers.get("cache-control") == "no-store"
    assert cross_sa.headers.get("pragma") == "no-cache"
    assert cross_sa.json()["error"]["code"] == "ASSIGNMENT_NOT_ACCESSIBLE"

    # 3. Student A tries to pass Student B's material item -> 403 MATERIAL_ITEM_NOT_ACCESSIBLE
    cross_item = db_client.post(
        "/api/v2/math-solutions/attempts",
        headers=student_a_headers,
        json={
            "source_kind": "TEACHER_MATERIAL",
            "context_type": "CLASSROOM_ASSIGNMENT",
            "mode": "INDEPENDENT_SOLUTION",
            "create_idempotency_key": "cross-item-key",
            "student_assignment_id": str(student_assignments[0].id),
            "student_assignment_material_item_id": str(assigned_items[1].id),
        },
    )
    assert cross_item.status_code == 403
    assert cross_item.headers.get("cache-control") == "no-store"
    assert cross_item.headers.get("pragma") == "no-cache"
    assert cross_item.json()["error"]["code"] == "MATERIAL_ITEM_NOT_ACCESSIBLE"


def test_v2_idempotency_and_revision_conflict_zero_duplicate_writes(
    db_client: TestClient,
    db_session: Session,
    v2_domain: V2Domain,
    auth_headers,
) -> None:
    headers = auth_headers(v2_domain.student)
    create_key = f"idempotent-write-check-{uuid4().hex[:8]}"
    create_res = db_client.post(
        "/api/v2/math-solutions/attempts",
        json=create_payload(v2_domain, key=create_key),
        headers=headers,
    )
    assert create_res.status_code == 201
    attempt_id = create_res.json()["id"]

    # Initial action
    action_id = str(uuid4())
    step_action = {
        "expected_attempt_revision": 1,
        "client_action_id": action_id,
        "step_type": "CUSTOM",
        "content_latex": "f(x)=x^2",
    }
    first_step = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
        json=step_action,
        headers=headers,
    )
    assert first_step.status_code == 201

    # Record row counts in DB
    step_count_before = db_session.scalar(select(func.count(SolutionStep.id)))
    rev_count_before = db_session.scalar(select(func.count(StepRevision.id)))
    op_count_before = db_session.scalar(select(func.count(SolutionOperation.id)))
    attempt_count_before = db_session.scalar(select(func.count(SolutionAttempt.id)))

    # Replay identical step addition request
    retry_step = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
        json=step_action,
        headers=headers,
    )
    assert retry_step.status_code == 201
    assert retry_step.json() == first_step.json()

    # Assert row counts didn't increase
    assert db_session.scalar(select(func.count(SolutionStep.id))) == step_count_before
    assert db_session.scalar(select(func.count(StepRevision.id))) == rev_count_before
    assert db_session.scalar(select(func.count(SolutionOperation.id))) == op_count_before
    assert db_session.scalar(select(func.count(SolutionAttempt.id))) == attempt_count_before

    # Stale revision conflict request
    stale_action = {
        "expected_attempt_revision": 1,  # Attempt revision is now 2
        "client_action_id": str(uuid4()),
        "step_type": "CUSTOM",
        "content_latex": "f'(x)=2x",
    }
    conflict_res = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
        json=stale_action,
        headers=headers,
    )
    assert conflict_res.status_code == 409
    assert conflict_res.json()["error"]["code"] == "SOLUTION_REVISION_CONFLICT"

    # Assert row counts still didn't increase
    assert db_session.scalar(select(func.count(SolutionStep.id))) == step_count_before
    assert db_session.scalar(select(func.count(StepRevision.id))) == rev_count_before
    assert db_session.scalar(select(func.count(SolutionOperation.id))) == op_count_before
    assert db_session.scalar(select(func.count(SolutionAttempt.id))) == attempt_count_before

    # Replay attempt creation request
    replay_create = db_client.post(
        "/api/v2/math-solutions/attempts",
        json=create_payload(v2_domain, key=create_key),
        headers=headers,
    )
    assert replay_create.status_code == 201
    assert replay_create.json()["id"] == attempt_id
    assert db_session.scalar(select(func.count(SolutionAttempt.id))) == attempt_count_before


def test_v2_workspace_never_leaks_correct_answers_or_rubrics(
    db_client: TestClient,
    db_session: Session,
    v2_domain: V2Domain,
    auth_headers,
) -> None:
    headers = auth_headers(v2_domain.student)

    # Attach an approved SolutionRubric to question
    rubric = SolutionRubric(
        question_id=v2_domain.question.id,
        rubric_version=1,
        title="Classified Evaluation Criteria",
        criteria={"hidden_rule": "check_derivatives_strictly", "secret_points": 10},
        max_score=1.0,
        status="APPROVED",
    )
    db_session.add(rubric)
    db_session.commit()

    # Create attempt referencing rubric
    create_body = {
        **create_payload(v2_domain, key="rubric-redaction-test"),
        "rubric_id": str(rubric.id),
    }
    create_res = db_client.post(
        "/api/v2/math-solutions/attempts",
        json=create_body,
        headers=headers,
    )
    assert create_res.status_code == 201
    attempt_id = create_res.json()["id"]

    # Add step
    step_res = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
        json=mutation(1, step_type="DERIVATIVE_CALCULATION", content_latex="y'=3x^2"),
        headers=headers,
    )
    assert step_res.status_code == 201
    step_id = step_res.json()["steps"][0]["id"]

    # Read attempt
    get_res = db_client.get(
        f"/api/v2/math-solutions/attempts/{attempt_id}",
        headers=headers,
    )
    assert get_res.status_code == 200

    # Read step revisions
    rev_res = db_client.get(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps/{step_id}/revisions",
        headers=headers,
    )
    assert rev_res.status_code == 200

    # Submit
    submit_res = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/submit",
        json=mutation(2),
        headers=headers,
    )
    assert submit_res.status_code == 200

    secret_terms = [
        "This answer must never be exposed through workspace APIs.",
        "Teacher-only test explanation.",
        "Classified Evaluation Criteria",
        "hidden_rule",
        "check_derivatives_strictly",
        "secret_points",
    ]

    for response in [create_res, step_res, get_res, rev_res, submit_res]:
        assert response.headers.get("cache-control") == "no-store"
        assert response.headers.get("pragma") == "no-cache"
        text_content = response.text
        for term in secret_terms:
            assert term not in text_content
        data = response.json()
        if isinstance(data, dict):
            assert "correct_answer" not in data
            assert "explanation" not in data
            assert "rubric" not in data
            assert "criteria" not in data