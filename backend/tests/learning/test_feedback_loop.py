from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
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


def test_lazy_feedback_persists_across_new_db_session(
    db_client: TestClient,
    db_engine: Engine,
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    practice_bearer,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    diagnosis, target, _ = _supported_diagnosis(
        db_session, practice_content, student_profile, average_score=0.75, question_count=6
    )
    service = AdaptiveRepairService(db_session)
    started = service.start(practice_students[0], diagnosis.id)

    # Mock auto-feedback during completion to fail so feedback is not created automatically
    with patch(
        "app.learning.feedback_service.LearningFeedbackService.resolve_feedback",
        side_effect=RuntimeError("Simulated auto-feedback failure"),
    ):
        for _ in range(4):
            _submit_answer(service, practice_students[0], started.id, is_correct=True)

    db_session.commit()

    # Confirm repair is completed but feedback decision does not exist yet
    assert db_session.scalar(
        select(LearningFeedbackDecision).where(
            LearningFeedbackDecision.adaptive_repair_session_id == started.id
        )
    ) is None

    # GET returns 409 when decision is not resolved yet
    headers = practice_bearer(practice_students[0])
    resp_unresolved = db_client.get(f"/repair/adaptive/{started.id}/next-action", headers=headers)
    assert resp_unresolved.status_code == 409
    assert resp_unresolved.json()["error"]["code"] == "LEARNING_FEEDBACK_NOT_RESOLVED"

    # Call POST next-action to resolve and commit
    resp = db_client.post(f"/repair/adaptive/{started.id}/next-action", headers=headers)
    assert resp.status_code == 200
    resp_data = resp.json()
    assert resp_data["id"] is not None

    # Subsequent GET returns existing resolved decision
    resp_get = db_client.get(f"/repair/adaptive/{started.id}/next-action", headers=headers)
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == resp_data["id"]

    # Verify durability across a completely fresh DB session
    with Session(db_engine) as fresh_session:
        persisted = fresh_session.scalar(
            select(LearningFeedbackDecision).where(
                LearningFeedbackDecision.adaptive_repair_session_id == started.id
            )
        )
        assert persisted is not None
        assert str(persisted.id) == resp_data["id"]
        assert persisted.action in {
            LearningFeedbackAction.RETURN_TO_CURRENT_LEARNING,
            LearningFeedbackAction.NO_ACTIVE_LEARNING,
        }


def test_lazy_resolved_feedback_persists_review_schedule(
    db_client: TestClient,
    db_engine: Engine,
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    practice_bearer,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    diagnosis, target, _ = _supported_diagnosis(
        db_session, practice_content, student_profile, average_score=0.75, question_count=6
    )
    service = AdaptiveRepairService(db_session)
    started = service.start(practice_students[0], diagnosis.id)

    # Mock auto-feedback so neither decision nor review schedule is created upon answer completion
    with patch(
        "app.learning.feedback_service.LearningFeedbackService.resolve_feedback",
        side_effect=RuntimeError("Simulated auto-feedback failure"),
    ):
        for _ in range(4):
            _submit_answer(service, practice_students[0], started.id, is_correct=True)

    db_session.commit()

    # Confirm no review schedule exists yet
    schedules_before = list(
        db_session.scalars(
            select(ReviewSchedule).where(ReviewSchedule.student_id == student_profile.id)
        )
    )
    assert len(schedules_before) == 0

    # GET returns 409 when unresolved
    headers = practice_bearer(practice_students[0])
    resp_unresolved = db_client.get(f"/repair/adaptive/{started.id}/next-action", headers=headers)
    assert resp_unresolved.status_code == 409
    assert resp_unresolved.json()["error"]["code"] == "LEARNING_FEEDBACK_NOT_RESOLVED"

    # Call POST to resolve
    resp = db_client.post(f"/repair/adaptive/{started.id}/next-action", headers=headers)
    assert resp.status_code == 200
    resp_data = resp.json()
    assert resp_data["review"] is not None
    schedule_id_str = resp_data["review"]["schedule_id"]
    assert schedule_id_str is not None

    # Open fresh DB session: review schedule and feedback decision must BOTH be durable
    with Session(db_engine) as fresh_session:
        sched = fresh_session.get(ReviewSchedule, UUID(schedule_id_str))
        assert sched is not None
        assert sched.student_id == student_profile.id

        persisted_dec = fresh_session.scalar(
            select(LearningFeedbackDecision).where(
                LearningFeedbackDecision.adaptive_repair_session_id == started.id
            )
        )
        assert persisted_dec is not None
        assert str(persisted_dec.review_schedule_id) == schedule_id_str


def test_feedback_next_learning_target_is_historical_snapshot(
    db_session: Session,
    db_client: TestClient,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    practice_bearer,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)

    # Create distinct PT_A and PT_B under separate concepts
    concept_a = Concept(
        subject_id=practice_content.subject.id,
        code=f"CONCEPT_A_{uuid4().hex[:6].upper()}",
        name="Concept A",
    )
    concept_b = Concept(
        subject_id=practice_content.subject.id,
        code=f"CONCEPT_B_{uuid4().hex[:6].upper()}",
        name="Concept B",
    )
    db_session.add_all([concept_a, concept_b])
    db_session.flush()

    pt_a = ProblemType(
        topic_id=practice_content.problem_type.topic_id,
        code=f"PT_A_{uuid4().hex[:6].upper()}",
        name="Problem Type A",
        order_index=97,
        is_active=True,
    )
    pt_b = ProblemType(
        topic_id=practice_content.problem_type.topic_id,
        code=f"PT_B_{uuid4().hex[:6].upper()}",
        name="Problem Type B",
        order_index=98,
        is_active=True,
    )
    db_session.add_all([pt_a, pt_b])
    db_session.flush()

    # Create questions for PT_A and PT_B
    q_a = Question(
        subject_id=practice_content.subject.id,
        content=f"Snapshot Question A {uuid4()}",
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
        problem_type_links=[QuestionProblemType(problem_type_id=pt_a.id, weight=1.0, is_primary=True)],
        concept_links=[QuestionConcept(concept_id=concept_a.id, weight=1.0)],
        learning_outcome_links=[QuestionLearningOutcome(learning_outcome_id=practice_content.learning_outcome.id, weight=1.0)],
    )
    q_b = Question(
        subject_id=practice_content.subject.id,
        content=f"Snapshot Question B {uuid4()}",
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
        problem_type_links=[QuestionProblemType(problem_type_id=pt_b.id, weight=1.0, is_primary=True)],
        concept_links=[QuestionConcept(concept_id=concept_b.id, weight=1.0)],
        learning_outcome_links=[QuestionLearningOutcome(learning_outcome_id=practice_content.learning_outcome.id, weight=1.0)],
    )
    db_session.add_all([q_a, q_b])
    db_session.flush()

    # Create teaching plan pointing to PT_A
    classroom = Classroom(
        name="Class A",
        academic_year="2025-2026",
        grade_level=12,
        created_by=practice_content.mcq.created_by,
    )
    db_session.add(classroom)
    db_session.flush()
    db_session.add(
        StudentEnrollment(
            classroom_id=classroom.id,
            student_id=student_profile.id,
            status=EnrollmentStatus.ACTIVE,
        )
    )
    db_session.flush()

    item_a = TeachingPlanItem(problem_type_id=pt_a.id, priority=10, order_index=0)
    plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=practice_content.subject.id,
        status=TeachingPlanStatus.ACTIVE,
        start_date=date.today(),
        created_by=practice_content.mcq.created_by,
        items=[item_a],
    )
    db_session.add(plan)
    db_session.commit()

    # Run repair session to completion
    diagnosis, target, _ = _supported_diagnosis(
        db_session, practice_content, student_profile, average_score=0.75, question_count=6
    )
    service = AdaptiveRepairService(db_session)
    started = service.start(practice_students[0], diagnosis.id)
    for _ in range(4):
        _submit_answer(service, practice_students[0], started.id, is_correct=True)

    # Feedback resolved: should have snapshot pointing to PT_A and q_a
    feedback_svc = LearningFeedbackService(db_session)
    dec = feedback_svc.resolve_feedback(started.id)
    assert dec.action == LearningFeedbackAction.RETURN_TO_CURRENT_LEARNING
    assert dec.next_learning is not None
    assert dec.next_learning.problem_type_id == pt_a.id
    assert dec.next_learning.recommended_question_id == q_a.id

    # Now change TeachingPlan to point to PT_B!
    item_a.problem_type_id = pt_b.id
    db_session.commit()

    # Re-read feedback decision via service and via API
    dec_after = feedback_svc.resolve_feedback(started.id)
    assert dec_after.next_learning is not None
    # Must STILL point to snapshot PT_A and q_a, NOT PT_B!
    assert dec_after.next_learning.problem_type_id == pt_a.id
    assert dec_after.next_learning.recommended_question_id == q_a.id

    headers = practice_bearer(practice_students[0])
    resp = db_client.get(f"/repair/adaptive/{started.id}/next-action", headers=headers)
    assert resp.status_code == 200
    api_next = resp.json()["next_learning"]
    assert api_next["problem_type_id"] == str(pt_a.id)
    assert api_next["recommended_question_id"] == str(q_a.id)


def test_feedback_legacy_row_without_next_target_does_not_recompute(
    db_session: Session,
    db_client: TestClient,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
    practice_bearer,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    diagnosis, target, _ = _supported_diagnosis(
        db_session, practice_content, student_profile, average_score=0.75, question_count=6
    )
    service = AdaptiveRepairService(db_session)
    started = service.start(practice_students[0], diagnosis.id)

    # Complete without automatic feedback
    with patch(
        "app.learning.feedback_service.LearningFeedbackService.resolve_feedback",
        side_effect=RuntimeError("suppressed"),
    ):
        for _ in range(4):
            _submit_answer(service, practice_students[0], started.id, is_correct=True)

    # Manually insert a legacy feedback decision row with NULL snapshot columns
    legacy_decision = LearningFeedbackDecision(
        student_id=student_profile.id,
        subject_id=practice_content.subject.id,
        adaptive_repair_session_id=started.id,
        action=LearningFeedbackAction.RETURN_TO_CURRENT_LEARNING,
        reason_code=LearningFeedbackReasonCode.CURRENT_LESSON_AVAILABLE,
        target_type=target.target_type,
        target_concept_id=target.target_concept_id,
        target_problem_type_id=target.target_problem_type_id,
        next_target_type=None,
        next_concept_id=None,
        next_problem_type_id=None,
        next_reason_code=None,
        recommended_question_id=None,
        review_schedule_id=None,
        repair_cycle_index=1,
        retry_allowed=False,
    )
    db_session.add(legacy_decision)
    db_session.commit()

    # Reading the decision must gracefully return next_learning=None without recomputing or crashing
    with patch(
        "app.recommendations.priority_service.LearningPriorityService.get_priorities",
        side_effect=AssertionError("get_priorities should NOT be called for existing decision!"),
    ):
        feedback_svc = LearningFeedbackService(db_session)
        read = feedback_svc.resolve_feedback(started.id)
        assert read.action == LearningFeedbackAction.RETURN_TO_CURRENT_LEARNING
        assert read.next_learning is None

        headers = practice_bearer(practice_students[0])
        resp = db_client.get(f"/repair/adaptive/{started.id}/next-action", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["next_learning"] is None


def test_initial_start_returns_cycle_one_after_retry_exists(
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
    assert c1.repair_cycle_index == 1

    # Complete cycle 1 with NEEDS_MORE_PRACTICE
    for _ in range(8):
        _submit_answer(service, practice_students[0], c1.id, is_correct=False)

    # Retry -> creates cycle 2
    c2 = service.retry(practice_students[0], c1.id)
    assert c2.repair_cycle_index == 2

    # Now call start() again on original diagnosis -> MUST return cycle 1, never cycle 2!
    re_started = service.start(practice_students[0], diagnosis.id)
    assert re_started.id == c1.id
    assert re_started.repair_cycle_index == 1


def test_concurrent_retry_returns_single_cycle_two(
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

    # Complete cycle 1 with NEEDS_MORE_PRACTICE
    for _ in range(8):
        _submit_answer(service, practice_students[0], c1.id, is_correct=False)

    # Call retry twice sequentially (idempotent retry)
    r1 = service.retry(practice_students[0], c1.id)
    r2 = service.retry(practice_students[0], c1.id)

    assert r1.id == r2.id
    assert r1.repair_cycle_index == 2
    assert r2.repair_cycle_index == 2

    # Verify only 1 cycle 2 session exists in database
    count_c2 = db_session.scalar(
        select(func.count())
        .select_from(AdaptiveRepairSession)
        .where(
            AdaptiveRepairSession.verification_target_id == target.id,
            AdaptiveRepairSession.repair_cycle_index == 2,
        )
    )
    assert count_c2 == 1


def test_retry_race_does_not_leave_orphan_practice_session(
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

    # Worker 1 succeeds and creates cycle 2
    winner_retry = service.retry(practice_students[0], c1.id)
    assert winner_retry.repair_cycle_index == 2

    ps_count_before = db_session.scalar(
        select(func.count())
        .select_from(PracticeSession)
        .where(PracticeSession.student_id == student_profile.id)
    )

    # Simulate race loser: existing_retry check returns None on first query to enter creation block,
    # then during flush inside savepoint, SQLite raises IntegrityError on uq_adaptive_repair_target_cycle.
    orig_scalar = db_session.scalar
    call_count = 0

    def scalar_intercept(stmt, *args, **kwargs):
        nonlocal call_count
        query_str = str(stmt)
        if "repair_cycle_index = :repair_cycle_index_1" in query_str and call_count == 0:
            call_count += 1
            return None  # Simulate first check missing existing cycle 2
        return orig_scalar(stmt, *args, **kwargs)

    with patch.object(db_session, "scalar", side_effect=scalar_intercept):
        loser_result = service.retry(practice_students[0], c1.id)

    # Loser must have safely recovered Winner's session
    assert loser_result.id == winner_retry.id
    assert loser_result.repair_cycle_index == 2

    # PracticeSession count must NOT have increased (no orphan PracticeSession created)
    ps_count_after = db_session.scalar(
        select(func.count())
        .select_from(PracticeSession)
        .where(PracticeSession.student_id == student_profile.id)
    )
    assert ps_count_after == ps_count_before

    # Exactly 1 cycle 2 session exists
    cycle2_count = db_session.scalar(
        select(func.count())
        .select_from(AdaptiveRepairSession)
        .where(
            AdaptiveRepairSession.verification_target_id == target.id,
            AdaptiveRepairSession.repair_cycle_index == 2,
        )
    )
    assert cycle2_count == 1

