from uuid import UUID, uuid4
import pytest
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
from app.core.config import Settings
from app.learning_evidence.models import LearningEvidenceEvent
from app.math_ink.schemas import InkPageWrite, InkPoint, InkStroke
from app.math_ink.service import MathInkService
from app.math_solutions.models import SolutionAttempt, SolutionStep
from app.math_solutions.schemas import StepKind
from app.math_solutions.service import MathSolutionService
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.questions.models import Question, QuestionStatus, QuestionType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

PASSWORD = "Math-OCR-Test-Password-2026!"


@pytest.fixture
def ocr_fixture(db_session: Session):
    users = UserService(db_session)

    student_user = users.create_user(
        UserCreate(
            email="ocr-student@example.com",
            password=PASSWORD,
            full_name="OCR Student",
            role=Role.STUDENT,
        )
    )
    outsider_user = users.create_user(
        UserCreate(
            email="ocr-outsider@example.com",
            password=PASSWORD,
            full_name="OCR Outsider",
            role=Role.STUDENT,
        )
    )
    teacher_user = users.create_user(
        UserCreate(
            email="ocr-teacher@example.com",
            password=PASSWORD,
            full_name="OCR Teacher",
            role=Role.TEACHER,
        )
    )

    profile = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student_user.id)
    )
    assert profile is not None

    subject = Subject(code="MATH-OCR-12", name="Math OCR Grade 12", grade_level=12)
    db_session.add(subject)
    db_session.flush()

    question = Question(
        subject_id=subject.id,
        content="Calculate integral \\int (3x^2 - 2x + 1) dx",
        question_type=QuestionType.OPEN_RESPONSE,
        difficulty=0.5,
        correct_answer=None,
        explanation="Test explanation",
        source_type="TEST",
        exam_weight=0.5,
        status=QuestionStatus.APPROVED,
        created_by=teacher_user.id,
    )
    db_session.add(question)
    db_session.flush()

    practice = PracticeSession(
        student_id=profile.id,
        subject_id=subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    db_session.add(practice)
    db_session.commit()

    attempt_dict = MathSolutionService(db_session).create(
        student_user.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        mode="INDEPENDENT_SOLUTION",
        create_idempotency_key="ocr-attempt-key",
        question_id=question.id,
        practice_session_id=practice.id,
    )

    return {
        "student": student_user,
        "outsider": outsider_user,
        "teacher": teacher_user,
        "attempt_id": UUID(attempt_dict["id"]),
    }


def auth_header(db_session: Session, settings: Settings, user: User) -> dict[str, str]:
    pair = AuthService(db_session, settings).login(
        LoginRequest(email=user.email, password=PASSWORD)
    )
    return {"Authorization": f"Bearer {pair.access_token}"}


def test_ocr_requires_student_role_and_ownership(
    db_client: TestClient, db_session: Session, settings: Settings, ocr_fixture
):
    attempt_id = ocr_fixture["attempt_id"]
    payload = {"page_index": 0}

    # 1. Unauthenticated -> 401
    resp = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/ocr/recognize",
        json=payload,
    )
    assert resp.status_code == 401

    # 2. Teacher -> 403
    t_headers = auth_header(db_session, settings, ocr_fixture["teacher"])
    resp = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/ocr/recognize",
        json=payload,
        headers=t_headers,
    )
    assert resp.status_code == 403

    # 3. Outsider student -> 404 (ownership check)
    o_headers = auth_header(db_session, settings, ocr_fixture["outsider"])
    resp = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/ocr/recognize",
        json=payload,
        headers=o_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ATTEMPT_NOT_FOUND"


def test_ocr_empty_strokes_and_filter_validation(
    db_client: TestClient, db_session: Session, settings: Settings, ocr_fixture
):
    attempt_id = ocr_fixture["attempt_id"]
    headers = auth_header(db_session, settings, ocr_fixture["student"])

    # Attempt has page 0 with 0 strokes initially
    resp = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/ocr/recognize",
        json={"page_index": 0},
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "NO_STROKES_FOR_OCR"

    # Add strokes to page 0
    stroke_id_1 = uuid4()
    stroke_id_2 = uuid4()
    stroke_1 = InkStroke(
        id=stroke_id_1,
        tool="PEN",
        color="#112233",
        width=2,
        points=[InkPoint(x=0.1, y=0.1), InkPoint(x=0.2, y=0.2)],
    )
    stroke_2 = InkStroke(
        id=stroke_id_2,
        tool="PEN",
        color="#112233",
        width=2,
        points=[InkPoint(x=0.3, y=0.3), InkPoint(x=0.4, y=0.4)],
    )
    ink_svc = MathInkService(db_session)
    ink_svc.save_page(
        ocr_fixture["student"].id,
        attempt_id,
        0,
        InkPageWrite(
            expected_document_revision=0,
            client_action_id=uuid4(),
            strokes=[stroke_1, stroke_2],
        ),
    )

    # Filtering with non-existent stroke ID returns 422
    resp = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/ocr/recognize",
        json={"page_index": 0, "stroke_ids": [str(uuid4())]},
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "NO_STROKES_FOR_OCR"

    # Filtering with valid stroke ID returns recognition
    resp = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/ocr/recognize",
        json={"page_index": 0, "stroke_ids": [str(stroke_id_1)]},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence"] > 0.8
    assert "latex" in data
    assert "suggested_step_type" in data


def test_ocr_topic_hints_grade12(
    db_client: TestClient, db_session: Session, settings: Settings, ocr_fixture
):
    attempt_id = ocr_fixture["attempt_id"]
    headers = auth_header(db_session, settings, ocr_fixture["student"])

    # Prepare 1 stroke
    stroke_1 = InkStroke(
        id=uuid4(),
        tool="PEN",
        color="#112233",
        width=2,
        points=[InkPoint(x=0.1, y=0.1), InkPoint(x=0.2, y=0.2)],
    )
    MathInkService(db_session).save_page(
        ocr_fixture["student"].id,
        attempt_id,
        0,
        InkPageWrite(
            expected_document_revision=0,
            client_action_id=uuid4(),
            strokes=[stroke_1],
        ),
    )

    topics_expected = [
        ("CALCULUS_INTEGRAL", "\\int (3x^2 - 2x + 1)", StepKind.EXPLANATION),
        ("CALCULUS_DERIVATIVE", "y' = 3x^2 - 6x", StepKind.DERIVATIVE_CALCULATION),
        ("SPATIAL_GEOMETRY", "\\vec{n}_{(P)}", StepKind.EXPLANATION),
        ("PROBABILITY", "P(A|B)", StepKind.EXPLANATION),
    ]

    for topic, latex_substr, expected_kind in topics_expected:
        resp = db_client.post(
            f"/api/v2/math-solutions/attempts/{attempt_id}/ocr/recognize",
            json={"page_index": 0, "hint_topic": topic},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert latex_substr in data["latex"]
        assert data["suggested_step_type"] == expected_kind.value
        assert data["confidence"] >= 0.90
        assert len(data["detected_symbols"]) > 0


def test_ocr_invariant_never_mutates_steps_or_mastery(
    db_client: TestClient, db_session: Session, settings: Settings, ocr_fixture
):
    """
    CRITICAL INVARIANT:
    OCR is purely an advisory suggestion tool.
    Calling /ocr/recognize must NEVER:
    1. Create a SolutionStep record.
    2. Mutate attempt.attempt_revision.
    3. Emit LearningEvidenceEvent or mutate mastery.
    """
    attempt_id = ocr_fixture["attempt_id"]
    headers = auth_header(db_session, settings, ocr_fixture["student"])

    stroke_1 = InkStroke(
        id=uuid4(),
        tool="PEN",
        color="#112233",
        width=2,
        points=[InkPoint(x=0.1, y=0.1), InkPoint(x=0.2, y=0.2)],
    )
    MathInkService(db_session).save_page(
        ocr_fixture["student"].id,
        attempt_id,
        0,
        InkPageWrite(
            expected_document_revision=0,
            client_action_id=uuid4(),
            strokes=[stroke_1],
        ),
    )

    attempt_before = db_session.get(SolutionAttempt, attempt_id)
    rev_before = attempt_before.attempt_revision_number
    step_count_before = db_session.scalar(
        select(func.count()).select_from(SolutionStep).where(SolutionStep.attempt_id == attempt_id)
    )
    evidence_count_before = db_session.scalar(
        select(func.count()).select_from(LearningEvidenceEvent)
    )

    # Both the normal suggestion and an on-demand alternative request are read-only.
    for include_alternatives in (False, True):
        resp = db_client.post(
            f"/api/v2/math-solutions/attempts/{attempt_id}/ocr/recognize",
            json={"page_index": 0, "hint_topic": "CALCULUS_INTEGRAL",
                  "include_alternatives": include_alternatives},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["alternative_latex"] == []

    db_session.expire_all()
    attempt_after = db_session.get(SolutionAttempt, attempt_id)
    assert attempt_after.attempt_revision_number == rev_before

    step_count_after = db_session.scalar(
        select(func.count()).select_from(SolutionStep).where(SolutionStep.attempt_id == attempt_id)
    )
    assert step_count_after == step_count_before == 0

    evidence_count_after = db_session.scalar(
        select(func.count()).select_from(LearningEvidenceEvent)
    )
    assert evidence_count_after == evidence_count_before


def _workspace_png_ink_payload(*, revision: int, pen_id: UUID, highlight_id: UUID | None = None) -> dict:
    """Serialized browser Canvas stroke payload sent through the Math Ink API."""
    strokes = [{
        "id": str(pen_id), "tool": "PEN", "color": "#112233", "width": 2,
        "points": [{"x": 0.1, "y": 0.2, "pressure": 0.5},
                   {"x": 0.2, "y": 0.3, "pressure": 0.5}],
    }]
    if highlight_id is not None:
        strokes.append({
            "id": str(highlight_id), "tool": "HIGHLIGHTER", "color": "#ffff00",
            "width": 12, "points": [{"x": 0.15, "y": 0.25}],
        })
    return {
        "expected_document_revision": revision,
        "client_action_id": str(uuid4()),
        "strokes": strokes,
    }


def test_workspace_saved_ink_ocr_requires_manual_confirmation_and_persists_step(
    db_client: TestClient, db_session: Session, settings: Settings, ocr_fixture,
):
    """API vertical slice: Canvas JSON -> durable ink -> OCR -> manual step -> reload.

    The test adapter is deterministic and intentionally does NOT prove model accuracy
    or exercise a live Next.js/browser session.
    """
    aid = ocr_fixture["attempt_id"]
    url = f"/api/v2/math-solutions/attempts/{aid}"
    owner = auth_header(db_session, settings, ocr_fixture["student"])
    other = auth_header(db_session, settings, ocr_fixture["outsider"])
    teacher = auth_header(db_session, settings, ocr_fixture["teacher"])
    pen, highlight = uuid4(), uuid4()

    before = db_client.get(url, headers=owner)
    assert before.status_code == 200
    starting_revision = before.json()["attempt_revision_number"]
    assert before.json()["steps"] == []

    save = db_client.put(
        f"{url}/ink/pages/0",
        headers=owner,
        json=_workspace_png_ink_payload(revision=0, pen_id=pen, highlight_id=highlight),
    )
    assert save.status_code == 200, save.text
    assert save.json()["document_revision"] == 1
    assert save.headers.get("cache-control") == "no-store"

    # Browser reload reads persisted ink, not a transient client-only draft.
    read_back = db_client.get(f"{url}/ink/pages/0", headers=owner)
    assert read_back.status_code == 200
    assert read_back.json()["document_revision"] == 1
    assert {s["id"] for s in read_back.json()["strokes"]} == {str(pen), str(highlight)}
    assert read_back.headers.get("cache-control") == "no-store"

    # Unauthenticated, teacher, and other students may not read or change ink.
    assert db_client.get(f"{url}/ink/pages/0").status_code == 401
    assert db_client.get(f"{url}/ink/pages/0", headers=teacher).status_code == 403
    assert db_client.get(f"{url}/ink/pages/0", headers=other).status_code == 404
    assert db_client.post(f"{url}/steps", headers=other, json={
        "expected_attempt_revision": starting_revision, "client_action_id": str(uuid4()),
        "step_type": "EXPLANATION", "content_latex": "x+1",
    }).status_code == 404

    evidence_before = db_session.scalar(select(func.count()).select_from(LearningEvidenceEvent))
    suggestion = db_client.post(
        f"{url}/ocr/recognize", headers=owner,
        json={"page_index": 0, "stroke_ids": [str(pen)]},
    )
    assert suggestion.status_code == 200, suggestion.text
    assert suggestion.json()["latex"]
    assert suggestion.headers.get("cache-control") == "no-store"

    # The recognition request does NOT create a solution step or learning evidence.
    after_ocr = db_client.get(url, headers=owner)
    assert after_ocr.status_code == 200
    assert after_ocr.json()["steps"] == []
    assert after_ocr.json()["attempt_revision_number"] == starting_revision
    assert db_session.scalar(select(func.count()).select_from(LearningEvidenceEvent)) == evidence_before

    # The student actively edits and confirms the suggestion, then saves a step.
    corrected = r"\\frac{1}{x+1}"
    action_id = str(uuid4())
    mutation = {
        "expected_attempt_revision": starting_revision,
        "client_action_id": action_id, "step_type": "EXPLANATION",
        "content_latex": corrected, "explanation_text": "Đã đối chiếu nét viết",
    }
    confirmed = db_client.post(f"{url}/steps", headers=owner, json=mutation)
    assert confirmed.status_code == 201, confirmed.text
    assert confirmed.json()["attempt_revision_number"] == starting_revision + 1
    assert len(confirmed.json()["steps"]) == 1
    assert confirmed.json()["steps"][0]["content_latex"] == corrected

    # Retry after a network timeout must not duplicate the confirmed step.
    retry = db_client.post(f"{url}/steps", headers=owner, json=mutation)
    assert retry.status_code == 201
    assert retry.json()["attempt_revision_number"] == starting_revision + 1
    assert len(retry.json()["steps"]) == 1

    reload = db_client.get(url, headers=owner)
    assert reload.status_code == 200
    assert len(reload.json()["steps"]) == 1
    assert reload.json()["steps"][0]["content_latex"] == corrected
    assert db_session.scalar(select(func.count()).select_from(LearningEvidenceEvent)) == evidence_before


def test_workspace_conflicting_ink_save_preserves_server_document_and_blocks_stale_ocr(
    db_client: TestClient, db_session: Session, settings: Settings, ocr_fixture,
):
    """A failed optimistic save never makes unpersisted Canvas strokes OCR-visible."""
    aid = ocr_fixture["attempt_id"]
    url = f"/api/v2/math-solutions/attempts/{aid}"
    owner = auth_header(db_session, settings, ocr_fixture["student"])
    old_pen, newer_pen = uuid4(), uuid4()

    first = db_client.put(f"{url}/ink/pages/0", headers=owner,
                          json=_workspace_png_ink_payload(revision=0, pen_id=old_pen))
    assert first.status_code == 200

    stale = db_client.put(f"{url}/ink/pages/0", headers=owner,
                          json=_workspace_png_ink_payload(revision=0, pen_id=newer_pen))
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "INK_REVISION_CONFLICT"

    persisted = db_client.get(f"{url}/ink/pages/0", headers=owner)
    assert persisted.status_code == 200
    assert persisted.json()["document_revision"] == 1
    assert [s["id"] for s in persisted.json()["strokes"]] == [str(old_pen)]

    unsaved_ocr = db_client.post(f"{url}/ocr/recognize", headers=owner,
                                 json={"page_index": 0, "stroke_ids": [str(newer_pen)]})
    assert unsaved_ocr.status_code == 422
    assert unsaved_ocr.json()["error"]["code"] == "NO_STROKES_FOR_OCR"
    assert db_client.post(f"{url}/ocr/recognize", headers=owner,
                          json={"page_index": 0, "stroke_ids": [str(old_pen)]}).status_code == 200
    assert db_client.get(url, headers=owner).json()["steps"] == []
