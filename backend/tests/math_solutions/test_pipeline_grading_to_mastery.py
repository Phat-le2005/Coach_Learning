"""Comprehensive tests for the hardened grading-to-mastery pipeline (5 core architectural fixes).

1. Gating provisional AI reviews (unverified / needs_teacher_review cannot alter mastery).
2. Unverified states scored as 0.0 (no arbitrary partial credit; low confidence downgraded).
3. Rubric-criterion skill attribution (step-level attribution prevents unrelated concept penalties).
4. No speculative keyword mapping (content keywords like 'x^3' do not fabricate competencies).
5. Teacher override synchronization & anti-double-counting (idempotent replay recalibrates mastery).
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.curriculum.models import Chapter, ProblemType, Topic
from app.learning_evidence.models import LearningEvidenceEvent, LearningEvidenceSourceKind
from app.mastery.evidence import DeterministicMasteryEvidencePublisher
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.math_solutions.answer_grounded_ai import AIStepGrade, AnswerGroundedReview
from app.math_solutions.evidence_adapter import MathSolutionEvidenceAdapter
from app.math_solutions.mastery_backdrop import (
    ErrorPedagogicalCategory,
    MasteryBackdropService,
    classify_step_error,
    compute_step_grounded_score,
)
from app.math_solutions.models import (
    EvaluationDecision,
    SolutionAttempt,
    SolutionRubric,
    SolutionStep,
)
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.questions.models import Question, QuestionConcept, QuestionProblemType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role, User


def _setup_curriculum(db_session: Session):
    user = User(
        email=f"pipeline_student_{uuid4()}@example.com",
        role=Role.STUDENT,
        password_hash="pw",
        full_name="Pipeline Student",
    )
    teacher = User(
        email=f"pipeline_teacher_{uuid4()}@example.com",
        role=Role.TEACHER,
        password_hash="pw",
        full_name="Pipeline Teacher",
    )
    db_session.add_all([user, teacher])
    db_session.flush()

    student = StudentProfile(user_id=user.id)
    db_session.add(student)
    db_session.flush()

    subj = Subject(code=f"SUBJ_{uuid4().hex[:6].upper()}", name="Toán 12", grade_level=12)
    db_session.add(subj)
    db_session.flush()

    c_derivative = Concept(subject_id=subj.id, code="FIRST_DERIVATIVE", name="Đạo hàm bậc nhất")
    c_monotone = Concept(subject_id=subj.id, code="MONOTONICITY_CRITERION", name="Tính đơn điệu")
    db_session.add_all([c_derivative, c_monotone])
    db_session.flush()

    chapter = Chapter(subject_id=subj.id, code=f"CHP_{uuid4().hex[:4].upper()}", name="Hàm số", order_index=1)
    db_session.add(chapter)
    db_session.flush()

    topic = Topic(chapter_id=chapter.id, code=f"TOP_{uuid4().hex[:4].upper()}", name="Đơn điệu", order_index=1)
    db_session.add(topic)
    db_session.flush()

    pt = ProblemType(
        topic_id=topic.id,
        code=f"PT_{uuid4().hex[:4].upper()}",
        name="Xét tính đơn điệu hàm đa thức",
        order_index=1,
    )
    db_session.add(pt)
    db_session.flush()

    ps = PracticeSession(
        student_id=student.id,
        subject_id=subj.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    db_session.add(ps)
    db_session.flush()

    return student, teacher, subj, c_derivative, c_monotone, pt, ps


def test_unverified_verdicts_score_zero_and_low_confidence_is_downgraded():
    """Requirement 2: Unverified/NEEDS_REVIEW must score 0.0 and VALID with low confidence must be flagged."""
    step = SolutionStep(step_index=1, step_type="DERIVATIVE_CALCULATION")

    # 1. NEEDS_REVIEW with 0 confidence gives 0.0 (previously gave 0.175)
    grade_unverified = AIStepGrade(
        step_index=1,
        verdict="NEEDS_REVIEW",
        score=None,
        confidence=0.0,
        student_quote="y' = ...",
        answer_quote="y' = ...",
        feedback="Chưa đủ căn cứ xác minh",
    )
    res_unverified = classify_step_error(step, grade_unverified, invalid_prior_step_indices=set())
    assert res_unverified.category == ErrorPedagogicalCategory.NEEDS_REVIEW
    assert res_unverified.score == 0.0

    # 2. VALID with low confidence (< 0.80) is downgraded to NEEDS_REVIEW with score 0.0
    grade_low_conf = AIStepGrade(
        step_index=1,
        verdict="VALID",
        score=1.0,
        confidence=0.20,
        student_quote="y' = x^2 - 2x",
        answer_quote="y' = x^2 - 2x",
        feedback="Có vẻ đúng",
    )
    res_low_conf = classify_step_error(step, grade_low_conf, invalid_prior_step_indices=set())
    assert res_low_conf.category == ErrorPedagogicalCategory.NEEDS_REVIEW
    assert res_low_conf.score == 0.0

    # 3. compute_step_grounded_score fails is_correct if any step is NEEDS_REVIEW
    review_with_unverified = AnswerGroundedReview(
        attempt_id=uuid4(),
        answer_sha256="fake_sha",
        step_grades=(grade_unverified,),
        needs_teacher_review=False,
    )
    final_score, is_correct, _, _ = compute_step_grounded_score([step], review_with_unverified)
    assert not is_correct
    assert final_score == 0.0


def test_provisional_ai_review_does_not_mutate_mastery_when_unverified(db_session: Session):
    """Requirement 1: Provisional reviews with needs_teacher_review or NEEDS_REVIEW do not touch official mastery."""
    student, teacher, subj, c_derivative, c_monotone, pt, ps = _setup_curriculum(db_session)

    question = Question(
        subject_id=subj.id,
        content="Khảo sát hàm số y = x^3 - 3x",
        question_type="OPEN_RESPONSE",
        difficulty=0.5,
        exam_weight=1.0,
        source_type="SAMPLE_TEST",
        status="APPROVED",
        created_by=teacher.id,
    )
    db_session.add(question)
    db_session.flush()
    db_session.add(QuestionProblemType(question_id=question.id, problem_type_id=pt.id, weight=1.0, is_primary=True))
    db_session.add(QuestionConcept(question_id=question.id, concept_id=c_derivative.id, weight=1.0))
    db_session.flush()

    attempt = SolutionAttempt(
        student_id=student.id,
        question_id=question.id,
        practice_session_id=ps.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        mode="INDEPENDENT_SOLUTION",
        status="SUBMITTED",
    )
    db_session.add(attempt)
    db_session.flush()

    step = SolutionStep(attempt_id=attempt.id, step_index=1, step_type="DERIVATIVE_CALCULATION")
    db_session.add(step)
    db_session.flush()

    # Case A: review.needs_teacher_review is True
    review_flagged = AnswerGroundedReview(
        attempt_id=attempt.id,
        answer_sha256="sha_flagged",
        step_grades=(
            AIStepGrade(
                step_index=1,
                verdict="VALID",
                score=1.0,
                confidence=0.9,
                student_quote="y' = 3x^2 - 3",
                answer_quote="y' = 3x^2 - 3",
                feedback="Đúng",
            ),
        ),
        needs_teacher_review=True,
    )

    backdrop = MasteryBackdropService(db_session)
    backdrop.record_answer_grounded_review(attempt=attempt, review=review_flagged, content_sha256="sha_flagged")
    db_session.flush()

    # Mastery must NOT be created
    mastery_pt = db_session.scalar(
        select(StudentProblemTypeMastery).where(
            StudentProblemTypeMastery.student_id == student.id,
            StudentProblemTypeMastery.problem_type_id == pt.id,
        )
    )
    assert mastery_pt is None

    # Case B: review has a step with NEEDS_REVIEW
    review_unverified_step = AnswerGroundedReview(
        attempt_id=attempt.id,
        answer_sha256="sha_unverified",
        step_grades=(
            AIStepGrade(
                step_index=1,
                verdict="NEEDS_REVIEW",
                score=None,
                confidence=0.5,
                student_quote="y' = 3x^2 - 3",
                answer_quote="y' = 3x^2 - 3",
                feedback="Cần kiểm tra thêm",
            ),
        ),
        needs_teacher_review=False,
    )
    backdrop.record_answer_grounded_review(attempt=attempt, review=review_unverified_step, content_sha256="sha_unverified")
    db_session.flush()

    mastery_pt_after = db_session.scalar(
        select(StudentProblemTypeMastery).where(
            StudentProblemTypeMastery.student_id == student.id,
            StudentProblemTypeMastery.problem_type_id == pt.id,
        )
    )
    assert mastery_pt_after is None


def test_rubric_criterion_skill_attribution_isolates_valid_derivative_from_failed_conclusion(db_session: Session):
    """Requirement 3: Multi-step solution correctly attributes valid derivative without being dragged down by conclusion."""
    student, teacher, subj, c_derivative, c_monotone, pt, ps = _setup_curriculum(db_session)

    question = Question(
        subject_id=subj.id,
        content="Khảo sát đơn điệu",
        question_type="OPEN_RESPONSE",
        difficulty=0.5,
        exam_weight=1.0,
        source_type="SAMPLE_TEST",
        status="APPROVED",
        created_by=teacher.id,
    )
    db_session.add(question)
    db_session.flush()
    db_session.add(QuestionProblemType(question_id=question.id, problem_type_id=pt.id, weight=1.0, is_primary=True))
    db_session.add(QuestionConcept(question_id=question.id, concept_id=c_derivative.id, weight=1.0))
    db_session.add(QuestionConcept(question_id=question.id, concept_id=c_monotone.id, weight=1.0))
    db_session.flush()

    attempt = SolutionAttempt(
        student_id=student.id,
        question_id=question.id,
        practice_session_id=ps.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        mode="INDEPENDENT_SOLUTION",
        status="SUBMITTED",
    )
    db_session.add(attempt)
    db_session.flush()

    step1 = SolutionStep(attempt_id=attempt.id, step_index=1, step_type="DERIVATIVE_CALCULATION")
    step2 = SolutionStep(attempt_id=attempt.id, step_index=2, step_type="CONCLUSION")
    db_session.add_all([step1, step2])
    db_session.flush()

    # Student calculates derivative perfectly (VALID), but concludes monotonicity incorrectly (CONCEPTUAL error)
    review = AnswerGroundedReview(
        attempt_id=attempt.id,
        answer_sha256="sha_multi",
        step_grades=(
            AIStepGrade(
                step_index=1,
                verdict="VALID",
                score=1.0,
                confidence=0.95,
                student_quote="y' = 3x^2 - 3",
                answer_quote="y' = 3x^2 - 3",
                feedback="Tính đạo hàm chính xác.",
            ),
            AIStepGrade(
                step_index=2,
                verdict="INVALID",
                score=0.0,
                confidence=0.95,
                student_quote="Hàm số luôn đồng biến trên R",
                answer_quote="Hàm số đồng biến trên (-inf, -1) và (1, +inf)",
                feedback="Áp dụng sai định lý dấu đạo hàm cho hàm bậc 3.",
                error_nature="CONCEPTUAL",
            ),
        ),
        needs_teacher_review=False,
    )

    backdrop = MasteryBackdropService(db_session)
    backdrop.record_answer_grounded_review(attempt=attempt, review=review, content_sha256="sha_multi")
    db_session.flush()

    # Derivative concept must be high / credited (not zeroed)
    m_derivative = db_session.scalar(
        select(StudentConceptMastery).where(
            StudentConceptMastery.student_id == student.id,
            StudentConceptMastery.concept_id == c_derivative.id,
        )
    )
    assert m_derivative is not None
    assert m_derivative.mastery_score > 0.0
    assert m_derivative.correct_count == 1

    # Monotonicity concept had an error on conclusion
    m_monotone = db_session.scalar(
        select(StudentConceptMastery).where(
            StudentConceptMastery.student_id == student.id,
            StudentConceptMastery.concept_id == c_monotone.id,
        )
    )
    assert m_monotone is not None
    assert m_monotone.correct_count == 0


def test_no_speculative_problem_type_mapping_from_keywords(db_session: Session):
    """Requirement 4: Backdrop does not guess problem types from keywords when unlinked."""
    student, teacher, subj, _, _, _, ps = _setup_curriculum(db_session)

    # Question with content containing "khảo sát" and "x^3", but NO curriculum links
    unlinked_question = Question(
        subject_id=subj.id,
        content="Khảo sát sự biến thiên của hàm bậc ba y = x^3 - 3x",
        question_type="OPEN_RESPONSE",
        difficulty=0.5,
        exam_weight=1.0,
        source_type="SAMPLE_TEST",
        status="APPROVED",
        created_by=teacher.id,
    )
    db_session.add(unlinked_question)
    db_session.flush()

    attempt = SolutionAttempt(
        student_id=student.id,
        question_id=unlinked_question.id,
        practice_session_id=ps.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        mode="INDEPENDENT_SOLUTION",
        status="SUBMITTED",
    )
    db_session.add(attempt)
    db_session.flush()

    step = SolutionStep(attempt_id=attempt.id, step_index=1, step_type="DERIVATIVE_CALCULATION")
    db_session.add(step)
    db_session.flush()

    review = AnswerGroundedReview(
        attempt_id=attempt.id,
        answer_sha256="sha_unlinked",
        step_grades=(
            AIStepGrade(
                step_index=1,
                verdict="VALID",
                score=1.0,
                confidence=0.95,
                student_quote="y' = 3x^2 - 3",
                answer_quote="y' = 3x^2 - 3",
                feedback="Đúng",
            ),
        ),
        needs_teacher_review=False,
    )

    backdrop = MasteryBackdropService(db_session)
    backdrop.record_answer_grounded_review(attempt=attempt, review=review, content_sha256="sha_unlinked")
    db_session.flush()

    # No fake problem types fabricated
    mastery_count = db_session.scalar(
        select(StudentProblemTypeMastery).where(StudentProblemTypeMastery.student_id == student.id)
    )
    assert mastery_count is None


def test_teacher_override_synchronizes_mastery_and_supersedes_backdrop(db_session: Session):
    """Requirement 5: Teacher override recalculates student mastery deterministically and eliminates duplicate counting."""
    student, teacher, subj, c_derivative, _, pt, ps = _setup_curriculum(db_session)

    question = Question(
        subject_id=subj.id,
        content="Tính đạo hàm",
        question_type="OPEN_RESPONSE",
        difficulty=0.5,
        exam_weight=1.0,
        source_type="SAMPLE_TEST",
        status="APPROVED",
        created_by=teacher.id,
    )
    db_session.add(question)
    db_session.flush()
    db_session.add(QuestionProblemType(question_id=question.id, problem_type_id=pt.id, weight=1.0, is_primary=True))
    db_session.add(QuestionConcept(question_id=question.id, concept_id=c_derivative.id, weight=1.0))
    db_session.flush()

    attempt = SolutionAttempt(
        student_id=student.id,
        question_id=question.id,
        practice_session_id=ps.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        mode="INDEPENDENT_SOLUTION",
        status="SUBMITTED",
    )
    db_session.add(attempt)
    db_session.flush()

    # Step evaluation initially failed with score 0.0
    decision = EvaluationDecision(
        attempt_id=attempt.id,
        decision_source="AUTOMATED_CONSENSUS",
        final_score=0.0,
        is_correct=False,
        decided_at=datetime.now(timezone.utc),
    )
    db_session.add(decision)
    db_session.flush()

    adapter = MathSolutionEvidenceAdapter(db_session)
    # Emit initial failed decision
    adapter.emit_evidence_for_decision(decision.id)
    db_session.flush()

    pt_mastery_initial = db_session.scalar(
        select(StudentProblemTypeMastery).where(
            StudentProblemTypeMastery.student_id == student.id,
            StudentProblemTypeMastery.problem_type_id == pt.id,
        )
    )
    assert pt_mastery_initial is not None
    assert pt_mastery_initial.correct_count == 0
    assert pt_mastery_initial.attempt_count == 1
    initial_score = pt_mastery_initial.mastery_score

    # Teacher reviews and overrides the student's solution to 100% correct
    override = adapter.apply_teacher_override(
        decision_id=decision.id,
        teacher_id=teacher.id,
        new_score=1.0,
        new_is_correct=True,
        reason="Học sinh sử dụng phương pháp giải tương đương hoàn toàn chính xác.",
    )
    db_session.flush()

    assert override.override_version == 1
    assert decision.final_score == 1.0
    assert decision.is_correct is True
    assert attempt.total_score == 1.0
    assert attempt.is_correct is True

    # Check that student mastery was RECALCULATED and now reflects the teacher's override!
    pt_mastery_updated = db_session.scalar(
        select(StudentProblemTypeMastery).where(
            StudentProblemTypeMastery.student_id == student.id,
            StudentProblemTypeMastery.problem_type_id == pt.id,
        )
    )
    assert pt_mastery_updated is not None
    assert pt_mastery_updated.correct_count == 1  # Updated from 0 to 1!
    assert pt_mastery_updated.attempt_count == 1  # NOT double-counted as 2 attempts!
    assert pt_mastery_updated.mastery_score > initial_score  # Increased!

    concept_mastery = db_session.scalar(
        select(StudentConceptMastery).where(
            StudentConceptMastery.student_id == student.id,
            StudentConceptMastery.concept_id == c_derivative.id,
        )
    )
    assert concept_mastery is not None
    assert concept_mastery.correct_count == 1
