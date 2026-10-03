from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.knowledge_gap.models import (
    RootCauseDiagnosis,
    RootCauseVerification,
    RootCauseVerificationOutcome,
    RootCauseVerificationStatus,
    RootCauseVerificationItem,
    RootCauseVerificationTarget,
    RootCauseVerificationTargetType,
)
from app.learning_evidence.models import LearningEvidenceEvent
from app.mastery.models import StudentConceptMastery
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
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.repair.adaptive_policy import AdaptiveRepairPolicy
from app.repair.adaptive_service import AdaptiveRepairService
from app.repair.models import (
    AdaptiveRepairDecision,
    AdaptiveRepairDecisionReason,
    AdaptiveRepairItem,
    AdaptiveRepairOutcome,
    AdaptiveRepairPhase,
    AdaptiveRepairStatus,
)
from app.repair.schemas import AdaptiveRepairAnswerSubmit
from app.students.models import StudentProfile
from app.users.models import User
from tests.knowledge_gap.test_verification import _create_diagnosis
from tests.practice.conftest import (
    PracticeContent,
    practice_bearer,
    practice_content,
    practice_students,
    practice_user_factory,
    student_profile,
)


def _repair_question(
    session: Session,
    content: PracticeContent,
    *,
    index: int,
    difficulty: float,
    status: QuestionStatus = QuestionStatus.APPROVED,
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE,
    concept_id: UUID | None = None,
) -> Question:
    question = Question(
        subject_id=content.subject.id,
        content=f"Adaptive repair question {index} {uuid4()}",
        question_type=question_type,
        difficulty=difficulty,
        correct_answer="A" if question_type != QuestionType.TRUE_FALSE else "TRUE",
        explanation=f"Explanation {index}",
        source_type="TEST",
        exam_weight=0.5,
        status=status,
        cognitive_level=CognitiveLevel.APPLY,
        created_by=content.mcq.created_by,
        options=(
            [
                QuestionOption(label="A", content="Correct", order_index=0),
                QuestionOption(label="B", content="Wrong", order_index=1),
            ]
            if question_type == QuestionType.MULTIPLE_CHOICE
            else []
        ),
        concept_links=[QuestionConcept(concept_id=concept_id or content.concept.id, weight=1.0)],
        problem_type_links=[
            QuestionProblemType(
                problem_type_id=content.problem_type.id,
                weight=1.0,
                is_primary=True,
            )
        ],
        learning_outcome_links=[
            QuestionLearningOutcome(
                learning_outcome_id=content.learning_outcome.id,
                weight=1.0,
            )
        ],
    )
    session.add(question)
    session.flush()
    return question


def _archive_existing_approved_questions(session: Session, content: PracticeContent) -> None:
    for question in (
        content.mcq,
        content.true_false,
        content.short_answer,
        content.open_response,
    ):
        question.status = QuestionStatus.ARCHIVED
    session.flush()

def _supported_diagnosis(
    session: Session,
    content: PracticeContent,
    student: StudentProfile,
    *,
    average_score: float = 0.75,
    question_count: int = 9,
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE,
) -> tuple[RootCauseDiagnosis, RootCauseVerificationTarget, list[Question]]:
    diagnosis = _create_diagnosis(
        session,
        content,
        student.id,
        root_concept_id=content.concept.id,
        candidate_concept_id=content.concept.id,
    )
    verification_practice = PracticeSession(
        student_id=student.id,
        subject_id=content.subject.id,
        session_type=PracticeSessionType.ROOT_CAUSE_VERIFICATION,
        status=PracticeSessionStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
    )
    session.add(verification_practice)
    session.flush()
    verification = RootCauseVerification(
        diagnosis_id=diagnosis.id,
        practice_session_id=verification_practice.id,
        status=RootCauseVerificationStatus.COMPLETED,
        required_probe_count=1,
        completed_probe_count=1,
        completed_at=datetime.now(timezone.utc),
    )
    session.add(verification)
    session.flush()
    target = RootCauseVerificationTarget(
        verification_id=verification.id,
        target_type=RootCauseVerificationTargetType.CONCEPT,
        target_concept_id=content.concept.id,
        priority_order=1,
        outcome=RootCauseVerificationOutcome.SUPPORTED,
        probe_count=1,
        correct_count=1 if average_score >= 0.5 else 0,
        average_score=average_score,
        completed_at=datetime.now(timezone.utc),
    )
    session.add(target)
    questions = [
        _repair_question(
            session,
            content,
            index=index,
            difficulty=min(0.8, 0.25 + index * 0.06),
            question_type=question_type,
        )
        for index in range(question_count)
    ]
    session.commit()
    return diagnosis, target, questions


def test_start_supported_target_is_idempotent_and_freezes_one_item(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    diagnosis, target, _ = _supported_diagnosis(db_session, practice_content, student_profile)
    service = AdaptiveRepairService(db_session)

    first = service.start(practice_students[0], diagnosis.id)
    again = service.start(practice_students[0], diagnosis.id)

    assert again.id == first.id
    assert first.verification_target_id == target.id
    assert first.target.concept_id == practice_content.concept.id
    assert first.current_item is not None
    assert first.current_item.question_id == again.current_item.question_id
    assert first.phase == AdaptiveRepairPhase.TARGET_PRACTICE
    assert first.current_difficulty == 0.4
    assert db_session.scalar(select(func.count()).select_from(AdaptiveRepairItem)) == 1
    practice = db_session.get(PracticeSession, first.practice_session_id)
    assert practice is not None and practice.session_type == PracticeSessionType.REPAIR


def test_start_rejects_unverified_and_unsupported_diagnoses(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    diagnosis = _create_diagnosis(db_session, practice_content, student_profile.id)
    with pytest.raises(ApplicationError) as unverified:
        AdaptiveRepairService(db_session).start(practice_students[0], diagnosis.id)
    assert unverified.value.code == "ADAPTIVE_REPAIR_VERIFY_ROOT_CAUSE"

    diagnosis2, target, _ = _supported_diagnosis(db_session, practice_content, student_profile)
    target.outcome = RootCauseVerificationOutcome.INCONCLUSIVE
    db_session.commit()
    with pytest.raises(ApplicationError) as unsupported:
        AdaptiveRepairService(db_session).start(practice_students[0], diagnosis2.id)
    assert unsupported.value.code == "ADAPTIVE_REPAIR_COLLECT_MORE_EVIDENCE"


def test_start_rejects_when_only_open_response_is_available(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    diagnosis, _, _ = _supported_diagnosis(
        db_session,
        practice_content,
        student_profile,
        question_count=1,
        question_type=QuestionType.OPEN_RESPONSE,
    )
    with pytest.raises(ApplicationError) as error:
        AdaptiveRepairService(db_session).start(practice_students[0], diagnosis.id)
    assert error.value.code == "ADAPTIVE_REPAIR_NO_CANONICAL_QUESTION"
    assert db_session.scalar(select(func.count()).select_from(AdaptiveRepairItem)) == 0


def test_wrong_answer_enters_guided_emits_evidence_and_suppresses_nested_diagnosis(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    diagnosis, _, _ = _supported_diagnosis(db_session, practice_content, student_profile, average_score=0.2)
    service = AdaptiveRepairService(db_session)
    started = service.start(practice_students[0], diagnosis.id)
    before_diagnoses = db_session.scalar(select(func.count()).select_from(RootCauseDiagnosis))

    result = service.answer_current(
        practice_students[0],
        started.id,
        AdaptiveRepairAnswerSubmit(item_id=started.current_item.id, student_answer="B"),
    )

    assert result.attempt.is_correct is False
    assert result.next_phase == AdaptiveRepairPhase.GUIDED
    assert result.difficulty_after < result.difficulty_before
    assert result.session.current_item is not None
    assert result.session.current_item.hints_allowed is True
    event = db_session.scalar(
        select(LearningEvidenceEvent).where(
            LearningEvidenceEvent.source_entity_id == result.attempt.id
        )
    )
    assert event is not None
    assert event.event_metadata["suppress_root_cause_rediagnosis"] is True
    assert event.event_metadata["adaptive_repair_session_id"] == str(started.id)
    assert db_session.scalar(select(func.count()).select_from(RootCauseDiagnosis)) == before_diagnoses
    mastery = db_session.get(StudentConceptMastery, (student_profile.id, practice_content.concept.id))
    assert mastery is not None and mastery.attempt_count == 1


def test_correct_with_hint_advances_less_and_duplicate_answer_is_rejected(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    diagnosis, _, _ = _supported_diagnosis(db_session, practice_content, student_profile)
    service = AdaptiveRepairService(db_session)
    started = service.start(practice_students[0], diagnosis.id)
    payload = AdaptiveRepairAnswerSubmit(
        item_id=started.current_item.id,
        student_answer="A",
        hint_count=1,
    )
    result = service.answer_current(practice_students[0], started.id, payload)
    assert result.difficulty_after == pytest.approx(result.difficulty_before + 0.05)
    assert result.reason_code == AdaptiveRepairDecisionReason.CORRECT_WITH_HINT_SMALL_ADVANCE

    with pytest.raises(ApplicationError) as duplicate:
        service.answer_current(practice_students[0], started.id, payload)
    assert duplicate.value.status_code == 409
    assert duplicate.value.code == "REPAIR_ITEM_ALREADY_ATTEMPTED"
    assert db_session.scalar(select(func.count()).select_from(LearningEvidenceEvent).where(LearningEvidenceEvent.source_entity_id == result.attempt.id)) == 1


def test_frozen_selection_does_not_change_until_answer(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    diagnosis, _, _ = _supported_diagnosis(db_session, practice_content, student_profile, question_count=2)
    service = AdaptiveRepairService(db_session)
    started = service.start(practice_students[0], diagnosis.id)
    frozen_question = started.current_item.question_id
    better = _repair_question(db_session, practice_content, index=99, difficulty=started.current_difficulty)
    db_session.commit()

    fetched = service.get(practice_students[0], started.id)
    assert fetched.current_item.question_id == frozen_question

    answered = service.answer_current(
        practice_students[0],
        started.id,
        AdaptiveRepairAnswerSubmit(item_id=started.current_item.id, student_answer="A"),
    )
    assert answered.session.current_item is not None
    assert answered.session.current_item.question_id == better.id


def test_final_recheck_pass_resolves_after_minimum_evidence(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    diagnosis, _, _ = _supported_diagnosis(db_session, practice_content, student_profile, average_score=0.75)
    service = AdaptiveRepairService(db_session)
    state = service.start(practice_students[0], diagnosis.id)

    for _ in range(3):
        result = service.answer_current(
            practice_students[0],
            state.id,
            AdaptiveRepairAnswerSubmit(item_id=state.current_item.id, student_answer="A"),
        )
        state = result.session
    assert state.phase == AdaptiveRepairPhase.FINAL_RECHECK
    assert state.current_item is not None and state.current_item.role.value == "FINAL_RECHECK"

    final = service.answer_current(
        practice_students[0],
        state.id,
        AdaptiveRepairAnswerSubmit(item_id=state.current_item.id, student_answer="A"),
    )
    assert final.reason_code == AdaptiveRepairDecisionReason.FINAL_RECHECK_PASSED
    assert final.session.status == AdaptiveRepairStatus.COMPLETED
    assert final.session.outcome == AdaptiveRepairOutcome.RESOLVED
    assert final.session.current_item is None
    practice = db_session.get(PracticeSession, final.session.practice_session_id)
    assert practice.status == PracticeSessionStatus.COMPLETED
    assert practice.completed_at is not None


def test_bank_exhaustion_completes_after_preserving_answer_evidence(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    diagnosis, _, _ = _supported_diagnosis(db_session, practice_content, student_profile, question_count=1)
    service = AdaptiveRepairService(db_session)
    state = service.start(practice_students[0], diagnosis.id)
    result = service.answer_current(
        practice_students[0],
        state.id,
        AdaptiveRepairAnswerSubmit(item_id=state.current_item.id, student_answer="A"),
    )
    assert result.reason_code == AdaptiveRepairDecisionReason.QUESTION_BANK_EXHAUSTED
    assert result.session.outcome == AdaptiveRepairOutcome.BANK_EXHAUSTED
    assert result.session.status == AdaptiveRepairStatus.COMPLETED
    assert db_session.get(QuestionAttempt, result.attempt.id) is not None
    assert db_session.scalar(select(func.count()).select_from(LearningEvidenceEvent).where(LearningEvidenceEvent.source_entity_id == result.attempt.id)) == 1


def test_owner_authorization_and_item_mismatch(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    diagnosis, _, _ = _supported_diagnosis(db_session, practice_content, student_profile)
    service = AdaptiveRepairService(db_session)
    state = service.start(practice_students[0], diagnosis.id)

    with pytest.raises(ApplicationError) as denied:
        service.get(practice_students[1], state.id)
    assert denied.value.status_code == 403

    with pytest.raises(ApplicationError) as mismatch:
        service.answer_current(
            practice_students[0],
            state.id,
            AdaptiveRepairAnswerSubmit(item_id=uuid4(), student_answer="A"),
        )
    assert mismatch.value.code == "REPAIR_ITEM_MISMATCH"


def test_policy_bounds_initial_difficulty_and_determinism() -> None:
    policy = AdaptiveRepairPolicy()
    assert policy.initial_difficulty(RootCauseVerificationTargetType.CONCEPT, 0.2) == 0.30
    assert policy.initial_difficulty(RootCauseVerificationTargetType.CONCEPT, None) == 0.35
    assert policy.initial_difficulty(RootCauseVerificationTargetType.PROBLEM_TYPE, 0.2) == 0.40
    assert policy.initial_difficulty(RootCauseVerificationTargetType.PROBLEM_TYPE, 0.8) == 0.50
    assert policy.adjusted_difficulty(0.8, is_correct=True, hint_count=0) == 0.8
    assert policy.adjusted_difficulty(0.2, is_correct=False, hint_count=2) == 0.2


def test_one_decision_per_answer_and_single_pending_item(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    diagnosis, _, _ = _supported_diagnosis(db_session, practice_content, student_profile)
    service = AdaptiveRepairService(db_session)
    state = service.start(practice_students[0], diagnosis.id)
    service.answer_current(
        practice_students[0], state.id,
        AdaptiveRepairAnswerSubmit(item_id=state.current_item.id, student_answer="A"),
    )
    assert db_session.scalar(select(func.count()).select_from(AdaptiveRepairDecision)) == 1
    assert db_session.scalar(select(func.count()).select_from(AdaptiveRepairItem).where(AdaptiveRepairItem.attempt_id.is_(None))) == 1




def test_repeated_wrong_enters_guided_and_correct_recovers(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    diagnosis, _, _ = _supported_diagnosis(db_session, practice_content, student_profile, average_score=0.75)
    service = AdaptiveRepairService(db_session)
    state = service.start(practice_students[0], diagnosis.id)

    first = service.answer_current(
        practice_students[0], state.id,
        AdaptiveRepairAnswerSubmit(item_id=state.current_item.id, student_answer="B"),
    )
    assert first.session.phase == AdaptiveRepairPhase.TARGET_PRACTICE
    second = service.answer_current(
        practice_students[0], state.id,
        AdaptiveRepairAnswerSubmit(item_id=first.session.current_item.id, student_answer="B"),
    )
    assert second.reason_code == AdaptiveRepairDecisionReason.REPEATED_WRONG_ENTER_GUIDED
    assert second.session.phase == AdaptiveRepairPhase.GUIDED
    recovered = service.answer_current(
        practice_students[0], state.id,
        AdaptiveRepairAnswerSubmit(item_id=second.session.current_item.id, student_answer="A"),
    )
    assert recovered.reason_code == AdaptiveRepairDecisionReason.RECOVERED_EXIT_GUIDED
    assert recovered.session.phase == AdaptiveRepairPhase.TARGET_PRACTICE


def test_failed_final_recheck_continues_when_budget_remains(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    diagnosis, _, _ = _supported_diagnosis(db_session, practice_content, student_profile, average_score=0.75)
    service = AdaptiveRepairService(db_session)
    state = service.start(practice_students[0], diagnosis.id)
    for _ in range(3):
        state = service.answer_current(
            practice_students[0], state.id,
            AdaptiveRepairAnswerSubmit(item_id=state.current_item.id, student_answer="A"),
        ).session
    assert state.phase == AdaptiveRepairPhase.FINAL_RECHECK

    failed = service.answer_current(
        practice_students[0], state.id,
        AdaptiveRepairAnswerSubmit(item_id=state.current_item.id, student_answer="B"),
    )
    assert failed.reason_code == AdaptiveRepairDecisionReason.FINAL_RECHECK_FAILED
    assert failed.session.status == AdaptiveRepairStatus.ACTIVE
    assert failed.session.outcome == AdaptiveRepairOutcome.PENDING
    assert failed.session.phase == AdaptiveRepairPhase.TARGET_PRACTICE
    assert failed.session.current_item is not None


def test_max_question_guard_completes_needs_more_practice(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    diagnosis, _, _ = _supported_diagnosis(db_session, practice_content, student_profile)
    service = AdaptiveRepairService(db_session, policy=AdaptiveRepairPolicy(max_questions=1))
    state = service.start(practice_students[0], diagnosis.id)
    result = service.answer_current(
        practice_students[0], state.id,
        AdaptiveRepairAnswerSubmit(item_id=state.current_item.id, student_answer="B"),
    )
    assert result.reason_code == AdaptiveRepairDecisionReason.MAX_QUESTIONS_REACHED
    assert result.session.status == AdaptiveRepairStatus.COMPLETED
    assert result.session.outcome == AdaptiveRepairOutcome.NEEDS_MORE_PRACTICE
    assert result.session.progress.attempted_count == 1



def test_adaptive_repair_api_start_get_answer_and_owner_guard(
    db_client: TestClient,
    db_session: Session,
    practice_bearer,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    diagnosis, _, _ = _supported_diagnosis(db_session, practice_content, student_profile)
    owner_headers = practice_bearer(practice_students[0])
    outsider_headers = practice_bearer(practice_students[1])

    started = db_client.post(
        f"/students/me/diagnostics/{diagnosis.id}/repair",
        headers=owner_headers,
        json={},
    )
    assert started.status_code == 200, started.text
    payload = started.json()
    assert payload["diagnosis_id"] == str(diagnosis.id)
    assert payload["current_item"] is not None

    fetched = db_client.get(
        f"/repair/adaptive/{payload['id']}", headers=owner_headers
    )
    assert fetched.status_code == 200
    assert fetched.json()["current_item"]["id"] == payload["current_item"]["id"]

    denied = db_client.get(
        f"/repair/adaptive/{payload['id']}", headers=outsider_headers
    )
    assert denied.status_code == 403

    answered = db_client.post(
        f"/repair/adaptive/{payload['id']}/current/answer",
        headers=owner_headers,
        json={
            "item_id": payload["current_item"]["id"],
            "student_answer": "A",
            "hint_count": 0,
        },
    )
    assert answered.status_code == 200, answered.text
    answer_payload = answered.json()
    assert answer_payload["attempt"]["is_correct"] is True
    assert answer_payload["difficulty_after"] > answer_payload["difficulty_before"]


def test_selection_excludes_recent_probe_draft_open_and_wrong_target(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _archive_existing_approved_questions(db_session, practice_content)
    diagnosis, target, questions = _supported_diagnosis(
        db_session, practice_content, student_profile, question_count=3
    )
    recent, probe, fresh = questions
    verification = db_session.get(RootCauseVerification, target.verification_id)
    verification.required_probe_count = 2
    verification.completed_probe_count = 2
    db_session.add(
        RootCauseVerificationItem(
            verification_target_id=target.id,
            question_id=probe.id,
            order_index=1,
            desired_difficulty=probe.difficulty,
            selection_score=1.0,
        )
    )
    recent_session = PracticeSession(
        student_id=student_profile.id,
        subject_id=practice_content.subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(recent_session)
    db_session.flush()
    db_session.add(
        QuestionAttempt(
            practice_session_id=recent_session.id,
            student_id=student_profile.id,
            question_id=recent.id,
            student_answer="A",
            is_correct=True,
            score=1.0,
            attempt_number=1,
            evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        )
    )
    _repair_question(
        db_session,
        practice_content,
        index=101,
        difficulty=0.4,
        status=QuestionStatus.DRAFT,
    )
    _repair_question(
        db_session,
        practice_content,
        index=102,
        difficulty=0.4,
        question_type=QuestionType.OPEN_RESPONSE,
    )
    invalid_key = _repair_question(
        db_session,
        practice_content,
        index=104,
        difficulty=0.4,
    )
    invalid_key.correct_answer = None
    other_concept = Concept(
        subject_id=practice_content.subject.id,
        code=f"OTHER_{uuid4().hex.upper()}",
        name="Other target",
    )
    db_session.add(other_concept)
    db_session.flush()
    _repair_question(
        db_session,
        practice_content,
        index=103,
        difficulty=0.4,
        concept_id=other_concept.id,
    )
    db_session.commit()

    state = AdaptiveRepairService(db_session).start(practice_students[0], diagnosis.id)
    assert state.current_item is not None
    assert state.current_item.question_id == fresh.id
    assert state.current_item.question_id not in {recent.id, probe.id}
