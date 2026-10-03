from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment
from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.knowledge_gap.models import (
    RootCauseDiagnosis,
    RootCauseVerification,
    RootCauseVerificationOutcome,
    RootCauseVerificationStatus,
    RootCauseVerificationTarget,
    RootCauseVerificationTargetType,
)
from app.learning.feedback_models import (
    LearningFeedbackAction,
    LearningFeedbackDecision,
    LearningFeedbackReasonCode,
)
from app.learning.feedback_policy import LearningFeedbackPolicy
from app.learning.feedback_service import LearningFeedbackService
from app.learning_evidence.models import LearningEvidenceEvent
from app.mastery.models import StudentConceptMastery
from app.misconceptions.models import (
    MisconceptionCategory,
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.planning.models import TeachingPlan, TeachingPlanItem, TeachingPlanStatus
from app.practice.models import (
    PracticeSession,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.questions.models import (
    CognitiveLevel,
    Question,
    QuestionConcept,
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.repair.adaptive_service import AdaptiveRepairService
from app.repair.models import (
    AdaptiveRepairOutcome,
    AdaptiveRepairPhase,
    AdaptiveRepairSession,
    AdaptiveRepairStatus,
)
from app.repair.schemas import AdaptiveRepairAnswerResult, AdaptiveRepairAnswerSubmit
from app.review.models import ReviewSchedule
from app.review.service import ReviewScheduleService
from app.students.models import StudentProfile
from app.users.models import Role, User
from tests.knowledge_gap.test_verification import _create_diagnosis
from tests.practice.conftest import (
    PracticeContent,
    practice_bearer,
    practice_content,
    practice_students,
    practice_user_factory,
    student_profile,
)
from tests.repair.test_adaptive_repair import (
    _archive_existing_approved_questions,
    _repair_question,
    _supported_diagnosis,
)


def _submit_answer(
    service: AdaptiveRepairService,
    user: User,
    session_id: UUID,
    is_correct: bool = True,
) -> AdaptiveRepairAnswerResult:
    session_read = service.get(user, session_id)
    item = session_read.current_item
    assert item is not None, "Cannot submit answer when current_item is None"
    question = service.session.get(Question, item.question_id)
    assert question is not None

    if is_correct:
        ans = question.correct_answer or "A"
    else:
        if question.question_type == QuestionType.TRUE_FALSE:
            ans = "FALSE" if (question.correct_answer or "").upper() == "TRUE" else "TRUE"
        elif question.question_type == QuestionType.MULTIPLE_CHOICE:
            ans = "B" if (question.correct_answer or "").upper() == "A" else "A"
        else:
            ans = "wrong_answer"

    return service.answer_current(
        user,
        session_id,
        AdaptiveRepairAnswerSubmit(item_id=item.id, student_answer=ans),
    )


def test_resolved_creates_review_schedule_and_returns_to_learning(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    diagnosis, target, _ = _supported_diagnosis(
        db_session, practice_content, student_profile, average_score=0.75, question_count=10
    )
    service = AdaptiveRepairService(db_session)
    started = service.start(practice_students[0], diagnosis.id)

    # 4 consecutive correct answers resolve the session
    for _ in range(4):
        _submit_answer(service, practice_students[0], started.id, is_correct=True)

    adaptive = db_session.get(AdaptiveRepairSession, started.id)
    assert adaptive.status == AdaptiveRepairStatus.COMPLETED
    assert adaptive.outcome == AdaptiveRepairOutcome.RESOLVED

    feedback_svc = LearningFeedbackService(db_session)
    decision = feedback_svc.resolve_feedback(started.id)

    assert decision.action in {
        LearningFeedbackAction.RETURN_TO_CURRENT_LEARNING,
        LearningFeedbackAction.NO_ACTIVE_LEARNING,
    }
    assert decision.retry.allowed is False
    assert decision.retry.current_cycle == 1
    assert decision.review is not None
    assert decision.review.schedule_id is not None
    assert decision.review.next_review_at is not None

    schedule = db_session.get(ReviewSchedule, decision.review.schedule_id)
    assert schedule is not None
    assert schedule.student_id == student_profile.id
    assert schedule.concept_id == practice_content.concept.id
    assert schedule.review_interval_days == 2.0
    assert schedule.next_review_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)

    # Idempotent: repeated resolution returns same decision and does not duplicate schedule
    repeat = feedback_svc.resolve_feedback(started.id)
    assert repeat.id == decision.id
    assert repeat.review.schedule_id == schedule.id
    assert db_session.scalar(select(func.count()).select_from(LearningFeedbackDecision)) == 1
    assert db_session.scalar(select(func.count()).select_from(ReviewSchedule)) == 1


def test_resolved_with_active_teaching_plan_returns_to_current_lesson(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)

    # 1. Setup a distinct ProblemType PT2 and Concept in the subject
    concept2 = Concept(
        subject_id=practice_content.subject.id,
        code=f"CONCEPT_CURRENT_{uuid4().hex[:6].upper()}",
        name="Current Lesson Concept",
        description="Current lesson concept",
        grade_level=12,
        order_index=99,
    )
    db_session.add(concept2)
    db_session.flush()

    pt2 = ProblemType(
        topic_id=practice_content.problem_type.topic_id,
        code=f"PT_CURRENT_{uuid4().hex[:6].upper()}",
        name="Current Lesson Problem Type",
        order_index=99,
        is_active=True,
    )
    db_session.add(pt2)
    db_session.flush()

    # Create approved question for PT2
    q_pt2 = Question(
        subject_id=practice_content.subject.id,
        content=f"Current lesson question {uuid4()}",
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=0.5,
        correct_answer="A",
        explanation="Explain",
        source_type="TEST",
        exam_weight=0.5,
        status=QuestionStatus.APPROVED,
        cognitive_level=CognitiveLevel.APPLY,
        created_by=practice_content.mcq.created_by,
        options=[
            QuestionOption(label="A", content="Correct", order_index=0),
            QuestionOption(label="B", content="Wrong", order_index=1),
        ],
        problem_type_links=[QuestionProblemType(problem_type_id=pt2.id, weight=1.0, is_primary=True)],
        concept_links=[QuestionConcept(concept_id=concept2.id, weight=1.0)],
        learning_outcome_links=[QuestionLearningOutcome(learning_outcome_id=practice_content.learning_outcome.id, weight=1.0)],
    )
    db_session.add(q_pt2)

    # Setup classroom and enrollment
    classroom = Classroom(
        name="12A1 Test Class",
        academic_year="2025-2026",
        grade_level=12,
        created_by=practice_content.mcq.created_by,
    )
    db_session.add(classroom)
    db_session.flush()

    enrollment = StudentEnrollment(
        classroom_id=classroom.id,
        student_id=student_profile.id,
        status=EnrollmentStatus.ACTIVE,
    )
    db_session.add(enrollment)

    # Setup ACTIVE TeachingPlan targeting pt2
    teaching_plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=practice_content.subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.ACTIVE,
        created_by=practice_content.mcq.created_by,
        items=[TeachingPlanItem(problem_type_id=pt2.id, priority=10, order_index=0)],
    )
    db_session.add(teaching_plan)
    db_session.flush()

    # 2. Setup diagnosis & repair on concept (distinct from PT2)
    diagnosis, target, _ = _supported_diagnosis(
        db_session, practice_content, student_profile, average_score=0.75, question_count=10
    )
    service = AdaptiveRepairService(db_session)
    started = service.start(practice_students[0], diagnosis.id)

    # 4 consecutive correct answers resolve
    for _ in range(4):
        _submit_answer(service, practice_students[0], started.id, is_correct=True)

    feedback_svc = LearningFeedbackService(db_session)
    decision = feedback_svc.resolve_feedback(started.id)

    assert decision.action == LearningFeedbackAction.RETURN_TO_CURRENT_LEARNING
    assert decision.reason_code == LearningFeedbackReasonCode.CURRENT_LESSON_AVAILABLE
    assert decision.next_learning is not None
    assert decision.next_learning.problem_type_id == pt2.id
    assert decision.next_learning.recommended_question_id == q_pt2.id
    assert decision.retry.allowed is False


def test_needs_more_practice_cycle1_authorizes_retry_and_prevents_question_reuse(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    diagnosis, target, questions = _supported_diagnosis(
        db_session, practice_content, student_profile, average_score=0.25, question_count=16
    )
    service = AdaptiveRepairService(db_session)
    started = service.start(practice_students[0], diagnosis.id)

    # Answer wrong 8 times to hit max_questions and complete with NEEDS_MORE_PRACTICE
    for _ in range(8):
        _submit_answer(service, practice_students[0], started.id, is_correct=False)

    adaptive_c1 = db_session.get(AdaptiveRepairSession, started.id)
    assert adaptive_c1.status == AdaptiveRepairStatus.COMPLETED
    assert adaptive_c1.outcome == AdaptiveRepairOutcome.NEEDS_MORE_PRACTICE
    assert adaptive_c1.repair_cycle_index == 1

    feedback_svc = LearningFeedbackService(db_session)
    decision = feedback_svc.resolve_feedback(started.id)

    assert decision.action == LearningFeedbackAction.RETRY_REPAIR
    assert decision.reason_code == LearningFeedbackReasonCode.REPAIR_NEEDS_MORE_RETRY_AVAILABLE
    assert decision.retry.allowed is True
    assert decision.retry.current_cycle == 1

    cycle1_qids = {item.question_id for item in adaptive_c1.items}
    assert len(cycle1_qids) == 8

    # Start Retry -> creates Cycle 2
    retry_session = service.retry(practice_students[0], started.id)

    assert retry_session.id != started.id
    assert retry_session.repair_cycle_index == 2
    assert retry_session.previous_adaptive_repair_session_id == started.id
    assert retry_session.status == AdaptiveRepairStatus.ACTIVE
    assert retry_session.current_item is not None
    # Question in cycle 2 must NEVER be one from cycle 1
    assert retry_session.current_item.question_id not in cycle1_qids
    assert retry_session.initial_difficulty == pytest.approx(
        max(service.policy.min_difficulty, adaptive_c1.current_difficulty - 0.10)
    )

    # Calling retry again is idempotent
    retry_again = service.retry(practice_students[0], started.id)
    assert retry_again.id == retry_session.id


def test_needs_more_practice_cycle2_reaches_retry_limit(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    diagnosis, target, _ = _supported_diagnosis(
        db_session, practice_content, student_profile, average_score=0.25, question_count=20
    )
    service = AdaptiveRepairService(db_session)
    c1 = service.start(practice_students[0], diagnosis.id)

    # Cycle 1 answers wrong 8 times -> NEEDS_MORE_PRACTICE
    for _ in range(8):
        _submit_answer(service, practice_students[0], c1.id, is_correct=False)

    # Cycle 2 retry
    c2 = service.retry(practice_students[0], c1.id)
    assert c2.repair_cycle_index == 2

    # Cycle 2 answers wrong 8 times -> completes with NEEDS_MORE_PRACTICE
    for _ in range(8):
        _submit_answer(service, practice_students[0], c2.id, is_correct=False)

    adaptive_c2 = db_session.get(AdaptiveRepairSession, c2.id)
    assert adaptive_c2.status == AdaptiveRepairStatus.COMPLETED
    assert adaptive_c2.outcome == AdaptiveRepairOutcome.NEEDS_MORE_PRACTICE

    feedback_svc = LearningFeedbackService(db_session)
    decision = feedback_svc.resolve_feedback(c2.id)

    assert decision.action == LearningFeedbackAction.COLLECT_MORE_EVIDENCE
    assert decision.reason_code == LearningFeedbackReasonCode.REPAIR_RETRY_LIMIT_REACHED
    assert decision.retry.allowed is False
    assert decision.retry.current_cycle == 2

    # Attempting to retry cycle 2 must fail with 409
    with pytest.raises(ApplicationError) as err:
        service.retry(practice_students[0], c2.id)
    assert err.value.status_code == 409
    assert err.value.code == "REPAIR_RETRY_NOT_ALLOWED"


def test_bank_exhausted_creates_question_supply_gap_and_denies_retry(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    # Only 1 question exists in the bank
    diagnosis, target, _ = _supported_diagnosis(
        db_session, practice_content, student_profile, average_score=0.25, question_count=1
    )
    service = AdaptiveRepairService(db_session)
    started = service.start(practice_students[0], diagnosis.id)

    # Answering wrong requires next question, but bank is exhausted
    res = _submit_answer(service, practice_students[0], started.id, is_correct=False)
    assert res.session.outcome == AdaptiveRepairOutcome.BANK_EXHAUSTED
    assert res.session.status == AdaptiveRepairStatus.COMPLETED

    feedback_svc = LearningFeedbackService(db_session)
    decision = feedback_svc.resolve_feedback(started.id)

    assert decision.action == LearningFeedbackAction.QUESTION_SUPPLY_GAP
    assert decision.reason_code == LearningFeedbackReasonCode.REPAIR_BANK_EXHAUSTED
    assert decision.retry.allowed is False
    assert decision.target is not None
    assert decision.target.concept_id == practice_content.concept.id

    # Retry denied
    with pytest.raises(ApplicationError) as err:
        service.retry(practice_students[0], started.id)
    assert err.value.status_code == 409
    assert err.value.code == "REPAIR_RETRY_NOT_ALLOWED"


def test_needs_more_practice_with_exhausted_bank_produces_question_supply_gap(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    # Create exactly 8 questions, so all 8 are consumed in cycle 1
    diagnosis, target, _ = _supported_diagnosis(
        db_session, practice_content, student_profile, average_score=0.25, question_count=8
    )
    service = AdaptiveRepairService(db_session)
    started = service.start(practice_students[0], diagnosis.id)

    for _ in range(8):
        _submit_answer(service, practice_students[0], started.id, is_correct=False)

    adaptive_c1 = db_session.get(AdaptiveRepairSession, started.id)
    assert adaptive_c1.outcome == AdaptiveRepairOutcome.NEEDS_MORE_PRACTICE

    feedback_svc = LearningFeedbackService(db_session)
    decision = feedback_svc.resolve_feedback(started.id)

    # No fresh questions exist for retry -> QUESTION_SUPPLY_GAP
    assert decision.action == LearningFeedbackAction.QUESTION_SUPPLY_GAP
    assert decision.reason_code == LearningFeedbackReasonCode.REPAIR_NEEDS_MORE_NO_QUESTIONS
    assert decision.retry.allowed is False


def test_existing_review_schedule_reused_without_overwrite(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    # 1. Mature review schedule already exists with interval 14 days
    existing_next = datetime.now(timezone.utc) + timedelta(days=14)
    existing_sched = ReviewSchedule(
        student_id=student_profile.id,
        concept_id=practice_content.concept.id,
        problem_type_id=None,
        next_review_at=existing_next,
        review_interval_days=14.0,
        review_count=3,
    )
    db_session.add(existing_sched)
    db_session.commit()

    # 2. Repair resolves
    diagnosis, target, _ = _supported_diagnosis(
        db_session, practice_content, student_profile, average_score=0.75, question_count=6
    )
    service = AdaptiveRepairService(db_session)
    started = service.start(practice_students[0], diagnosis.id)

    for _ in range(4):
        _submit_answer(service, practice_students[0], started.id, is_correct=True)

    feedback_svc = LearningFeedbackService(db_session)
    decision = feedback_svc.resolve_feedback(started.id)

    assert decision.review is not None
    assert decision.review.schedule_id == existing_sched.id

    sched_after = db_session.get(ReviewSchedule, existing_sched.id)
    assert sched_after.review_interval_days == 14.0
    assert sched_after.next_review_at == existing_next
    assert db_session.scalar(select(func.count()).select_from(ReviewSchedule)) == 1


def test_misconception_target_schedules_concept_review_and_leaves_misconception_status_untouched(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    # Setup misconception definition and student misconception
    mis_def = MisconceptionDefinition(
        concept_id=practice_content.concept.id,
        code=f"MISC_TEST_{uuid4().hex[:6].upper()}",
        name="Test Misconception",
        description="Common confusion",
        category=MisconceptionCategory.CONCEPTUAL,
    )
    db_session.add(mis_def)
    db_session.flush()

    student_misc = StudentMisconception(
        student_id=student_profile.id,
        misconception_definition_id=mis_def.id,
        status=StudentMisconceptionStatus.CONFIRMED,
        confidence=0.85,
        occurrence_count=2,
        first_detected_at=datetime.now(timezone.utc),
        last_detected_at=datetime.now(timezone.utc),
        resolved_at=None,
    )
    db_session.add(student_misc)
    db_session.flush()

    # Create diagnosis targeting this misconception
    diagnosis, target, _ = _supported_diagnosis(
        db_session, practice_content, student_profile, average_score=0.75, question_count=6
    )
    target.target_type = RootCauseVerificationTargetType.MISCONCEPTION
    target.misconception_definition_id = mis_def.id
    db_session.commit()

    service = AdaptiveRepairService(db_session)
    started = service.start(practice_students[0], diagnosis.id)

    for _ in range(4):
        _submit_answer(service, practice_students[0], started.id, is_correct=True)

    feedback_svc = LearningFeedbackService(db_session)
    decision = feedback_svc.resolve_feedback(started.id)

    assert decision.review is not None
    assert decision.review.schedule_id is not None

    sched = db_session.get(ReviewSchedule, decision.review.schedule_id)
    assert sched.concept_id == practice_content.concept.id

    # Misconception permanent status must NOT be changed to RESOLVED
    reloaded_misc = db_session.get(
        StudentMisconception,
        (student_profile.id, mis_def.id),
    )
    assert reloaded_misc.status == StudentMisconceptionStatus.CONFIRMED


def test_retry_evidence_suppresses_nested_diagnoses(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    diagnosis, target, _ = _supported_diagnosis(
        db_session, practice_content, student_profile, average_score=0.25, question_count=18
    )
    service = AdaptiveRepairService(db_session)
    c1 = service.start(practice_students[0], diagnosis.id)

    for _ in range(8):
        _submit_answer(service, practice_students[0], c1.id, is_correct=False)

    c2 = service.retry(practice_students[0], c1.id)
    diagnoses_before = db_session.scalar(select(func.count()).select_from(RootCauseDiagnosis))

    # Wrong answer in cycle 2
    res = _submit_answer(service, practice_students[0], c2.id, is_correct=False)

    ev = db_session.scalar(
        select(LearningEvidenceEvent).where(LearningEvidenceEvent.source_entity_id == res.attempt.id)
    )
    assert ev is not None
    assert ev.event_metadata["suppress_root_cause_rediagnosis"] is True
    assert ev.event_metadata["adaptive_repair_session_id"] == str(c2.id)

    diagnoses_after = db_session.scalar(select(func.count()).select_from(RootCauseDiagnosis))
    assert diagnoses_after == diagnoses_before


def test_failure_isolation_preserves_completed_repair_state(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    diagnosis, target, _ = _supported_diagnosis(
        db_session, practice_content, student_profile, average_score=0.75, question_count=6
    )
    service = AdaptiveRepairService(db_session)
    started = service.start(practice_students[0], diagnosis.id)

    # Mock LearningFeedbackService.resolve_feedback to throw an error
    with patch(
        "app.learning.feedback_service.LearningFeedbackService.resolve_feedback",
        side_effect=RuntimeError("Simulated feedback failure"),
    ):
        for _ in range(4):
            _submit_answer(service, practice_students[0], started.id, is_correct=True)

    # Repair state must still be COMPLETED and attempts preserved
    adaptive = db_session.get(AdaptiveRepairSession, started.id)
    assert adaptive.status == AdaptiveRepairStatus.COMPLETED
    assert adaptive.outcome == AdaptiveRepairOutcome.RESOLVED
    assert adaptive.attempted_count == 4
    assert db_session.scalar(select(func.count()).select_from(QuestionAttempt)) >= 4
    assert db_session.scalar(select(func.count()).select_from(LearningEvidenceEvent)) >= 4

    # Feedback can still be resolved later
    feedback_svc = LearningFeedbackService(db_session)
    dec = feedback_svc.resolve_feedback(started.id)
    assert dec.action in {
        LearningFeedbackAction.RETURN_TO_CURRENT_LEARNING,
        LearningFeedbackAction.NO_ACTIVE_LEARNING,
    }


def test_api_endpoints_next_action_retry_and_latest(
    db_client: TestClient,
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    practice_bearer,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    diagnosis, target, _ = _supported_diagnosis(
        db_session, practice_content, student_profile, average_score=0.25, question_count=18
    )
    headers = practice_bearer(practice_students[0])

    # Start repair via API
    resp = db_client.post(f"/students/me/diagnostics/{diagnosis.id}/repair", headers=headers)
    assert resp.status_code == 200
    session_id = resp.json()["id"]

    # Calling next-action before completion returns 409
    resp_early = db_client.get(f"/repair/adaptive/{session_id}/next-action", headers=headers)
    assert resp_early.status_code == 409
    assert resp_early.json()["error"]["code"] == "ADAPTIVE_REPAIR_NOT_COMPLETED"

    # Answer 8 times wrong to complete with NEEDS_MORE_PRACTICE
    for _ in range(8):
        s_data = db_client.get(f"/repair/adaptive/{session_id}", headers=headers).json()
        item_id = s_data["current_item"]["id"]
        db_client.post(
            f"/repair/adaptive/{session_id}/current/answer",
            json={"item_id": item_id, "student_answer": "B"},
            headers=headers,
        )

    # Next action now succeeds
    resp_action = db_client.get(f"/repair/adaptive/{session_id}/next-action", headers=headers)
    assert resp_action.status_code == 200
    action_data = resp_action.json()
    assert action_data["action"] == "RETRY_REPAIR"
    assert action_data["retry"]["allowed"] is True

    # Latest feedback endpoint works
    resp_latest = db_client.get(
        f"/students/me/learning/feedback/latest?subject_id={practice_content.subject.id}",
        headers=headers,
    )
    assert resp_latest.status_code == 200
    assert resp_latest.json()["id"] == action_data["id"]

    # Retry endpoint works
    resp_retry = db_client.post(f"/repair/adaptive/{session_id}/retry", headers=headers)
    assert resp_retry.status_code == 200
    retry_data = resp_retry.json()
    assert retry_data["repair_cycle_index"] == 2
    assert retry_data["previous_adaptive_repair_session_id"] == session_id
