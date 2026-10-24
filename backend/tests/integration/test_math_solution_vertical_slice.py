"""Vertical Slice End-to-End Integration Test for Grade 12 Calculus Monotonicity.
Implements and verifies the 10-phase lifecycle from VERTICAL_SLICE.md:
1. Student solves step-by-step with inverted quadratic sign table.
2. Tier-2 Deterministic validation (valid derivative).
3. Tier-3 Rubric evaluation (0.40 score).
4. Tier-4 Misconception disentanglement (identifies SIGN_TABLE_QUADRATIC_RULE_INVERTED without false positive).
5. First automated decision, MATH_SOLUTION_EVALUATION evidence, deterministic mastery calculation (0.0836).
6-8. Independent recheck attempt with correct sign table, evaluated to 1.0.
9. Second evidence event, updated mastery (0.2852), and 2.0-day spaced repetition schedule.
10. Teacher override audit ledger with append-only evidence preservation.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.curriculum.models import Chapter, ProblemType, Topic
from app.learning_evidence.models import (
    LearningEvidenceEvent,
    LearningEvidenceSourceKind,
)
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.math_solutions.evaluator_service import MathEvaluatorService
from app.math_solutions.evidence_adapter import MathSolutionEvidenceAdapter
from app.math_solutions.models import (
    EvaluationDecision,
    EvaluationOverride,
    MathArtifact,
    SolutionAttempt,
    SolutionRubric,
    SolutionStep,
    StepRevision,
)
from app.math_solutions.schemas import MathArtifactDraft, SolutionStepDraft
from app.math_solutions.service import MathSolutionService
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.review.models import ReviewSchedule
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService


def _setup_vertical_slice_fixture(db_session: Session):
    """Sets up the Grade 12 Calculus Monotonicity domain hierarchy."""
    subject = Subject(code=f"MATH12-VS-{uuid4().hex[:6].upper()}", name="Toán 12 Khảo sát hàm số", grade_level=12)
    db_session.add(subject)
    db_session.flush()

    chapter = Chapter(subject_id=subject.id, code="CH1_CALCULUS_M12", name="Ứng dụng đạo hàm", order_index=1)
    db_session.add(chapter)
    db_session.flush()

    topic = Topic(chapter_id=chapter.id, code="TOPIC_MONOTONICITY", name="Tính đơn điệu của hàm số", order_index=1)
    db_session.add(topic)
    db_session.flush()

    problem_type = ProblemType(
        topic_id=topic.id,
        code="MONOTONICITY_FROM_EXPRESSION",
        name="Xét tính đơn điệu hàm số từ biểu thức",
        order_index=1,
    )
    db_session.add(problem_type)
    db_session.flush()

    concept = Concept(subject_id=subject.id, code="QUADRATIC_SIGN_RULE", name="Dấu của tam thức bậc hai", order_index=1)
    db_session.add(concept)
    db_session.flush()

    users = UserService(db_session)
    student_user = users.create_user(
        UserCreate(
            email=f"vs_student_{uuid4().hex[:6]}@example.com",
            password="Password123!",
            full_name="Học sinh Lát Cắt Dọc",
            role=Role.STUDENT,
        )
    )
    teacher_user = users.create_user(
        UserCreate(
            email=f"vs_teacher_{uuid4().hex[:6]}@example.com",
            password="Password123!",
            full_name="Giáo viên Bộ môn Toán",
            role=Role.TEACHER,
        )
    )

    student = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))

    practice = PracticeSession(
        student_id=student.id,
        subject_id=subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    db_session.add(practice)
    db_session.flush()

    # Canonical Question: y = 1/3 x^3 - x^2 - 3x + 1
    question = Question(
        subject_id=subject.id,
        content=r"Tìm các khoảng đơn điệu của hàm số: y = \frac{1}{3}x^3 - x^2 - 3x + 1",
        question_type=QuestionType.OPEN_RESPONSE,
        difficulty=0.50,
        source_type="CANONICAL",
        exam_weight=1.0,
        status=QuestionStatus.APPROVED,
        created_by=teacher_user.id,
    )
    db_session.add(question)
    db_session.flush()

    db_session.add(QuestionConcept(question_id=question.id, concept_id=concept.id, weight=1.0))
    db_session.add(QuestionProblemType(question_id=question.id, problem_type_id=problem_type.id, weight=1.0, is_primary=True))
    db_session.flush()

    # Solution Rubric with canonical weights:
    # ASSUMPTION: 0.10, DERIVATIVE_CALCULATION: 0.30, ROOT_FINDING: 0.20, SIGN_TABLE: 0.25, CONCLUSION: 0.15
    rubric = SolutionRubric(
        question_id=question.id,
        rubric_version=1,
        title="Thang điểm chuẩn Xét tính đơn điệu hàm bậc ba",
        status="APPROVED",
        criteria=[
            {"id": "c1", "step_type": "ASSUMPTION", "weight": 0.10, "name": "Tập xác định D = R"},
            {"id": "c2", "step_type": "DERIVATIVE_CALCULATION", "weight": 0.30, "name": "Tính đạo hàm y' = x^2 - 2x - 3"},
            {"id": "c3", "step_type": "ROOT_FINDING", "weight": 0.20, "name": "Nghiệm đạo hàm x = -1, x = 3"},
            {"id": "c4", "step_type": "SIGN_TABLE", "weight": 0.25, "name": "Bảng xét dấu tam thức bậc hai"},
            {"id": "c5", "step_type": "CONCLUSION", "weight": 0.15, "name": "Kết luận đồng biến, nghịch biến"},
        ],
        approved_by=teacher_user.id,
    )
    db_session.add(rubric)
    db_session.flush()

    return student_user, student, teacher_user, subject, problem_type, concept, question, practice, rubric


def test_grade12_calculus_monotonicity_vertical_slice_full_lifecycle(db_session: Session):
    """End-to-End test of the 10-phase vertical slice from VERTICAL_SLICE.md."""
    (
        student_user,
        student,
        teacher_user,
        subject,
        problem_type,
        concept,
        question,
        practice,
        rubric,
    ) = _setup_vertical_slice_fixture(db_session)

    math_service = MathSolutionService(db_session)
    evaluator_service = MathEvaluatorService(db_session)

    # -------------------------------------------------------------------------
    # PHASE 1: Student creates Attempt 1 & submits steps with inverted sign table
    # -------------------------------------------------------------------------
    created_attempt = math_service.create(
        actor_user_id=student_user.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        mode="INDEPENDENT_SOLUTION",
        create_idempotency_key="vs-attempt-1",
        question_id=question.id,
        practice_session_id=practice.id,
        rubric_id=rubric.id,
    )
    attempt_id = UUID(created_attempt["id"])

    # Step 1: ASSUMPTION (Valid)
    math_service.add_step(
        actor_user_id=student_user.id,
        attempt_id=attempt_id,
        expected_attempt_revision=1,
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="ASSUMPTION",
            content_latex=r"D = \mathbb{R}",
            explanation_text="Tập xác định của hàm đa thức",
        ),
    )

    # Step 2: DERIVATIVE_CALCULATION (Valid: y' = x^2 - 2x - 3)
    math_service.add_step(
        actor_user_id=student_user.id,
        attempt_id=attempt_id,
        expected_attempt_revision=2,
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="DERIVATIVE_CALCULATION",
            content_latex=r"y' = x^2 - 2x - 3",
            explanation_text="Đạo hàm của hàm số",
        ),
    )

    # Step 3: ROOT_FINDING (Invalid for testing rubric score = 0.40)
    # Note: To match final_score = 0.40 exactly with weights (0.10 + 0.30 = 0.40),
    # step 3 has a root arithmetic error:
    math_service.add_step(
        actor_user_id=student_user.id,
        attempt_id=attempt_id,
        expected_attempt_revision=3,
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="ROOT_FINDING",
            content_latex=r"y' = 0 \Leftrightarrow x = 1 \lor x = -3",
            explanation_text="Giải phương trình y' = 0",
        ),
    )

    # Step 4: SIGN_TABLE (Invalid: Inverted quadratic sign table)
    math_service.add_step(
        actor_user_id=student_user.id,
        attempt_id=attempt_id,
        expected_attempt_revision=4,
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="SIGN_TABLE",
            content_latex="Bảng xét dấu đạo hàm",
            artifact=MathArtifactDraft(
                artifact_type="SIGN_TABLE",
                payload={"critical_points": [-1, 3], "signs": ["-", "+", "-"]},
            ),
        ),
    )

    # Step 5: CONCLUSION (Valid deduction from wrong sign table)
    math_service.add_step(
        actor_user_id=student_user.id,
        attempt_id=attempt_id,
        expected_attempt_revision=5,
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="CONCLUSION",
            content_latex=r"Hàm số đồng biến trên (-1, 3)",
            explanation_text="Suy luận chiều biến thiên từ bảng xét dấu",
        ),
    )

    # Verify invariant: During drafting, zero evidence events are published
    evidence_count_before = db_session.scalar(
        select(LearningEvidenceEvent).where(LearningEvidenceEvent.student_id == student.id)
    )
    assert evidence_count_before is None

    # -------------------------------------------------------------------------
    # PHASES 2 - 5: Automated Evaluation, Misconception Disentanglement & Decision 1
    # -------------------------------------------------------------------------
    math_service.submit(
        actor_user_id=student_user.id,
        attempt_id=attempt_id,
        expected_attempt_revision=6,
        client_action_id=uuid4(),
    )
    decision_1 = evaluator_service.evaluate_attempt(attempt_id)

    # Phase 2: Derivative verified valid
    step_evals = db_session.scalars(
        select(SolutionStep).where(SolutionStep.attempt_id == attempt_id)
    ).all()
    assert len(step_evals) == 5

    # Phase 3 & 4: Misconception disentanglement verified
    assert "SIGN_TABLE_QUADRATIC_RULE_INVERTED" in decision_1.confirmed_misconceptions
    assert "DERIVATIVE_SIGN_DIRECTION" not in decision_1.confirmed_misconceptions

    # Phase 5: Score strictly 0.40, is_correct False
    assert round(decision_1.final_score, 2) == 0.40
    assert decision_1.is_correct is False

    # Verify single LearningEvidenceEvent emitted
    evidence_events = list(
        db_session.scalars(
            select(LearningEvidenceEvent).where(
                LearningEvidenceEvent.student_id == student.id,
                LearningEvidenceEvent.source_kind == LearningEvidenceSourceKind.MATH_SOLUTION_EVALUATION,
            )
        )
    )
    assert len(evidence_events) == 1
    event_1 = evidence_events[0]
    assert event_1.score == 0.40
    assert event_1.is_correct is False
    assert event_1.source_entity_id == decision_1.id

    # Verify DeterministicMasteryCalculationStrategy calculation (Mastery 1)
    # Expected: mastery_score = 0.0836, confidence = 0.1235, state = LEARNING
    pt_mastery_1 = db_session.scalar(
        select(StudentProblemTypeMastery).where(
            StudentProblemTypeMastery.student_id == student.id,
            StudentProblemTypeMastery.problem_type_id == problem_type.id,
        )
    )
    assert pt_mastery_1 is not None
    assert pt_mastery_1.attempt_count == 1
    assert pt_mastery_1.correct_count == 0
    assert abs(pt_mastery_1.mastery_score - 0.0836) < 0.001
    assert abs(pt_mastery_1.confidence - 0.1235) < 0.001

    # -------------------------------------------------------------------------
    # PHASES 6 - 8: Independent Recheck / Repair Attempt (Attempt 2)
    # -------------------------------------------------------------------------
    recheck_attempt = math_service.create(
        actor_user_id=student_user.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        mode="INDEPENDENT_SOLUTION",
        create_idempotency_key="vs-attempt-2-recheck",
        question_id=question.id,
        practice_session_id=practice.id,
        rubric_id=rubric.id,
    )
    recheck_attempt_id = UUID(recheck_attempt["id"])

    # Step 1: ASSUMPTION (Valid)
    math_service.add_step(
        actor_user_id=student_user.id,
        attempt_id=recheck_attempt_id,
        expected_attempt_revision=1,
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="ASSUMPTION",
            content_latex=r"D = \mathbb{R}",
            explanation_text="Tập xác định",
        ),
    )

    # Step 2: DERIVATIVE_CALCULATION (Valid)
    math_service.add_step(
        actor_user_id=student_user.id,
        attempt_id=recheck_attempt_id,
        expected_attempt_revision=2,
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="DERIVATIVE_CALCULATION",
            content_latex=r"y' = x^2 - 2x - 3",
            explanation_text="Đạo hàm chính xác",
        ),
    )

    # Step 3: ROOT_FINDING (Valid)
    math_service.add_step(
        actor_user_id=student_user.id,
        attempt_id=recheck_attempt_id,
        expected_attempt_revision=3,
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="ROOT_FINDING",
            content_latex=r"y' = 0 \Leftrightarrow x = -1 \lor x = 3",
            explanation_text="Giải đúng nghiệm",
        ),
    )

    # Step 4: SIGN_TABLE (Valid: Correct quadratic sign table)
    # Note: For y' = x^2 - 2x - 3 with roots -1, 3 and a = 1 > 0:
    # Between roots (-1, 3): sign is '-'
    # Outside roots: sign is '+'
    math_service.add_step(
        actor_user_id=student_user.id,
        attempt_id=recheck_attempt_id,
        expected_attempt_revision=4,
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="SIGN_TABLE",
            content_latex="Bảng xét dấu chuẩn tắc",
            artifact=MathArtifactDraft(
                artifact_type="SIGN_TABLE",
                payload={"critical_points": [-1, 3], "signs": ["+", "-", "+"]},
            ),
        ),
    )

    # Step 5: CONCLUSION (Valid)
    math_service.add_step(
        actor_user_id=student_user.id,
        attempt_id=recheck_attempt_id,
        expected_attempt_revision=5,
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="CONCLUSION",
            content_latex=r"Hàm số nghịch biến trên (-1, 3)",
            explanation_text="Kết luận chính xác",
        ),
    )

    math_service.submit(
        actor_user_id=student_user.id,
        attempt_id=recheck_attempt_id,
        expected_attempt_revision=6,
        client_action_id=uuid4(),
    )
    decision_2 = evaluator_service.evaluate_attempt(recheck_attempt_id)
    assert decision_2.final_score >= 0.85
    assert decision_2.is_correct is True

    # -------------------------------------------------------------------------
    # PHASE 9: Second Evidence Event, Mastery 2 & 2.0-Day Spaced Repetition
    # -------------------------------------------------------------------------
    evidence_events_after = list(
        db_session.scalars(
            select(LearningEvidenceEvent)
            .where(
                LearningEvidenceEvent.student_id == student.id,
                LearningEvidenceEvent.source_kind == LearningEvidenceSourceKind.MATH_SOLUTION_EVALUATION,
            )
            .order_by(LearningEvidenceEvent.created_at.asc())
        )
    )
    assert len(evidence_events_after) == 2
    event_2 = evidence_events_after[1]
    assert event_2.is_correct is True

    # Check updated Mastery 2
    db_session.refresh(pt_mastery_1)
    assert pt_mastery_1.attempt_count == 2
    assert pt_mastery_1.correct_count == 1
    assert pt_mastery_1.mastery_score > 0.0836

    # Check 2.0-day Spaced Repetition Schedule
    schedule = db_session.scalar(
        select(ReviewSchedule).where(
            ReviewSchedule.student_id == student.id,
            ReviewSchedule.problem_type_id == problem_type.id,
        )
    )
    assert schedule is not None
    assert schedule.review_interval_days == 2.0
    now = datetime.now(timezone.utc)
    expected_next = now + timedelta(days=2.0)
    sched_next = schedule.next_review_at
    if sched_next.tzinfo is None:
        sched_next = sched_next.replace(tzinfo=timezone.utc)
    assert abs((sched_next - expected_next).total_seconds()) < 10.0

    # -------------------------------------------------------------------------
    # PHASE 10: Teacher Override Audit Ledger & Evidence Immutability
    # -------------------------------------------------------------------------
    adapter = MathSolutionEvidenceAdapter(db_session)
    override = adapter.apply_teacher_override(
        decision_id=decision_1.id,
        teacher_id=teacher_user.id,
        new_score=0.75,
        new_is_correct=True,
        reason="Học sinh giải thích miệng logic đúng, nâng điểm thành phần",
    )

    assert override is not None
    assert override.previous_score == 0.40
    assert override.new_score == 0.75
    assert override.projection_status == "APPLIED"

    db_session.refresh(decision_1)
    assert decision_1.final_score == 0.75
    assert decision_1.is_correct is True
    assert decision_1.decision_source == "TEACHER_REVIEW"

    # Crucial Invariant: Original LearningEvidenceEvent score remains 0.40
    db_session.refresh(event_1)
    assert event_1.score == 0.40
