from uuid import UUID
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.mastery.evidence import MasteryAttemptEvidencePublisher
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.practice.evidence import AttemptEvaluatedEvidence
from app.practice.models import EvaluationStatus, QuestionAttempt
from app.practice.open_response_evaluator import AIOpenResponseEvaluationService
from app.practice.open_response_schemas import OpenResponseEvaluationOutput
from app.practice.schemas import PracticeAnswerCreate, PracticeSessionCreate
from app.practice.service import PracticeService
from app.questions.models import QuestionType
from app.users.models import Role, User
from tests.practice.conftest import PracticeContent


class RecordingPublisher:
    def __init__(self) -> None:
        self.published_events: list[AttemptEvaluatedEvidence] = []

    def publish(self, evidence: AttemptEvaluatedEvidence, session: Session) -> None:
        self.published_events.append(evidence)


def _create_open_response_attempt(
    service: PracticeService,
    student: User,
    content: PracticeContent,
    answer_text: str = "Hàm số đồng biến trên R vì đạo hàm f'(x) = 3x^2 + 1 > 0 với mọi x.",
) -> QuestionAttempt:
    practice = service.create_session(
        student,
        PracticeSessionCreate(
            subject_id=content.subject.id,
            session_type="PRACTICE",
            problem_type_ids=[content.problem_type.id],
            concept_ids=[content.concept.id],
        ),
    )
    attempt = service.answer(
        student,
        practice.id,
        PracticeAnswerCreate(
            question_id=content.open_response.id,
            student_answer=answer_text,
            response_time_seconds=45.0,
            hint_count=1,
        ),
    )
    assert attempt.evaluation_status == EvaluationStatus.NEEDS_EVALUATION
    return attempt


# --------------------------------------------------------------------------
# 1. State & Format Guardrail Tests
# --------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ai_evaluator_rejects_non_needs_evaluation_status(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
    settings: Settings,
) -> None:
    student, _ = practice_students
    service = PracticeService(db_session)
    practice = service.create_session(
        student,
        PracticeSessionCreate(
            subject_id=practice_content.subject.id,
            session_type="PRACTICE",
            problem_type_ids=[practice_content.problem_type.id],
            concept_ids=[practice_content.concept.id],
        ),
    )
    # Answer MCQ question (auto-evaluated)
    attempt = service.answer(
        student,
        practice.id,
        PracticeAnswerCreate(
            question_id=practice_content.mcq.id,
            student_answer="A",
        ),
    )
    assert attempt.evaluation_status == EvaluationStatus.AUTO_EVALUATED

    gateway = AIGateway(provider=MockAIProvider(), settings=settings)
    eval_service = AIOpenResponseEvaluationService(db_session, gateway)

    with pytest.raises(ApplicationError) as exc_info:
        await eval_service.evaluate_attempt(attempt.id)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "INVALID_EVALUATION_STATUS"


@pytest.mark.anyio
async def test_ai_evaluator_blocks_mcq_and_true_false_questions(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
    settings: Settings,
) -> None:
    student, _ = practice_students
    service = PracticeService(db_session)
    practice = service.create_session(
        student,
        PracticeSessionCreate(
            subject_id=practice_content.subject.id,
            session_type="PRACTICE",
            problem_type_ids=[practice_content.problem_type.id],
            concept_ids=[practice_content.concept.id],
        ),
    )
    attempt = service.answer(
        student,
        practice.id,
        PracticeAnswerCreate(
            question_id=practice_content.true_false.id,
            student_answer="TRUE",
        ),
    )
    # Even if forced to NEEDS_EVALUATION, question type check must strictly block it
    attempt.evaluation_status = EvaluationStatus.NEEDS_EVALUATION
    db_session.commit()

    gateway = AIGateway(provider=MockAIProvider(), settings=settings)
    eval_service = AIOpenResponseEvaluationService(db_session, gateway)

    with pytest.raises(ApplicationError) as exc_info:
        await eval_service.evaluate_attempt(attempt.id)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "OBJECTIVE_QUESTION_AI_BLOCKED"


# --------------------------------------------------------------------------
# 2. Whitelist Validation Tests (AI cannot invent codes)
# --------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ai_evaluator_fails_when_ai_hallucinates_unauthorized_concept(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
    settings: Settings,
) -> None:
    student, _ = practice_students
    practice_service = PracticeService(db_session)
    attempt = _create_open_response_attempt(practice_service, student, practice_content)

    canned_output = OpenResponseEvaluationOutput(
        score=0.9,
        is_correct=True,
        reason="Bài làm xuất sắc nhưng chứa mã lạ.",
        evidence="f'(x) = 3x^2 + 1 > 0",
        confidence=0.95,
        demonstrated_concept_codes=["NON_EXISTENT_HALLUCINATED_CONCEPT"],
    )
    mock_provider = MockAIProvider(canned_structured=canned_output)
    gateway = AIGateway(provider=mock_provider, settings=settings)
    eval_service = AIOpenResponseEvaluationService(db_session, gateway)

    with pytest.raises(ApplicationError) as exc_info:
        await eval_service.evaluate_attempt(attempt.id)
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "UNAUTHORIZED_CONCEPT_CODE"


@pytest.mark.anyio
async def test_ai_evaluator_fails_when_ai_hallucinates_unauthorized_learning_outcome(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
    settings: Settings,
) -> None:
    student, _ = practice_students
    practice_service = PracticeService(db_session)
    attempt = _create_open_response_attempt(practice_service, student, practice_content)

    canned_output = OpenResponseEvaluationOutput(
        score=0.9,
        is_correct=True,
        reason="Bài làm tốt.",
        evidence="f'(x) > 0",
        confidence=0.92,
        demonstrated_learning_outcome_codes=["LO_HALLUCINATED_XYZ"],
    )
    mock_provider = MockAIProvider(canned_structured=canned_output)
    gateway = AIGateway(provider=mock_provider, settings=settings)
    eval_service = AIOpenResponseEvaluationService(db_session, gateway)

    with pytest.raises(ApplicationError) as exc_info:
        await eval_service.evaluate_attempt(attempt.id)
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "UNAUTHORIZED_LEARNING_OUTCOME_CODE"


# --------------------------------------------------------------------------
# 3. High Confidence & Mastery Engine Delegation Tests
# --------------------------------------------------------------------------

@pytest.mark.anyio
async def test_high_confidence_evaluates_attempt_and_delegates_to_mastery_engine(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
    settings: Settings,
) -> None:
    student, _ = practice_students
    practice_service = PracticeService(db_session)
    attempt = _create_open_response_attempt(practice_service, student, practice_content)

    valid_concept_code = practice_content.concept.code
    valid_lo_code = practice_content.learning_outcome.code

    canned_output = OpenResponseEvaluationOutput(
        score=0.95,
        is_correct=True,
        reason="Lập luận chặt chẽ, tính đạo hàm chính xác và kết luận đúng tính đơn điệu.",
        evidence="Đạo hàm f'(x) = 3x^2 + 1 > 0 với mọi x thuộc R.",
        confidence=0.88,
        demonstrated_concept_codes=[valid_concept_code],
        demonstrated_learning_outcome_codes=[valid_lo_code],
    )
    mock_provider = MockAIProvider(canned_structured=canned_output)
    gateway = AIGateway(provider=mock_provider, settings=settings)
    recording_publisher = RecordingPublisher()

    eval_service = AIOpenResponseEvaluationService(
        db_session,
        gateway,
        evidence_publisher=recording_publisher,
    )

    evaluated = await eval_service.evaluate_attempt(attempt.id, confidence_threshold=0.70)

    # 1. Attempt updated properly
    assert evaluated.evaluation_status == EvaluationStatus.EVALUATED
    assert evaluated.score == 0.95
    assert evaluated.is_correct is True
    assert evaluated.evaluation_details is not None
    assert evaluated.evaluation_details["confidence"] == 0.88
    assert evaluated.evaluation_details["demonstrated_concept_codes"] == [valid_concept_code]

    # 2. Mastery evidence published to publisher
    assert len(recording_publisher.published_events) == 1
    event = recording_publisher.published_events[0]
    assert event.attempt_id == attempt.id
    assert event.is_correct is True
    assert event.score == 0.95
    assert event.concept_ids == (practice_content.concept.id,)
    assert event.problem_type_ids == (practice_content.problem_type.id,)


@pytest.mark.anyio
async def test_high_confidence_updates_real_mastery_tables_deterministically(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
    settings: Settings,
) -> None:
    student, _ = practice_students
    practice_service = PracticeService(db_session)
    attempt = _create_open_response_attempt(practice_service, student, practice_content)

    canned_output = OpenResponseEvaluationOutput(
        score=1.0,
        is_correct=True,
        reason="Hoàn thành xuất sắc toàn bộ yêu cầu bài toán.",
        evidence="f'(x) = 3x^2 + 1 > 0",
        confidence=0.90,
        demonstrated_concept_codes=[practice_content.concept.code],
    )
    mock_provider = MockAIProvider(canned_structured=canned_output)
    gateway = AIGateway(provider=mock_provider, settings=settings)

    # Use default real MasteryAttemptEvidencePublisher
    real_mastery_publisher = MasteryAttemptEvidencePublisher()
    eval_service = AIOpenResponseEvaluationService(
        db_session, gateway, evidence_publisher=real_mastery_publisher
    )

    await eval_service.evaluate_attempt(attempt.id)

    # Verify deterministic mastery rows were updated by MasteryEngine
    concept_mastery = db_session.scalar(
        select(StudentConceptMastery).where(
            StudentConceptMastery.student_id == attempt.student_id,
            StudentConceptMastery.concept_id == practice_content.concept.id,
        )
    )
    assert concept_mastery is not None
    assert concept_mastery.attempt_count == 1
    assert concept_mastery.correct_count == 1
    assert concept_mastery.mastery_score > 0.0

    pt_mastery = db_session.scalar(
        select(StudentProblemTypeMastery).where(
            StudentProblemTypeMastery.student_id == attempt.student_id,
            StudentProblemTypeMastery.problem_type_id == practice_content.problem_type.id,
        )
    )
    assert pt_mastery is not None
    assert pt_mastery.attempt_count == 1


# --------------------------------------------------------------------------
# 4. Low Confidence & Teacher Review Branching Tests
# --------------------------------------------------------------------------

@pytest.mark.anyio
async def test_low_confidence_marks_needs_teacher_review_and_skips_mastery(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
    settings: Settings,
) -> None:
    student, _ = practice_students
    practice_service = PracticeService(db_session)
    attempt = _create_open_response_attempt(practice_service, student, practice_content)

    # Low confidence: 0.55 < threshold 0.70
    canned_output = OpenResponseEvaluationOutput(
        score=0.6,
        is_correct=False,
        reason="Bài làm mơ hồ, bước biến đổi chưa rõ ràng.",
        evidence="f'(x) > 0 (?)",
        confidence=0.55,
        weak_concept_codes=[practice_content.concept.code],
    )
    mock_provider = MockAIProvider(canned_structured=canned_output)
    gateway = AIGateway(provider=mock_provider, settings=settings)
    recording_publisher = RecordingPublisher()

    eval_service = AIOpenResponseEvaluationService(
        db_session, gateway, evidence_publisher=recording_publisher
    )

    evaluated = await eval_service.evaluate_attempt(attempt.id, confidence_threshold=0.70)

    # 1. Flagged as NEEDS_TEACHER_REVIEW
    assert evaluated.evaluation_status == EvaluationStatus.NEEDS_TEACHER_REVIEW
    assert evaluated.score == 0.6
    assert evaluated.is_correct is False
    assert evaluated.evaluation_details["confidence"] == 0.55

    # 2. Mastery Engine NOT called
    assert len(recording_publisher.published_events) == 0

    # 3. No mastery rows created
    mastery = db_session.scalar(
        select(StudentConceptMastery).where(
            StudentConceptMastery.student_id == attempt.student_id,
            StudentConceptMastery.concept_id == practice_content.concept.id,
        )
    )
    assert mastery is None


# --------------------------------------------------------------------------
# 5. API Endpoint Integration Tests
# --------------------------------------------------------------------------

def test_ai_evaluate_attempt_api_authorized(
    db_client: TestClient,
    db_session: Session,
    practice_students: tuple[User, User],
    practice_bearer: any,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    practice_service = PracticeService(db_session)
    attempt = _create_open_response_attempt(practice_service, student, practice_content)

    headers = practice_bearer(student)
    response = db_client.post(
        f"/practice/attempts/{attempt.id}/ai-evaluate",
        headers=headers,
        json={"rubric": "Chấm điểm từng bước", "confidence_threshold": 0.70},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(attempt.id)
    assert data["evaluation_status"] in ["EVALUATED", "NEEDS_TEACHER_REVIEW"]
    assert data["evaluation_details"] is not None


def test_ai_evaluate_attempt_api_forbidden_for_other_student(
    db_client: TestClient,
    db_session: Session,
    practice_students: tuple[User, User],
    practice_bearer: any,
    practice_content: PracticeContent,
) -> None:
    student, outsider = practice_students
    practice_service = PracticeService(db_session)
    attempt = _create_open_response_attempt(practice_service, student, practice_content)

    # Outsider student tries to trigger evaluation for another student's attempt
    headers = practice_bearer(outsider)
    response = db_client.post(
        f"/practice/attempts/{attempt.id}/ai-evaluate",
        headers=headers,
        json={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCESS_DENIED"
