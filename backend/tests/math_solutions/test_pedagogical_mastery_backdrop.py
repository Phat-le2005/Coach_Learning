"""Tests for the pedagogical step error classification, consequential scoring, and two-tier mastery backdrop."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.subjects.models import Subject
from app.users.models import Role, User
from app.curriculum.models import Chapter, ProblemType, Topic
from app.concepts.models import Concept
from app.learning_evidence.models import LearningEvidenceEvent
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.math_solutions.answer_grounded_ai import AIStepGrade, AnswerGroundedReview
from app.math_solutions.mastery_backdrop import (
    ErrorPedagogicalCategory,
    MasteryBackdropService,
    classify_step_error,
    compute_step_grounded_score,
)
from app.math_solutions.models import SolutionAttempt, SolutionStep
from app.misconceptions.models import (
    MisconceptionCategory,
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.questions.models import Question, QuestionConcept, QuestionProblemType
from app.students.models import StudentProfile


def test_classify_step_error_identifies_arithmetic_slip():
    step = SolutionStep(step_index=1, step_type="DERIVATIVE_CALCULATION")
    grade = AIStepGrade(
        step_index=1,
        verdict="INVALID",
        score=0.0,
        confidence=0.9,
        student_quote="y' = 3x^2 - 2x + 1",
        answer_quote="y' = 3x^2 - 2x - 3",
        feedback="Tính nhầm dấu số hạng tự do ở bước đạo hàm.",
    )
    res = classify_step_error(step, grade, invalid_prior_step_indices=set())
    assert res.category == ErrorPedagogicalCategory.ARITHMETIC_SLIP
    assert res.score == 0.50  # Partial credit for correct differentiation structure


def test_classify_step_error_honors_structured_ai_enum_without_relying_on_keywords():
    """Verify that structured error_nature from AI is honored even if feedback has novel/unseen wording."""
    step_slip = SolutionStep(step_index=2, step_type="DERIVATIVE_CALCULATION")
    grade_slip = AIStepGrade(
        step_index=2,
        verdict="INVALID",
        score=0.0,
        confidence=0.92,
        student_quote="f'(x)=2x+5",
        answer_quote="f'(x)=2x+6",
        feedback="Học sinh có độ lệch giá trị đại số ở phần hệ số.",
        error_nature="ARITHMETIC_SLIP",
    )
    res_slip = classify_step_error(step_slip, grade_slip, invalid_prior_step_indices=set())
    assert res_slip.category == ErrorPedagogicalCategory.ARITHMETIC_SLIP
    assert res_slip.score == 0.50

    step_consequential = SolutionStep(step_index=3, step_type="CONCLUSION")
    grade_consequential = AIStepGrade(
        step_index=3,
        verdict="INVALID",
        score=0.0,
        confidence=0.88,
        student_quote="Hàm số đạt cực đại tại x = 1",
        answer_quote="Hàm số đạt cực đại tại x = 2",
        feedback="Thao tác suy luận logic của học sinh hoàn toàn nhất quán với kết quả thu được ở bước 2.",
        error_nature="CONSEQUENTIAL",
    )
    res_consequential = classify_step_error(step_consequential, grade_consequential, invalid_prior_step_indices=set())
    assert res_consequential.category == ErrorPedagogicalCategory.CONSEQUENTIAL
    assert res_consequential.score == 0.75

    step_concept = SolutionStep(step_index=4, step_type="LOCAL_EXTREMA")
    grade_concept = AIStepGrade(
        step_index=4,
        verdict="INVALID",
        score=0.0,
        confidence=0.95,
        student_quote="x = 0 là điểm cực trị vì f'(0) = 0",
        answer_quote="f' không đổi dấu nên không có cực trị tại x = 0",
        feedback="Học sinh ngộ nhận rằng đạo hàm bằng không thì nhất thiết phải là cực trị.",
        error_nature="CONCEPTUAL",
    )
    res_concept = classify_step_error(step_concept, grade_concept, invalid_prior_step_indices=set())
    assert res_concept.category == ErrorPedagogicalCategory.CONCEPTUAL
    assert res_concept.score == 0.0
    assert res_concept.misconception_code == "DERIVATIVE_ZERO_ALWAYS_EXTREMUM"


def test_ai_step_grade_schema_validation_rules():
    import pytest
    from pydantic import ValidationError

    # Valid step cannot have error_nature
    with pytest.raises(ValidationError):
        AIStepGrade(
            step_index=1,
            verdict="VALID",
            score=1.0,
            confidence=0.9,
            student_quote="OK",
            answer_quote="OK",
            feedback="Bước giải đúng",
            error_nature="ARITHMETIC_SLIP",
        )

    # Needs review step cannot have error_nature
    with pytest.raises(ValidationError):
        AIStepGrade(
            step_index=1,
            verdict="NEEDS_REVIEW",
            score=None,
            confidence=0.5,
            student_quote="Check",
            answer_quote="Check",
            feedback="Cần kiểm tra lại",
            error_nature="CONCEPTUAL",
        )

    # Invalid step with valid error_nature is accepted
    grade = AIStepGrade(
        step_index=1,
        verdict="INVALID",
        score=0.0,
        confidence=0.9,
        student_quote="x=1",
        answer_quote="x=2",
        feedback="Sai sót",
        error_nature="ARITHMETIC_SLIP",
    )
    assert grade.error_nature == "ARITHMETIC_SLIP"


def test_classify_step_error_identifies_consequential_method_credit():
    step = SolutionStep(step_index=3, step_type="VARIATION_TABLE")
    grade = AIStepGrade(
        step_index=3,
        verdict="INVALID",
        score=0.0,
        confidence=0.85,
        student_quote="x | -1  1",
        answer_quote="x | -1  3",
        feedback="Bảng biến thiên lập đúng theo nghiệm sai ở bước trên.",
    )
    # Step 2 had an error
    res = classify_step_error(step, grade, invalid_prior_step_indices={2})
    assert res.category == ErrorPedagogicalCategory.CONSEQUENTIAL
    assert res.score == 0.75  # 75% method credit according to exam standards


def test_classify_step_error_identifies_conceptual_misconception():
    step = SolutionStep(step_index=3, step_type="SIGN_TABLE")
    grade = AIStepGrade(
        step_index=3,
        verdict="INVALID",
        score=0.0,
        confidence=0.95,
        student_quote="f'(x) > 0 trong khoảng (-1, 3)",
        answer_quote="f'(x) < 0 trong khoảng (-1, 3)",
        feedback="Áp dụng sai quy tắc xét dấu tam thức bậc hai: trong trái ngoài cùng.",
    )
    res = classify_step_error(step, grade, invalid_prior_step_indices=set())
    assert res.category == ErrorPedagogicalCategory.CONCEPTUAL
    assert res.score == 0.0
    assert res.misconception_code == "DERIVATIVE_SIGN_DIRECTION"


def test_compute_step_grounded_score_protects_student_with_consequential_credit():
    steps = [
        SolutionStep(step_index=1, step_type="ASSUMPTION"),
        SolutionStep(step_index=2, step_type="ROOT_FINDING"),
        SolutionStep(step_index=3, step_type="VARIATION_TABLE"),
    ]
    review = AnswerGroundedReview(
        attempt_id=uuid4(),
        answer_sha256="fake",
        step_grades=(
            AIStepGrade(step_index=1, verdict="VALID", score=1.0, confidence=0.9, student_quote="D=R", answer_quote="D=R", feedback="OK"),
            AIStepGrade(step_index=2, verdict="INVALID", score=0.0, confidence=0.9, student_quote="x=1", answer_quote="x=3", feedback="Tính nhầm nghiệm"),
            AIStepGrade(step_index=3, verdict="INVALID", score=0.0, confidence=0.9, student_quote="bbt", answer_quote="bbt", feedback="Đúng phương pháp theo nghiệm ở trên"),
        ),
        needs_teacher_review=False,
    )
    final_score, is_correct, summaries, classifications = compute_step_grounded_score(steps, review)
    # Score should reflect partial credit for step 2 (slip 0.5) and step 3 (consequential 0.75)
    assert final_score >= 0.70
    assert not is_correct
    assert len(classifications) == 3


def test_first_failure_remains_suspected_and_does_not_zero_penalize_concept(db_session: Session):
    user = User(
        email=f"test_{uuid4()}@example.com",
        role=Role.STUDENT,
        password_hash="pw",
        full_name="Test Student",
    )
    db_session.add(user)
    db_session.flush()

    student = StudentProfile(user_id=user.id)
    db_session.add(student)
    db_session.flush()

    subj = Subject(code=f"M_{uuid4().hex[:6].upper()}", name="Toán", grade_level=12)
    db_session.add(subj)
    db_session.flush()

    concept = Concept(subject_id=subj.id, code="DERIVATIVE", name="Đạo hàm", description="Khái niệm đạo hàm")
    db_session.add(concept)
    db_session.flush()

    definition = MisconceptionDefinition(
        code="DERIVATIVE_SIGN_DIRECTION",
        concept_id=concept.id,
        name="Đổi dấu đạo hàm",
        description="Nhầm chiều biến thiên từ dấu đạo hàm",
        category=MisconceptionCategory.CONCEPTUAL,
        is_active=True,
    )
    db_session.add(definition)
    db_session.flush()

    chapter = Chapter(subject_id=subj.id, code="CH1", name="Hàm số", order_index=1)
    db_session.add(chapter)
    db_session.flush()

    topic = Topic(chapter_id=chapter.id, code="TOP1", name="Đơn điệu", order_index=1)
    db_session.add(topic)
    db_session.flush()

    pt = ProblemType(topic_id=topic.id, code="MONOTONICITY_FROM_EXPRESSION", name="Tính đơn điệu", order_index=1)
    db_session.add(pt)
    db_session.flush()

    question = Question(
        subject_id=subj.id,
        content="Khảo sát hàm số",
        question_type="OPEN_RESPONSE",
        difficulty=0.5,
        exam_weight=1.0,
        source_type="SAMPLE_TEST",
        status="APPROVED",
        created_by=user.id,
    )
    db_session.add(question)
    db_session.flush()

    db_session.add(QuestionConcept(question_id=question.id, concept_id=concept.id, weight=1.0))
    db_session.add(QuestionProblemType(question_id=question.id, problem_type_id=pt.id, weight=1.0, is_primary=True))
    db_session.flush()

    # Pre-populate student with healthy 75% concept mastery
    db_session.add(
        StudentConceptMastery(
            student_id=student.id,
            concept_id=concept.id,
            mastery_score=0.75,
            confidence=0.70,
            attempt_count=3,
            correct_count=2,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()

    # Attempt 1: Student makes a conceptual error on variation table
    ps = PracticeSession(
        student_id=student.id,
        subject_id=subj.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    db_session.add(ps)
    db_session.flush()

    attempt1 = SolutionAttempt(
        student_id=student.id,
        question_id=question.id,
        practice_session_id=ps.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        mode="INDEPENDENT_SOLUTION",
        status="SUBMITTED",
    )
    db_session.add(attempt1)
    db_session.flush()

    step1 = SolutionStep(attempt_id=attempt1.id, step_index=1, step_type="VARIATION_TABLE")
    db_session.add(step1)
    db_session.flush()

    review1 = AnswerGroundedReview(
        attempt_id=attempt1.id,
        answer_sha256="sha1",
        needs_teacher_review=False,
        step_grades=(
            AIStepGrade(
                step_index=1,
                verdict="INVALID",
                score=0.0,
                confidence=0.9,
                student_quote="f'(x) > 0",
                answer_quote="f'(x) < 0",
                feedback="Áp dụng sai quy tắc xét dấu đạo hàm.",
            ),
        ),
    )

    backdrop = MasteryBackdropService(db_session)
    backdrop.record_answer_grounded_review(attempt=attempt1, review=review1, content_sha256="sha1")
    db_session.flush()

    # Check that after FIRST failure:
    # 1. StudentMisconception is SUSPECTED (occurrence_count = 1)
    misc = db_session.scalar(
        select(StudentMisconception).where(
            StudentMisconception.student_id == student.id,
            StudentMisconception.misconception_definition_id == definition.id,
        )
    )
    assert misc is not None
    assert misc.status == StudentMisconceptionStatus.SUSPECTED
    assert misc.occurrence_count == 1

    # 2. StudentConceptMastery was NOT plunged to 0.0! Score gently declined (remains > 0.50)
    mastery = db_session.scalar(
        select(StudentConceptMastery).where(
            StudentConceptMastery.student_id == student.id,
            StudentConceptMastery.concept_id == concept.id,
        )
    )
    assert mastery.mastery_score > 0.50  # Protected from brutal zero-penalty!
    assert mastery.mastery_score < 0.75  # Slightly adjusted

