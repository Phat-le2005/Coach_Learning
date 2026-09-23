from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
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
from app.questions.models import (
    CognitiveLevel,
    Question,
    QuestionConcept,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.repair.policy import RepairPolicy
from app.repair.schemas import (
    RepairAnswerSubmit,
    RepairSessionCreate,
    RepairStepRole,
    RepairTargetType,
    RepairTriggerType,
)
from app.repair.service import RepairSessionService
from app.students.models import StudentProfile
from app.users.models import Role, User
from tests.practice.conftest import (
    PracticeContent,
    practice_content,
    practice_students,
    practice_user_factory,
    student_profile,
)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def repair_questions_pool(
    db_session: Session, practice_content: PracticeContent
) -> list[Question]:
    """Create a graded pool of APPROVED questions with varying difficulty."""
    creator_id = practice_content.mcq.created_by
    subject_id = practice_content.subject.id
    pt_id = practice_content.problem_type.id
    c_id = practice_content.concept.id

    questions = []
    difficulties = [0.10, 0.20, 0.30, 0.40]

    for i, diff in enumerate(difficulties):
        q = Question(
            subject_id=subject_id,
            content=f"Câu hỏi luyện tập khắc phục số {i + 1} (độ khó {diff})?",
            content_hash=f"{uuid4().hex}{uuid4().hex}",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=diff,
            correct_answer="A",
            explanation=f"Hướng dẫn giải chi tiết cho câu {i + 1}.",
            source_type="BANK",
            exam_weight=1.0,
            status=QuestionStatus.APPROVED,
            created_by=creator_id,
        )
        db_session.add(q)
        db_session.flush()

        opt_a = QuestionOption(
            question_id=q.id, label="A", content="Đáp án đúng", order_index=0
        )
        opt_b = QuestionOption(
            question_id=q.id, label="B", content="Đáp án sai", order_index=1
        )
        db_session.add_all([opt_a, opt_b])

        qpt = QuestionProblemType(
            question_id=q.id,
            problem_type_id=pt_id,
            is_primary=True,
            weight=1.0,
        )
        qc = QuestionConcept(
            question_id=q.id,
            concept_id=c_id,
            weight=1.0,
        )
        db_session.add_all([qpt, qc])
        questions.append(q)

    # Add a DRAFT question to ensure question source guardrail filters it out
    draft_q = Question(
        subject_id=subject_id,
        content="Câu hỏi DRAFT không được đưa vào bài chính thức.",
        content_hash=f"{uuid4().hex}{uuid4().hex}",
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=0.20,
        correct_answer="A",
        source_type="AI_GENERATED",
        exam_weight=1.0,
        status=QuestionStatus.DRAFT,
        created_by=creator_id,
    )
    db_session.add(draft_q)
    db_session.flush()
    db_session.add(
        QuestionProblemType(
            question_id=draft_q.id, problem_type_id=pt_id, is_primary=True
        )
    )

    db_session.commit()
    return questions


@pytest.fixture
def prereq_concept_with_questions(
    db_session: Session, practice_content: PracticeContent
) -> tuple[Concept, list[Question]]:
    """Create a prerequisite concept with approved questions."""
    creator_id = practice_content.mcq.created_by
    subject_id = practice_content.subject.id

    prereq = Concept(
        subject_id=subject_id,
        code="PREREQ_INEQUALITY",
        name="Bất phương trình cơ bản",
        description="Kiến thức bất phương trình bậc nhất và hai.",
        grade_level=10,
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

    questions = []
    for i in range(4):
        q = Question(
            subject_id=subject_id,
            content=f"Câu hỏi kiến thức tiên quyết {i + 1}?",
            content_hash=f"{uuid4().hex}{uuid4().hex}",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=0.20 + (i * 0.15),
            correct_answer="A",
            explanation=f"Giải thích câu tiên quyết {i + 1}.",
            source_type="BANK",
            exam_weight=1.0,
            status=QuestionStatus.APPROVED,
            created_by=creator_id,
        )
        db_session.add(q)
        db_session.flush()

        opt_a = QuestionOption(
            question_id=q.id, label="A", content="Đúng", order_index=0
        )
        opt_b = QuestionOption(
            question_id=q.id, label="B", content="Sai", order_index=1
        )
        db_session.add_all([opt_a, opt_b])
        db_session.add(QuestionConcept(question_id=q.id, concept_id=prereq.id, weight=1.0))
        questions.append(q)

    db_session.commit()
    return prereq, questions


# --------------------------------------------------------------------------
# 1. Start Repair Session: ProblemType Target & 5-Step Sequence
# --------------------------------------------------------------------------


def test_start_repair_session_problem_type_target(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
    repair_questions_pool: list[Question],
) -> None:
    student, _ = practice_students
    service = RepairSessionService(db_session)

    data = RepairSessionCreate(
        trigger=RepairTriggerType.LOW_PROBLEM_TYPE_MASTERY,
        target_type=RepairTargetType.PROBLEM_TYPE,
        target_id=practice_content.problem_type.id,
    )

    session_read = service.start_repair_session(student, data)

    # 1. Session metadata
    assert session_read.target_type == RepairTargetType.PROBLEM_TYPE
    assert session_read.target_id == practice_content.problem_type.id
    assert session_read.status == PracticeSessionStatus.ACTIVE
    assert not session_read.is_completed

    # 2. Sequence has exactly 5 steps
    assert len(session_read.steps) == 5

    # Step 1: Brief Review (Pedagogical recap)
    s1 = session_read.steps[0]
    assert s1.step_number == 1
    assert s1.role == RepairStepRole.BRIEF_REVIEW
    assert s1.review_content is not None
    assert len(s1.review_content) > 20
    assert s1.question_id is None

    # Step 2: Easy Verification
    s2 = session_read.steps[1]
    assert s2.step_number == 2
    assert s2.role == RepairStepRole.EASY_VERIFICATION
    assert s2.question_id is not None
    assert s2.difficulty <= 0.40

    # Step 3: Guided Practice (Hints available)
    s3 = session_read.steps[2]
    assert s3.step_number == 3
    assert s3.role == RepairStepRole.GUIDED_PRACTICE
    assert s3.hints_available is True

    # Step 4: Medium Practice
    s4 = session_read.steps[3]
    assert s4.step_number == 4
    assert s4.role == RepairStepRole.MEDIUM_PRACTICE

    # Step 5: Final Recheck
    s5 = session_read.steps[4]
    assert s5.step_number == 5
    assert s5.role == RepairStepRole.FINAL_RECHECK


# --------------------------------------------------------------------------
# 2. Start Repair Session: Prerequisite Concept Target
# --------------------------------------------------------------------------


def test_start_repair_session_prerequisite_concept_target(
    db_session: Session,
    practice_students: tuple[User, User],
    prereq_concept_with_questions: tuple[Concept, list[Question]],
) -> None:
    student, _ = practice_students
    concept, questions = prereq_concept_with_questions
    service = RepairSessionService(db_session)

    data = RepairSessionCreate(
        trigger=RepairTriggerType.KNOWLEDGE_GAP_DETECTED,
        target_type=RepairTargetType.PREREQUISITE_CONCEPT,
        target_id=concept.id,
    )

    session_read = service.start_repair_session(student, data)

    assert session_read.target_type == RepairTargetType.PREREQUISITE_CONCEPT
    assert session_read.target_id == concept.id
    assert session_read.target_name == concept.name
    assert len(session_read.steps) == 5

    # Questions are drawn from the prerequisite concept question bank
    assigned_q_ids = {s.question_id for s in session_read.steps if s.question_id}
    prereq_q_ids = {q.id for q in questions}
    assert assigned_q_ids.issubset(prereq_q_ids)


# --------------------------------------------------------------------------
# 3. Question Bank Guardrail: Never Selects DRAFT Questions
# --------------------------------------------------------------------------


def test_question_bank_guardrail_only_selects_approved(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
    repair_questions_pool: list[Question],
) -> None:
    student, _ = practice_students
    service = RepairSessionService(db_session)

    data = RepairSessionCreate(
        trigger=RepairTriggerType.REPEATED_WRONG_ATTEMPTS,
        target_type=RepairTargetType.PROBLEM_TYPE,
        target_id=practice_content.problem_type.id,
    )

    session_read = service.start_repair_session(student, data)

    assigned_q_ids = [s.question_id for s in session_read.steps if s.question_id]
    assigned_questions = db_session.scalars(
        select(Question).where(Question.id.in_(assigned_q_ids))
    ).all()

    for q in assigned_questions:
        assert q.status == QuestionStatus.APPROVED
        assert q.status != QuestionStatus.DRAFT


# --------------------------------------------------------------------------
# 4. Answer Flow & Mastery Engine Integration
# --------------------------------------------------------------------------


def test_repair_answer_flow_into_mastery_engine(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    repair_questions_pool: list[Question],
) -> None:
    student, _ = practice_students
    service = RepairSessionService(db_session)

    data = RepairSessionCreate(
        trigger=RepairTriggerType.LOW_PROBLEM_TYPE_MASTERY,
        target_type=RepairTargetType.PROBLEM_TYPE,
        target_id=practice_content.problem_type.id,
    )
    session_read = service.start_repair_session(student, data)

    # Submit answer for Step 2 (Question 1)
    res_2 = service.submit_step_answer(
        student,
        session_read.id,
        step_number=2,
        data=RepairAnswerSubmit(student_answer="A", response_time_seconds=20.0),
    )
    assert res_2.is_correct is True
    assert res_2.score == 1.0

    # Verify standard QuestionAttempt was persisted
    attempt = db_session.scalar(
        select(QuestionAttempt).where(
            QuestionAttempt.practice_session_id == session_read.id,
            QuestionAttempt.question_id == res_2.question_id,
        )
    )
    assert attempt is not None
    assert attempt.is_correct is True
    assert attempt.score == 1.0
    assert attempt.evaluation_status == EvaluationStatus.AUTO_EVALUATED

    # Verify Mastery Engine was updated deterministically
    mastery = db_session.scalar(
        select(StudentProblemTypeMastery).where(
            StudentProblemTypeMastery.student_id == student_profile.id,
            StudentProblemTypeMastery.problem_type_id == practice_content.problem_type.id,
        )
    )
    assert mastery is not None
    assert mastery.attempt_count >= 1
    assert mastery.correct_count >= 1


# --------------------------------------------------------------------------
# 5. Deterministic Success Evaluation: Meets All Criteria
# --------------------------------------------------------------------------


def test_repair_session_deterministic_success(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    repair_questions_pool: list[Question],
) -> None:
    student, _ = practice_students
    service = RepairSessionService(
        db_session,
        policy=RepairPolicy(min_performance_threshold=0.70, require_final_recheck_correct=True),
    )

    data = RepairSessionCreate(
        trigger=RepairTriggerType.LOW_PROBLEM_TYPE_MASTERY,
        target_type=RepairTargetType.PROBLEM_TYPE,
        target_id=practice_content.problem_type.id,
    )
    session_read = service.start_repair_session(student, data)

    # Answer steps 2, 3, 4, 5 (all correct 'A')
    for step_no in range(2, 6):
        service.submit_step_answer(
            student,
            session_read.id,
            step_number=step_no,
            data=RepairAnswerSubmit(student_answer="A"),
        )

    eval_result = service.evaluate_session_completion(student, session_read.id)

    # 1. Success criteria satisfied
    assert eval_result.is_successful is True
    assert eval_result.average_score == 1.0
    assert eval_result.final_recheck_correct is True
    assert eval_result.evidence_count == 4
    assert eval_result.resolution_status == "RESOLVED"
    assert eval_result.status == PracticeSessionStatus.COMPLETED


# --------------------------------------------------------------------------
# 6. Failure Evaluation: High Average Score but Final Recheck Wrong
# --------------------------------------------------------------------------


def test_repair_session_failure_when_final_recheck_wrong(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
    repair_questions_pool: list[Question],
) -> None:
    student, _ = practice_students
    service = RepairSessionService(
        db_session,
        policy=RepairPolicy(min_performance_threshold=0.70, require_final_recheck_correct=True),
    )

    data = RepairSessionCreate(
        trigger=RepairTriggerType.LOW_PROBLEM_TYPE_MASTERY,
        target_type=RepairTargetType.PROBLEM_TYPE,
        target_id=practice_content.problem_type.id,
    )
    session_read = service.start_repair_session(student, data)

    # Steps 2, 3, 4 correct (score 1.0 each)
    for step_no in [2, 3, 4]:
        service.submit_step_answer(
            student,
            session_read.id,
            step_number=step_no,
            data=RepairAnswerSubmit(student_answer="A"),
        )

    # Step 5 (Final Recheck) answered WRONGLY
    service.submit_step_answer(
        student,
        session_read.id,
        step_number=5,
        data=RepairAnswerSubmit(student_answer="B"),  # Wrong answer
    )

    eval_result = service.evaluate_session_completion(student, session_read.id)

    # Average score is 3/4 = 0.75 >= 0.70, but Final Recheck is FALSE!
    assert eval_result.average_score == 0.75
    assert eval_result.final_recheck_correct is False
    assert eval_result.is_successful is False
    assert eval_result.resolution_status == "NEEDS_FURTHER_PRACTICE"
    assert "Final Recheck" in eval_result.summary_message


# --------------------------------------------------------------------------
# 7. Failure Evaluation: Final Recheck Correct but Average Score Below Threshold
# --------------------------------------------------------------------------


def test_repair_session_failure_when_average_score_too_low(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
    repair_questions_pool: list[Question],
) -> None:
    student, _ = practice_students
    service = RepairSessionService(
        db_session,
        policy=RepairPolicy(min_performance_threshold=0.70, require_final_recheck_correct=True),
    )

    data = RepairSessionCreate(
        trigger=RepairTriggerType.LOW_PROBLEM_TYPE_MASTERY,
        target_type=RepairTargetType.PROBLEM_TYPE,
        target_id=practice_content.problem_type.id,
    )
    session_read = service.start_repair_session(student, data)

    # Steps 2, 3 wrong ('B')
    for step_no in [2, 3]:
        service.submit_step_answer(
            student,
            session_read.id,
            step_number=step_no,
            data=RepairAnswerSubmit(student_answer="B"),
        )

    # Steps 4, 5 correct ('A')
    for step_no in [4, 5]:
        service.submit_step_answer(
            student,
            session_read.id,
            step_number=step_no,
            data=RepairAnswerSubmit(student_answer="A"),
        )

    eval_result = service.evaluate_session_completion(student, session_read.id)

    # Average score is 2/4 = 0.50 (< 0.70 threshold)
    assert eval_result.average_score == 0.50
    assert eval_result.final_recheck_correct is True
    assert eval_result.is_successful is False
    assert eval_result.resolution_status == "NEEDS_FURTHER_PRACTICE"


# --------------------------------------------------------------------------
# 8. Success Resolves Persistent Misconception
# --------------------------------------------------------------------------


def test_repair_session_resolves_persistent_misconception(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    repair_questions_pool: list[Question],
) -> None:
    student, _ = practice_students
    service = RepairSessionService(db_session)

    # Setup confirmed misconception
    m_def = MisconceptionDefinition(
        code="TEST_REPAIR_MISCONCEPTION",
        concept_id=practice_content.concept.id,
        problem_type_id=practice_content.problem_type.id,
        name="Lỗi sai kiểm thử repair",
        description="Mô tả lỗi sai.",
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
        occurrence_count=2,
        status=StudentMisconceptionStatus.CONFIRMED,
        first_detected_at=now,
        last_detected_at=now,
    )
    db_session.add(student_m)
    db_session.commit()

    data = RepairSessionCreate(
        trigger=RepairTriggerType.PERSISTENT_MISCONCEPTION,
        target_type=RepairTargetType.PROBLEM_TYPE,
        target_id=practice_content.problem_type.id,
        misconception_definition_id=m_def.id,
    )
    session_read = service.start_repair_session(student, data)

    # Answer all steps correctly
    for step_no in range(2, 6):
        service.submit_step_answer(
            student,
            session_read.id,
            step_number=step_no,
            data=RepairAnswerSubmit(student_answer="A"),
        )

    eval_result = service.evaluate_session_completion(
        student,
        session_read.id,
        misconception_definition_id=m_def.id,
    )

    assert eval_result.is_successful is True
    assert eval_result.misconception_resolved is True

    # Check database state: Misconception status is now RESOLVED
    db_session.refresh(student_m)
    assert student_m.status == StudentMisconceptionStatus.RESOLVED
    assert student_m.resolved_at is not None
