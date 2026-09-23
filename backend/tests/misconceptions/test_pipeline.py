from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.config import Settings
from app.curriculum.models import Chapter, ProblemType, Topic
from app.misconceptions.deterministic_rules import has_reasoning
from app.misconceptions.models import (
    MisconceptionCategory,
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.misconceptions.pipeline import MisconceptionPipeline
from app.misconceptions.schemas import (
    MisconceptionAnalysisOutput,
    MisconceptionPipelineResult,
)
from app.misconceptions.service import MisconceptionService
from app.misconceptions.taxonomy import TaxonomyScoper
from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role, User
from tests.practice.conftest import PracticeContent


# --------------------------------------------------------------------------
# Fixtures & Helpers
# --------------------------------------------------------------------------


@pytest.fixture
def prerequisite_concept(
    db_session: Session, practice_content: PracticeContent
) -> Concept:
    """Create a prerequisite concept linked to the practice question's concept."""
    prereq = Concept(
        subject_id=practice_content.subject.id,
        code="BASIC_FUNCTION_LIMITS",
        name="Giới hạn hàm số cơ bản",
        description="Khái niệm giới hạn hàm số.",
        grade_level=11,
        order_index=0,
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
def unrelated_concept(db_session: Session, practice_content: PracticeContent) -> Concept:
    """Create an unrelated concept that should NOT be in the question's scoped taxonomy."""
    unrelated = Concept(
        subject_id=practice_content.subject.id,
        code="UNRELATED_SOLID_GEOMETRY",
        name="Hình học không gian cổ điển",
        description="Khối đa diện và thể tích.",
        grade_level=12,
        order_index=5,
    )
    db_session.add(unrelated)
    db_session.flush()
    return unrelated


@pytest.fixture
def setup_taxonomy(
    db_session: Session,
    practice_content: PracticeContent,
    prerequisite_concept: Concept,
    unrelated_concept: Concept,
) -> dict[str, MisconceptionDefinition]:
    """Create scoped and unscoped misconception definitions."""
    # 1. Primary concept misconception
    m_derivative = MisconceptionDefinition(
        code="DERIVATIVE_SIGN_DIRECTION",
        concept_id=practice_content.concept.id,
        problem_type_id=practice_content.problem_type.id,
        name="Derivative sign and monotonic direction",
        description="Treats a negative derivative as increasing or positive as decreasing.",
        category=MisconceptionCategory.CONCEPTUAL,
        is_active=True,
    )
    # 2. Prerequisite concept misconception
    m_prereq = MisconceptionDefinition(
        code="LIMIT_AT_INFINITY_CONFUSION",
        concept_id=prerequisite_concept.id,
        problem_type_id=None,
        name="Confuses limit at infinity with asymptote",
        description="Fails to evaluate basic limit behavior at infinity.",
        category=MisconceptionCategory.CONCEPTUAL,
        is_active=True,
    )
    # 3. Unrelated concept misconception (MUST NOT appear in scope)
    m_unrelated = MisconceptionDefinition(
        code="SOLID_VOLUME_FORMULA_CONFUSION",
        concept_id=unrelated_concept.id,
        problem_type_id=None,
        name="Cone vs cylinder volume factor",
        description="Omits 1/3 factor in cone volume formula.",
        category=MisconceptionCategory.PROCEDURAL,
        is_active=True,
    )

    db_session.add_all([m_derivative, m_prereq, m_unrelated])
    db_session.commit()

    return {
        "derivative": m_derivative,
        "prereq": m_prereq,
        "unrelated": m_unrelated,
    }


def _create_attempt(
    db_session: Session,
    student: User,
    student_profile: StudentProfile,
    question: Question,
    *,
    is_correct: bool = False,
    student_answer: str = "Ta có y' > 0 nên hàm số nghịch biến trên R.",
) -> QuestionAttempt:
    """Helper to persist a PracticeSession and QuestionAttempt in the DB."""
    session_obj = PracticeSession(
        student_id=student_profile.id,
        subject_id=question.subject_id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    db_session.add(session_obj)
    db_session.flush()

    attempt = QuestionAttempt(
        practice_session_id=session_obj.id,
        student_id=student_profile.id,
        question_id=question.id,
        student_answer=student_answer,
        is_correct=is_correct,
        score=1.0 if is_correct else 0.0,
        response_time_seconds=30.0,
        attempt_number=1,
        evaluation_status=EvaluationStatus.EVALUATED,
    )
    db_session.add(attempt)
    db_session.flush()
    return attempt


# --------------------------------------------------------------------------
# 1. Reasoning Detection Tests
# --------------------------------------------------------------------------


def test_has_reasoning_detects_explanation_vs_bare_choices() -> None:
    # Bare choices
    assert not has_reasoning("A")
    assert not has_reasoning("B")
    assert not has_reasoning("TRUE")
    assert not has_reasoning("FALSE")
    assert not has_reasoning("sai")
    assert not has_reasoning("")
    assert not has_reasoning(None)

    # Responses with reasoning
    assert has_reasoning("Vì f'(x) < 0 nên hàm số nghịch biến")
    assert has_reasoning("y' = 3x^2 - 6x = 0 suy ra x = 0 hoặc x = 2")
    assert has_reasoning("Ta tính đạo hàm y' = 2x - 4 => x = 2")


# --------------------------------------------------------------------------
# 2. Taxonomy Scoper Tests
# --------------------------------------------------------------------------


def test_taxonomy_scoper_restricts_to_question_and_prerequisites(
    db_session: Session,
    practice_content: PracticeContent,
    setup_taxonomy: dict[str, MisconceptionDefinition],
    prerequisite_concept: Concept,
    unrelated_concept: Concept,
) -> None:
    scoper = TaxonomyScoper(db_session)
    taxonomy = scoper.get_scoped_taxonomy(practice_content.open_response)

    # Scoped definitions must include question concept and prerequisite concept
    codes = {d.code for d in taxonomy.definitions}
    assert "DERIVATIVE_SIGN_DIRECTION" in codes
    assert "LIMIT_AT_INFINITY_CONFUSION" in codes
    # Unrelated definition MUST NOT be in scope
    assert "SOLID_VOLUME_FORMULA_CONFUSION" not in codes

    # Check allowed ID sets
    assert practice_content.concept.id in taxonomy.allowed_concept_ids
    assert prerequisite_concept.id in taxonomy.allowed_concept_ids
    assert unrelated_concept.id not in taxonomy.allowed_concept_ids
    assert prerequisite_concept.id in taxonomy.allowed_prerequisite_concept_ids


# --------------------------------------------------------------------------
# 3. Pipeline: Correct Attempt Guardrail
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pipeline_skips_correct_attempt(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    setup_taxonomy: dict[str, MisconceptionDefinition],
    settings: Settings,
) -> None:
    student, _ = practice_students
    attempt = _create_attempt(
        db_session,
        student,
        student_profile,
        practice_content.open_response,
        is_correct=True,
        student_answer="Hàm số đồng biến vì f'(x) > 0 với mọi x.",
    )

    gateway = AIGateway(provider=MockAIProvider(), settings=settings)
    pipeline = MisconceptionPipeline(db_session, gateway=gateway)

    result = await pipeline.run_pipeline(attempt)
    assert not result.detected
    assert result.detection_source == "NONE"
    assert "correct" in (result.reason or "").lower()
    assert not result.evidence_recorded


# --------------------------------------------------------------------------
# 4. Pipeline: Deterministic Rule Detection (No AI called)
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pipeline_deterministic_rule_matches_without_ai(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    setup_taxonomy: dict[str, MisconceptionDefinition],
    settings: Settings,
) -> None:
    student, _ = practice_students
    # Student answer matches built-in deterministic pattern for derivative sign reversed
    attempt = _create_attempt(
        db_session,
        student,
        student_profile,
        practice_content.open_response,
        is_correct=False,
        student_answer="Vì y' > 0 nên hàm số nghịch biến trên khoảng xác định.",
    )

    mock_provider = MockAIProvider()
    gateway = AIGateway(provider=mock_provider, settings=settings)
    pipeline = MisconceptionPipeline(db_session, gateway=gateway)

    result = await pipeline.run_pipeline(attempt)

    # 1. Detected via deterministic rule
    assert result.detected
    assert result.detection_source == "DETERMINISTIC"
    assert result.misconception_code == "DERIVATIVE_SIGN_DIRECTION"
    assert result.evidence_recorded
    assert result.student_misconception_status == StudentMisconceptionStatus.SUSPECTED
    assert result.occurrence_count == 1

    # 2. Mock AI provider was NEVER called!
    assert mock_provider.call_count == 0


# --------------------------------------------------------------------------
# 5. Pipeline: Skips AI when response lacks reasoning
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pipeline_skips_ai_when_no_reasoning(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    setup_taxonomy: dict[str, MisconceptionDefinition],
    settings: Settings,
) -> None:
    student, _ = practice_students
    # Student gave a bare choice without reasoning
    attempt = _create_attempt(
        db_session,
        student,
        student_profile,
        practice_content.mcq,
        is_correct=False,
        student_answer="B",
    )

    mock_provider = MockAIProvider()
    gateway = AIGateway(provider=mock_provider, settings=settings)
    pipeline = MisconceptionPipeline(db_session, gateway=gateway)

    result = await pipeline.run_pipeline(attempt)

    assert not result.detected
    assert result.detection_source == "NONE"
    assert "reasoning" in (result.reason or "").lower()
    assert mock_provider.call_count == 0
    assert not result.evidence_recorded


# --------------------------------------------------------------------------
# 6. Pipeline: AI Analysis with Valid Diagnosis
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pipeline_ai_analysis_diagnoses_and_records_evidence(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    setup_taxonomy: dict[str, MisconceptionDefinition],
    settings: Settings,
) -> None:
    student, _ = practice_students
    attempt = _create_attempt(
        db_session,
        student,
        student_profile,
        practice_content.open_response,
        is_correct=False,
        student_answer="Em tính ra đạo hàm rồi suy ra hàm nghịch biến vì dấu trừ của biểu thức mẫu.",
    )

    # Provide canned structured output matching the scoped taxonomy
    canned_output = MisconceptionAnalysisOutput(
        concept_id=practice_content.concept.id,
        problem_type_id=practice_content.problem_type.id,
        misconception_code="DERIVATIVE_SIGN_DIRECTION",
        error_category=MisconceptionCategory.CONCEPTUAL,
        first_wrong_step="Interpreted denominator sign incorrectly to conclude decreasing.",
        confidence=0.88,
        possible_prerequisite_concept_id=None,
        requires_prerequisite_check=False,
    )

    mock_provider = MockAIProvider(canned_structured=canned_output)
    gateway = AIGateway(provider=mock_provider, settings=settings)
    pipeline = MisconceptionPipeline(db_session, gateway=gateway)

    result = await pipeline.run_pipeline(attempt)

    assert result.detected
    assert result.detection_source == "AI"
    assert result.misconception_code == "DERIVATIVE_SIGN_DIRECTION"
    assert result.evidence_recorded
    assert result.confidence == 0.88
    assert result.student_misconception_status == StudentMisconceptionStatus.SUSPECTED
    assert result.occurrence_count == 1
    assert mock_provider.call_count == 1

    # Check database state in student_misconceptions
    state = db_session.scalar(
        select(StudentMisconception).where(
            StudentMisconception.student_id == student_profile.id,
            StudentMisconception.misconception_definition_id == setup_taxonomy["derivative"].id,
        )
    )
    assert state is not None
    assert state.occurrence_count == 1
    assert state.status == StudentMisconceptionStatus.SUSPECTED


# --------------------------------------------------------------------------
# 7. Pipeline Guardrail: AI Cannot Invent Codes
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pipeline_rejects_invented_misconception_code(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    setup_taxonomy: dict[str, MisconceptionDefinition],
    settings: Settings,
) -> None:
    student, _ = practice_students
    attempt = _create_attempt(
        db_session,
        student,
        student_profile,
        practice_content.open_response,
        is_correct=False,
        student_answer="Cách giải: chia cả 2 vế cho biến số và rút gọn sai dẫn đến kết quả sai.",
    )

    # AI tries to invent a code not in the taxonomy
    invented_output = MisconceptionAnalysisOutput(
        concept_id=practice_content.concept.id,
        problem_type_id=practice_content.problem_type.id,
        misconception_code="AI_INVENTED_ARBITRARY_CODE",
        error_category=MisconceptionCategory.PROCEDURAL,
        first_wrong_step="Divided by variable without non-zero constraint.",
        confidence=0.90,
        possible_prerequisite_concept_id=None,
        requires_prerequisite_check=False,
    )

    mock_provider = MockAIProvider(canned_structured=invented_output)
    gateway = AIGateway(provider=mock_provider, settings=settings)
    pipeline = MisconceptionPipeline(db_session, gateway=gateway)

    result = await pipeline.run_pipeline(attempt)

    # Whitelist validator converted code to UNKNOWN
    assert not result.detected
    assert result.detection_source == "AI"
    assert not result.evidence_recorded
    assert "UNKNOWN" in (result.reason or "")

    # Ensure no record was created for an invented definition
    count = db_session.scalar(
        select(StudentMisconception).where(
            StudentMisconception.student_id == student_profile.id
        )
    )
    assert count is None


# --------------------------------------------------------------------------
# 8. Pipeline Guardrail: AI Cannot Use Out-Of-Scope Concept
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pipeline_rejects_out_of_scope_concept_code(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    setup_taxonomy: dict[str, MisconceptionDefinition],
    unrelated_concept: Concept,
    settings: Settings,
) -> None:
    student, _ = practice_students
    attempt = _create_attempt(
        db_session,
        student,
        student_profile,
        practice_content.open_response,
        is_correct=False,
        student_answer="Giải thích chi tiết các bước tính toán và phân tích hàm số.",
    )

    # AI outputs a valid definition code, but from an unrelated out-of-scope concept
    out_of_scope_output = MisconceptionAnalysisOutput(
        concept_id=unrelated_concept.id,
        problem_type_id=None,
        misconception_code="SOLID_VOLUME_FORMULA_CONFUSION",
        error_category=MisconceptionCategory.PROCEDURAL,
        first_wrong_step="Some step.",
        confidence=0.85,
        possible_prerequisite_concept_id=None,
        requires_prerequisite_check=False,
    )

    mock_provider = MockAIProvider(canned_structured=out_of_scope_output)
    gateway = AIGateway(provider=mock_provider, settings=settings)
    pipeline = MisconceptionPipeline(db_session, gateway=gateway)

    result = await pipeline.run_pipeline(attempt)

    # Scoped whitelist rejected the out-of-scope code
    assert not result.detected
    assert not result.evidence_recorded


# --------------------------------------------------------------------------
# 9. Pipeline Policy: Low Confidence Skips Evidence Recording
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pipeline_low_confidence_skips_evidence_per_policy(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    setup_taxonomy: dict[str, MisconceptionDefinition],
    settings: Settings,
) -> None:
    student, _ = practice_students
    attempt = _create_attempt(
        db_session,
        student,
        student_profile,
        practice_content.open_response,
        is_correct=False,
        student_answer="Em cảm thấy hàm này có đạo hàm đổi chiều nhưng không chắc chắn lắm.",
    )

    # Confidence 0.35 is below the default threshold (0.50)
    low_confidence_output = MisconceptionAnalysisOutput(
        concept_id=practice_content.concept.id,
        problem_type_id=practice_content.problem_type.id,
        misconception_code="DERIVATIVE_SIGN_DIRECTION",
        error_category=MisconceptionCategory.CONCEPTUAL,
        first_wrong_step="Ambiguous sign deduction.",
        confidence=0.35,
        possible_prerequisite_concept_id=None,
        requires_prerequisite_check=False,
    )

    mock_provider = MockAIProvider(canned_structured=low_confidence_output)
    gateway = AIGateway(provider=mock_provider, settings=settings)
    pipeline = MisconceptionPipeline(
        db_session, gateway=gateway, min_confidence_to_record=0.50
    )

    result = await pipeline.run_pipeline(attempt)

    # Diagnosed, but evidence recording was skipped due to low confidence policy
    assert result.detected
    assert result.detection_source == "AI"
    assert not result.evidence_recorded
    assert "below minimum recording threshold" in (result.reason or "")

    # Confirm no evidence was recorded in DB
    record = db_session.scalar(
        select(StudentMisconception).where(
            StudentMisconception.student_id == student_profile.id,
            StudentMisconception.misconception_definition_id == setup_taxonomy["derivative"].id,
        )
    )
    assert record is None


# --------------------------------------------------------------------------
# 10. Pipeline Policy: Backend Decides Confirmation (2+ Occurrences)
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pipeline_backend_controls_student_misconception_confirmation(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    setup_taxonomy: dict[str, MisconceptionDefinition],
    settings: Settings,
) -> None:
    student, _ = practice_students

    # Occurrence 1: High confidence (0.90) from AI
    attempt_1 = _create_attempt(
        db_session,
        student,
        student_profile,
        practice_content.open_response,
        is_correct=False,
        student_answer="Bước 1 tính đạo hàm. Bước 2: vì f' > 0 nên hàm nghịch biến.",
    )

    canned_1 = MisconceptionAnalysisOutput(
        concept_id=practice_content.concept.id,
        problem_type_id=practice_content.problem_type.id,
        misconception_code="DERIVATIVE_SIGN_DIRECTION",
        error_category=MisconceptionCategory.CONCEPTUAL,
        first_wrong_step="First step.",
        confidence=0.90,
        possible_prerequisite_concept_id=None,
        requires_prerequisite_check=False,
    )

    mock_provider = MockAIProvider(canned_structured=canned_1)
    gateway = AIGateway(provider=mock_provider, settings=settings)
    pipeline = MisconceptionPipeline(db_session, gateway=gateway)

    res_1 = await pipeline.run_pipeline(attempt_1)
    # AI had 0.90 confidence, but backend keeps status at SUSPECTED because occurrence_count == 1
    assert res_1.evidence_recorded
    assert res_1.occurrence_count == 1
    assert res_1.student_misconception_status == StudentMisconceptionStatus.SUSPECTED

    # Occurrence 2: High confidence from AI
    attempt_2 = _create_attempt(
        db_session,
        student,
        student_profile,
        practice_content.open_response,
        is_correct=False,
        student_answer="Tương tự bài trước, y' âm thì hàm số phải đồng biến.",
    )
    canned_2 = MisconceptionAnalysisOutput(
        concept_id=practice_content.concept.id,
        problem_type_id=practice_content.problem_type.id,
        misconception_code="DERIVATIVE_SIGN_DIRECTION",
        error_category=MisconceptionCategory.CONCEPTUAL,
        first_wrong_step="Second step.",
        confidence=0.90,
        possible_prerequisite_concept_id=None,
        requires_prerequisite_check=False,
    )
    mock_provider.canned_structured = canned_2

    res_2 = await pipeline.run_pipeline(attempt_2)
    # Backend now confirms the persistent misconception!
    assert res_2.evidence_recorded
    assert res_2.occurrence_count == 2
    assert res_2.student_misconception_status == StudentMisconceptionStatus.CONFIRMED


# --------------------------------------------------------------------------
# 11. Pipeline Prerequisite Gap Detection
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pipeline_prerequisite_concept_gap_flagged(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    setup_taxonomy: dict[str, MisconceptionDefinition],
    prerequisite_concept: Concept,
    settings: Settings,
) -> None:
    student, _ = practice_students
    attempt = _create_attempt(
        db_session,
        student,
        student_profile,
        practice_content.open_response,
        is_correct=False,
        student_answer="Em không tính được giới hạn khi x tiến ra vô cùng để xét tiệm cận đứng.",
    )

    canned_prereq = MisconceptionAnalysisOutput(
        concept_id=prerequisite_concept.id,
        problem_type_id=None,
        misconception_code="LIMIT_AT_INFINITY_CONFUSION",
        error_category=MisconceptionCategory.CONCEPTUAL,
        first_wrong_step="Confused limit at infinity.",
        confidence=0.85,
        possible_prerequisite_concept_id=prerequisite_concept.id,
        requires_prerequisite_check=True,
    )

    mock_provider = MockAIProvider(canned_structured=canned_prereq)
    gateway = AIGateway(provider=mock_provider, settings=settings)
    pipeline = MisconceptionPipeline(db_session, gateway=gateway)

    result = await pipeline.run_pipeline(attempt)

    assert result.detected
    assert result.misconception_code == "LIMIT_AT_INFINITY_CONFUSION"
    assert result.requires_prerequisite_check
    assert result.possible_prerequisite_concept_id == prerequisite_concept.id
    assert result.evidence_recorded
