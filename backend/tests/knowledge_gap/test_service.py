from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.curriculum.models import ProblemType, ProblemTypeConcept
from app.knowledge_gap.schemas import (
    AIGapDiagnosisOutput,
    KnowledgeGapResult,
    KnowledgeGapType,
)
from app.knowledge_gap.service import KnowledgeGapService
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.misconceptions.models import (
    MisconceptionCategory,
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.questions.models import Question, QuestionProblemType
from app.students.models import StudentProfile
from app.users.models import User
from tests.practice.conftest import PracticeContent, practice_content, practice_students, practice_user_factory, student_profile


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def inequality_prereq_concept(
    db_session: Session, practice_content: PracticeContent
) -> Concept:
    """Create prerequisite concept INEQUALITY_SOLVING linked to MONOTONICITY."""
    prereq = Concept(
        subject_id=practice_content.subject.id,
        code="INEQUALITY_SOLVING",
        name="Giải bất phương trình",
        description="Giải bất phương trình chứa tham số.",
        grade_level=10,
        order_index=1,
    )
    db_session.add(prereq)
    db_session.flush()

    relation = ConceptRelation(
        source_concept_id=prereq.id,
        target_concept_id=practice_content.concept.id,
        relation_type=RelationType.PREREQUISITE,
    )
    db_session.add(relation)
    db_session.flush()
    return prereq


@pytest.fixture
def second_direct_concept(
    db_session: Session, practice_content: PracticeContent
) -> Concept:
    """Create a second direct concept linked to the problem type for multi-concept tests."""
    c2 = Concept(
        subject_id=practice_content.subject.id,
        code="DERIVATIVE_COMPUTATION",
        name="Quy tắc tính đạo hàm",
        description="Tính đạo hàm hàm hợp và phân thức.",
        grade_level=12,
        order_index=2,
    )
    db_session.add(c2)
    db_session.flush()

    ptc = ProblemTypeConcept(
        problem_type_id=practice_content.problem_type.id,
        concept_id=c2.id,
        weight=0.5,
        is_primary=False,
    )
    # Ensure primary concept link also exists in ProblemTypeConcept
    ptc_primary = ProblemTypeConcept(
        problem_type_id=practice_content.problem_type.id,
        concept_id=practice_content.concept.id,
        weight=0.5,
        is_primary=True,
    )
    db_session.add_all([ptc, ptc_primary])
    db_session.commit()
    return c2


def _set_concept_mastery(
    db_session: Session,
    student_id: UUID,
    concept_id: UUID,
    score: float,
    *,
    confidence: float = 0.8,
    attempts: int = 5,
    correct: int = 4,
) -> StudentConceptMastery:
    now = datetime.now(timezone.utc)
    mastery = StudentConceptMastery(
        student_id=student_id,
        concept_id=concept_id,
        mastery_score=score,
        confidence=confidence,
        attempt_count=attempts,
        correct_count=correct,
        last_practiced_at=now,
    )
    db_session.merge(mastery)
    db_session.flush()
    return mastery


def _set_problem_type_mastery(
    db_session: Session,
    student_id: UUID,
    problem_type_id: UUID,
    score: float,
    *,
    confidence: float = 0.8,
    attempts: int = 5,
    correct: int = 1,
) -> StudentProblemTypeMastery:
    now = datetime.now(timezone.utc)
    mastery = StudentProblemTypeMastery(
        student_id=student_id,
        problem_type_id=problem_type_id,
        mastery_score=score,
        confidence=confidence,
        attempt_count=attempts,
        correct_count=correct,
        last_practiced_at=now,
    )
    db_session.merge(mastery)
    db_session.flush()
    return mastery


def _create_attempt_with_reasoning(
    db_session: Session,
    student_profile: StudentProfile,
    question: Question,
    *,
    student_answer: str = "Ta có y' = 3x^2 - 6mx >= 0 với mọi x thuộc R. Em giải delta nhưng không biết tìm điều kiện m.",
) -> QuestionAttempt:
    practice_session = PracticeSession(
        student_id=student_profile.id,
        subject_id=question.subject_id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    db_session.add(practice_session)
    db_session.flush()

    attempt = QuestionAttempt(
        practice_session_id=practice_session.id,
        student_id=student_profile.id,
        question_id=question.id,
        student_answer=student_answer,
        is_correct=False,
        score=0.0,
        response_time_seconds=45.0,
        attempt_number=1,
        evaluation_status=EvaluationStatus.EVALUATED,
    )
    db_session.add(attempt)
    db_session.commit()
    return attempt


# --------------------------------------------------------------------------
# 1. Prerequisite Concept Gap Test (User's Exact Example)
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_prerequisite_concept_gap_user_example(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    inequality_prereq_concept: Concept,
    settings: Settings,
) -> None:
    """User example:

    Student frequently errs in PARAMETER_MONOTONICITY,
    MONOTONICITY mastery is HIGH (0.85),
    INEQUALITY_SOLVING prerequisite mastery is LOW (0.30)
    -> PREREQUISITE_CONCEPT_GAP: INEQUALITY_SOLVING
    """
    # High mastery in direct concept MONOTONICITY
    _set_concept_mastery(
        db_session, student_profile.id, practice_content.concept.id, score=0.85
    )
    # Low mastery in prerequisite concept INEQUALITY_SOLVING
    _set_concept_mastery(
        db_session, student_profile.id, inequality_prereq_concept.id, score=0.30
    )
    # Low mastery in problem type PARAMETER_MONOTONICITY
    _set_problem_type_mastery(
        db_session, student_profile.id, practice_content.problem_type.id, score=0.25
    )
    db_session.commit()

    mock_gateway = AIGateway(provider=MockAIProvider(), settings=settings)
    service = KnowledgeGapService(db_session, gateway=mock_gateway)

    result = await service.analyze_gap(
        student_id=student_profile.id,
        problem_type_id=practice_content.problem_type.id,
    )

    assert result.gap_type == KnowledgeGapType.PREREQUISITE_CONCEPT_GAP
    assert result.target_concept_id == inequality_prereq_concept.id
    assert result.target_concept_code == "INEQUALITY_SOLVING"
    assert result.target_problem_type_id == practice_content.problem_type.id
    assert result.confidence >= 0.85
    assert "PREREQUISITE_GAP_INEQUALITY_SOLVING" in result.reason_code


# --------------------------------------------------------------------------
# 2. Current Problem Type Gap Test
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_current_problem_type_gap(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    inequality_prereq_concept: Concept,
    settings: Settings,
) -> None:
    """Direct concept is strong, prerequisite is strong,

    BUT problem type mastery is weak -> CURRENT_PROBLEM_TYPE_GAP.
    """
    # Direct concept is strong
    _set_concept_mastery(
        db_session, student_profile.id, practice_content.concept.id, score=0.80
    )
    # Prerequisite concept is also strong
    _set_concept_mastery(
        db_session, student_profile.id, inequality_prereq_concept.id, score=0.75
    )
    # Problem type itself is weak
    _set_problem_type_mastery(
        db_session, student_profile.id, practice_content.problem_type.id, score=0.30
    )
    db_session.commit()

    mock_gateway = AIGateway(provider=MockAIProvider(), settings=settings)
    service = KnowledgeGapService(db_session, gateway=mock_gateway)

    result = await service.analyze_gap(
        student_id=student_profile.id,
        problem_type_id=practice_content.problem_type.id,
    )

    assert result.gap_type == KnowledgeGapType.CURRENT_PROBLEM_TYPE_GAP
    assert result.target_problem_type_id == practice_content.problem_type.id
    assert result.confidence >= 0.80
    assert "PROBLEM_TYPE_SYNTHESIS_DEFICIT" in result.reason_code


# --------------------------------------------------------------------------
# 3. Persistent Misconception Test
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_persistent_misconception(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    settings: Settings,
) -> None:
    """Student has an active CONFIRMED misconception in scope -> PERSISTENT_MISCONCEPTION."""
    m_def = MisconceptionDefinition(
        code="PARAM_MONOTONE_EXTREMUM_CONFUSION",
        concept_id=practice_content.concept.id,
        problem_type_id=practice_content.problem_type.id,
        name="Confuses monotonic interval with extremum condition",
        description="Sets y' = 0 instead of y' >= 0 for parameter monotonicity.",
        category=MisconceptionCategory.CONCEPTUAL,
        is_active=True,
    )
    db_session.add(m_def)
    db_session.flush()

    now = datetime.now(timezone.utc)
    student_m = StudentMisconception(
        student_id=student_profile.id,
        misconception_definition_id=m_def.id,
        confidence=0.85,
        occurrence_count=3,
        status=StudentMisconceptionStatus.CONFIRMED,
        first_detected_at=now,
        last_detected_at=now,
    )
    db_session.add(student_m)
    db_session.commit()

    mock_gateway = AIGateway(provider=MockAIProvider(), settings=settings)
    service = KnowledgeGapService(db_session, gateway=mock_gateway)

    result = await service.analyze_gap(
        student_id=student_profile.id,
        problem_type_id=practice_content.problem_type.id,
    )

    assert result.gap_type == KnowledgeGapType.PERSISTENT_MISCONCEPTION
    assert result.target_concept_id == practice_content.concept.id
    assert "CONFIRMED_MISCONCEPTION" in result.reason_code


# --------------------------------------------------------------------------
# 4. Multi-Concept Gap Test
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_multi_concept_gap(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    second_direct_concept: Concept,
    settings: Settings,
) -> None:
    """Two direct concepts required by the problem type are both weak -> MULTI_CONCEPT_GAP."""
    # Weak direct concept 1
    _set_concept_mastery(
        db_session, student_profile.id, practice_content.concept.id, score=0.35
    )
    # Weak direct concept 2
    _set_concept_mastery(
        db_session, student_profile.id, second_direct_concept.id, score=0.25
    )
    # Weak problem type
    _set_problem_type_mastery(
        db_session, student_profile.id, practice_content.problem_type.id, score=0.20
    )
    db_session.commit()

    mock_gateway = AIGateway(provider=MockAIProvider(), settings=settings)
    service = KnowledgeGapService(db_session, gateway=mock_gateway)

    result = await service.analyze_gap(
        student_id=student_profile.id,
        problem_type_id=practice_content.problem_type.id,
    )

    assert result.gap_type == KnowledgeGapType.MULTI_CONCEPT_GAP
    assert result.target_problem_type_id == practice_content.problem_type.id
    assert "MULTI_DIRECT_CONCEPTS_DEFICIT" in result.reason_code


# --------------------------------------------------------------------------
# 5. Insufficient Evidence Test
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_insufficient_evidence(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    settings: Settings,
) -> None:
    """No practice attempts or mastery records exist for this student -> INSUFFICIENT_EVIDENCE."""
    mock_gateway = AIGateway(provider=MockAIProvider(), settings=settings)
    service = KnowledgeGapService(db_session, gateway=mock_gateway)

    result = await service.analyze_gap(
        student_id=student_profile.id,
        problem_type_id=practice_content.problem_type.id,
    )

    assert result.gap_type == KnowledgeGapType.INSUFFICIENT_EVIDENCE
    assert result.target_problem_type_id == practice_content.problem_type.id
    assert "INSUFFICIENT" in result.reason_code


# --------------------------------------------------------------------------
# 6. Deterministic Priority: Mock AI is NOT Called for Decisive Signals
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_deterministic_priority_does_not_call_ai(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    inequality_prereq_concept: Concept,
    settings: Settings,
) -> None:
    """When deterministic rules match clearly, AI is never invoked."""
    _set_concept_mastery(
        db_session, student_profile.id, practice_content.concept.id, score=0.85
    )
    _set_concept_mastery(
        db_session, student_profile.id, inequality_prereq_concept.id, score=0.25
    )
    _set_problem_type_mastery(
        db_session, student_profile.id, practice_content.problem_type.id, score=0.30
    )
    db_session.commit()

    mock_provider = MockAIProvider()
    mock_gateway = AIGateway(provider=mock_provider, settings=settings)
    service = KnowledgeGapService(db_session, gateway=mock_gateway)

    result = await service.analyze_gap(
        student_id=student_profile.id,
        problem_type_id=practice_content.problem_type.id,
    )

    assert result.gap_type == KnowledgeGapType.PREREQUISITE_CONCEPT_GAP
    # Mock AI was NEVER called!
    assert mock_provider.call_count == 0


# --------------------------------------------------------------------------
# 7. AI Consultation for Complex Reasoning in Borderline Data
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ai_consultation_when_borderline_and_reasoning_present(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    inequality_prereq_concept: Concept,
    settings: Settings,
) -> None:
    """When quantitative data is borderline (e.g. scores around 0.55), but recent attempt

    has rich reasoning, AI is consulted and Backend decides the final classification.
    """
    # Borderline concept score
    _set_concept_mastery(
        db_session, student_profile.id, practice_content.concept.id, score=0.55, attempts=2, correct=1
    )
    # Borderline problem type score
    _set_problem_type_mastery(
        db_session, student_profile.id, practice_content.problem_type.id, score=0.55, attempts=2, correct=1
    )
    db_session.commit()

    # Create recent attempt with explicit reasoning
    attempt = _create_attempt_with_reasoning(
        db_session,
        student_profile,
        practice_content.open_response,
        student_answer="Ta có y' = 3x^2 - 6mx. Em biết hàm đồng biến khi y' >= 0 nhưng không biết giải bất phương trình bậc 2 có tham số m.",
    )

    canned_ai_output = AIGapDiagnosisOutput(
        suggested_gap_type=KnowledgeGapType.PREREQUISITE_CONCEPT_GAP,
        target_concept_id=inequality_prereq_concept.id,
        target_problem_type_id=practice_content.problem_type.id,
        observations=[
            "Học sinh nắm được điều kiện đạo hàm y' >= 0.",
            "Lúng túng rõ ràng ở bước giải bất phương trình bậc hai chứa tham số.",
        ],
        confidence=0.88,
        reason_code="PREREQUISITE_QUADRATIC_INEQUALITY_GAP",
    )

    mock_provider = MockAIProvider(canned_structured=canned_ai_output)
    mock_gateway = AIGateway(provider=mock_provider, settings=settings)
    service = KnowledgeGapService(db_session, gateway=mock_gateway)

    result = await service.analyze_gap(
        student_id=student_profile.id,
        problem_type_id=practice_content.problem_type.id,
        recent_attempt_id=attempt.id,
        use_ai=True,
    )

    # AI was consulted
    assert mock_provider.call_count == 1
    # Backend finalized the result
    assert result.gap_type == KnowledgeGapType.PREREQUISITE_CONCEPT_GAP
    assert result.target_concept_id == inequality_prereq_concept.id
    assert result.confidence == 0.88
    assert result.metadata.get("ai_consulted") is True


# --------------------------------------------------------------------------
# 8. Error Handling: 404 for Unknown ProblemType or Student
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_problem_type_or_student_not_found(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    settings: Settings,
) -> None:
    mock_gateway = AIGateway(provider=MockAIProvider(), settings=settings)
    service = KnowledgeGapService(db_session, gateway=mock_gateway)

    from uuid import uuid4

    # Unknown ProblemType
    with pytest.raises(ApplicationError) as exc:
        await service.analyze_gap(
            student_id=student_profile.id,
            problem_type_id=uuid4(),
        )
    assert exc.value.status_code == 404
    assert exc.value.code == "PROBLEM_TYPE_NOT_FOUND"

    # Unknown Student
    with pytest.raises(ApplicationError) as exc_s:
        await service.analyze_gap(
            student_id=uuid4(),
            problem_type_id=practice_content.problem_type.id,
        )
    assert exc_s.value.status_code == 404
    assert exc_s.value.code == "STUDENT_NOT_FOUND"


# --------------------------------------------------------------------------
# 9. AI Consultation Whitelist Rejection
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ai_consultation_whitelist_rejection(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    settings: Settings,
) -> None:
    """If AI invents an out-of-scope concept ID, the backend filters it out to None."""
    _set_concept_mastery(
        db_session, student_profile.id, practice_content.concept.id, score=0.55, attempts=2, correct=1
    )
    _set_problem_type_mastery(
        db_session, student_profile.id, practice_content.problem_type.id, score=0.55, attempts=2, correct=1
    )
    db_session.commit()

    attempt = _create_attempt_with_reasoning(
        db_session,
        student_profile,
        practice_content.open_response,
        student_answer="Lời giải chi tiết các bước tính toán và phân tích hàm số rất phức tạp.",
    )

    arbitrary_concept_id = uuid4()
    canned_ai_output = AIGapDiagnosisOutput(
        suggested_gap_type=KnowledgeGapType.PREREQUISITE_CONCEPT_GAP,
        target_concept_id=arbitrary_concept_id,
        target_problem_type_id=practice_content.problem_type.id,
        observations=["Observations from AI."],
        confidence=0.85,
        reason_code="OUT_OF_SCOPE_CONCEPT",
    )

    mock_provider = MockAIProvider(canned_structured=canned_ai_output)
    mock_gateway = AIGateway(provider=mock_provider, settings=settings)
    service = KnowledgeGapService(db_session, gateway=mock_gateway)

    result = await service.analyze_gap(
        student_id=student_profile.id,
        problem_type_id=practice_content.problem_type.id,
        recent_attempt_id=attempt.id,
        use_ai=True,
    )

    # Backend filtered out the arbitrary concept ID
    assert result.target_concept_id is None
    assert result.target_concept_code is None


# --------------------------------------------------------------------------
# 10. AI Failure Fallback
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ai_failure_graceful_fallback(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    settings: Settings,
) -> None:
    """If the AI call encounters an error, backend falls back gracefully without crashing."""
    _set_concept_mastery(
        db_session, student_profile.id, practice_content.concept.id, score=0.55, attempts=2, correct=1
    )
    _set_problem_type_mastery(
        db_session, student_profile.id, practice_content.problem_type.id, score=0.55, attempts=2, correct=1
    )
    db_session.commit()

    attempt = _create_attempt_with_reasoning(
        db_session,
        student_profile,
        practice_content.open_response,
        student_answer="Lời giải chi tiết các bước tính toán và phân tích hàm số rất phức tạp.",
    )

    # Simulate 503 service unavailable
    mock_provider = MockAIProvider(service_unavailable_failures=5)
    mock_gateway = AIGateway(provider=mock_provider, settings=settings)
    service = KnowledgeGapService(db_session, gateway=mock_gateway)

    result = await service.analyze_gap(
        student_id=student_profile.id,
        problem_type_id=practice_content.problem_type.id,
        recent_attempt_id=attempt.id,
        use_ai=True,
    )

    assert result is not None
    assert isinstance(result, KnowledgeGapResult)


# --------------------------------------------------------------------------
# 11. Reasoning Absent Skips AI
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_reasoning_absent_skips_ai(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    settings: Settings,
) -> None:
    """When the student answer is a bare option (e.g. 'A') without reasoning, AI is not called."""
    _set_concept_mastery(
        db_session, student_profile.id, practice_content.concept.id, score=0.55, attempts=2, correct=1
    )
    _set_problem_type_mastery(
        db_session, student_profile.id, practice_content.problem_type.id, score=0.55, attempts=2, correct=1
    )
    db_session.commit()

    # Attempt with no reasoning (bare 'B')
    attempt = _create_attempt_with_reasoning(
        db_session,
        student_profile,
        practice_content.mcq,
        student_answer="B",
    )

    mock_provider = MockAIProvider()
    mock_gateway = AIGateway(provider=mock_provider, settings=settings)
    service = KnowledgeGapService(db_session, gateway=mock_gateway)

    result = await service.analyze_gap(
        student_id=student_profile.id,
        problem_type_id=practice_content.problem_type.id,
        recent_attempt_id=attempt.id,
        use_ai=True,
    )

    # AI should not be called because there is no reasoning
    assert mock_provider.call_count == 0
    assert result.metadata.get("ai_consulted") is not True
