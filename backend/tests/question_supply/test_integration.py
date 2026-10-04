"""Integration tests for Question Supply with Repair Start, Feedback loop, and Verification."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.knowledge_gap.models import (
    RootCauseDiagnosis,
    RootCauseVerification,
    RootCauseVerificationOutcome,
    RootCauseVerificationStatus,
    RootCauseVerificationTarget,
    RootCauseVerificationTargetType,
)
from app.knowledge_gap.verification import RootCauseVerificationService
from app.learning.feedback_models import (
    LearningFeedbackAction,
    LearningFeedbackDecision,
)
from app.learning.feedback_service import LearningFeedbackService
from app.practice.models import (
    PracticeSession,
    PracticeSessionStatus,
    PracticeSessionType,
)
from app.question_supply.models import (
    QuestionSupplyGap,
    QuestionSupplyGapObservation,
    QuestionSupplyHealth,
    QuestionSupplyObservationSourceKind,
    QuestionSupplyReasonCode,
    QuestionSupplySeverity,
    QuestionSupplyStatus,
    QuestionSupplyUseCase,
)
from app.questions.evaluation_eligibility import is_deterministically_auto_evaluable
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
from tests.repair.test_adaptive_repair import (
    _archive_existing_approved_questions,
    _supported_diagnosis,
)
from tests.question_supply.test_sufficiency import _archive_questions, _make_question


def test_repair_start_no_bank_persists_gap_and_returns_409(
    db_client: TestClient,
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
    practice_bearer,
) -> None:
    _archive_questions(db_session)
    student_user = db_session.get(User, student_profile.user_id)
    assert student_user is not None
    headers = practice_bearer(student_user)

    diagnosis, target, _ = _supported_diagnosis(
        db_session,
        practice_content,
        student_profile,
        question_count=0,  # 0 questions created
    )
    _archive_existing_approved_questions(db_session, practice_content)
    db_session.commit()

    # Attempt to start adaptive repair
    response = db_client.post(
        f"/students/me/diagnostics/{diagnosis.id}/repair",
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ADAPTIVE_REPAIR_NO_CANONICAL_QUESTION"

    # In fresh DB state, verify operational supply gap was persisted
    db_session.expire_all()
    gap = db_session.scalar(
        select(QuestionSupplyGap).where(
            QuestionSupplyGap.use_case == QuestionSupplyUseCase.ADAPTIVE_REPAIR,
            QuestionSupplyGap.concept_id == target.target_concept_id,
        )
    )
    assert gap is not None
    assert gap.status == QuestionSupplyStatus.OPEN
    assert gap.severity == QuestionSupplySeverity.CRITICAL
    assert gap.demand_count == 1

    # Verify observation
    obs = db_session.scalar(
        select(QuestionSupplyGapObservation).where(
            QuestionSupplyGapObservation.gap_id == gap.id
        )
    )
    assert obs is not None
    assert obs.source_kind == QuestionSupplyObservationSourceKind.ADAPTIVE_REPAIR_START
    assert obs.source_entity_id == diagnosis.id
    assert obs.student_id == student_profile.id

    # Verify NO orphan PracticeSession or AdaptiveRepairSession was created
    repair_sessions = list(
        db_session.scalars(
            select(PracticeSession).where(
                PracticeSession.student_id == student_profile.id,
                PracticeSession.session_type == PracticeSessionType.REPAIR,
            )
        )
    )
    assert len(repair_sessions) == 0

    adaptive_sessions = list(
        db_session.scalars(
            select(AdaptiveRepairSession).where(
                AdaptiveRepairSession.student_id == student_profile.id,
                AdaptiveRepairSession.diagnosis_id == diagnosis.id,
            )
        )
    )
    assert len(adaptive_sessions) == 0


def test_feedback_loop_creates_supply_gap(
    db_client: TestClient,
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
    practice_bearer,
) -> None:
    _archive_questions(db_session)
    student_user = db_session.get(User, student_profile.user_id)
    assert student_user is not None
    headers = practice_bearer(student_user)

    diagnosis, target, _ = _supported_diagnosis(
        db_session,
        practice_content,
        student_profile,
        question_count=0,
    )
    # Manually create a completed adaptive repair session with outcome BANK_EXHAUSTED
    now = datetime.now(timezone.utc)
    ps = PracticeSession(
        student_id=student_profile.id,
        subject_id=practice_content.subject.id,
        session_type=PracticeSessionType.REPAIR,
        status=PracticeSessionStatus.COMPLETED,
        completed_at=now,
    )
    db_session.add(ps)
    db_session.flush()

    adaptive = AdaptiveRepairSession(
        practice_session_id=ps.id,
        student_id=student_profile.id,
        subject_id=practice_content.subject.id,
        diagnosis_id=diagnosis.id,
        verification_id=diagnosis.verifications[0].id,
        verification_target_id=target.id,
        target_type=target.target_type,
        target_concept_id=target.target_concept_id,
        repair_cycle_index=1,
        phase=AdaptiveRepairPhase.FOUNDATION,
        initial_difficulty=0.35,
        current_difficulty=0.35,
        target_exit_difficulty=0.50,
        verification_average_score=target.average_score,
        status=AdaptiveRepairStatus.COMPLETED,
        outcome=AdaptiveRepairOutcome.BANK_EXHAUSTED,
        completed_at=now,
        max_questions=8,
    )
    db_session.add(adaptive)
    db_session.commit()

    # Call next-action endpoint
    resp = db_client.get(
        f"/repair/adaptive/{adaptive.id}/next-action",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "QUESTION_SUPPLY_GAP"

    # Verify QuestionSupplyGap exists and observation is linked
    gap = db_session.scalar(
        select(QuestionSupplyGap).where(
            QuestionSupplyGap.use_case == QuestionSupplyUseCase.ADAPTIVE_REPAIR,
            QuestionSupplyGap.concept_id == target.target_concept_id,
        )
    )
    assert gap is not None
    assert gap.status == QuestionSupplyStatus.OPEN
    assert gap.demand_count == 1

    decision = db_session.scalar(
        select(LearningFeedbackDecision).where(
            LearningFeedbackDecision.adaptive_repair_session_id == adaptive.id
        )
    )
    assert decision is not None

    obs = db_session.scalar(
        select(QuestionSupplyGapObservation).where(
            QuestionSupplyGapObservation.gap_id == gap.id
        )
    )
    assert obs is not None
    assert obs.source_kind == QuestionSupplyObservationSourceKind.LEARNING_FEEDBACK
    assert obs.source_entity_id == decision.id

    # Repeated GET /next-action should be idempotent
    resp2 = db_client.get(
        f"/repair/adaptive/{adaptive.id}/next-action",
        headers=headers,
    )
    assert resp2.status_code == 200
    db_session.expire_all()
    reloaded_gap = db_session.get(QuestionSupplyGap, gap.id)
    assert reloaded_gap.demand_count == 1


def test_verification_probes_recorded_as_gaps(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    svc = RootCauseVerificationService(db_session)

    # 1. Verification with 0 probes -> CRITICAL gap
    _archive_questions(db_session)
    diag0 = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        root_concept_id=practice_content.concept.id,
        candidate_concept_id=practice_content.concept.id,
    )
    read0 = svc.start_verification(student_id=student_profile.id, diagnosis_id=diag0.id)
    assert read0.status == RootCauseVerificationStatus.UNAVAILABLE

    gap0 = db_session.scalar(
        select(QuestionSupplyGap).where(
            QuestionSupplyGap.use_case == QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
            QuestionSupplyGap.concept_id == practice_content.concept.id,
        )
    )
    assert gap0 is not None
    assert gap0.severity == QuestionSupplySeverity.CRITICAL

    # 2. Verification with 1 probe -> INSUFFICIENT gap
    _archive_questions(db_session)
    _make_question(db_session, practice_content, index=1, difficulty=0.35)
    diag1 = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        root_concept_id=practice_content.concept.id,
        candidate_concept_id=practice_content.concept.id,
    )
    read1 = svc.start_verification(student_id=student_profile.id, diagnosis_id=diag1.id)
    assert read1.status == RootCauseVerificationStatus.ACTIVE
    assert read1.required_probe_count == 1

    gap1 = db_session.scalar(
        select(QuestionSupplyGap).where(
            QuestionSupplyGap.use_case == QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
            QuestionSupplyGap.concept_id == practice_content.concept.id,
        )
    )
    assert gap1 is not None
    assert gap1.approved_eligible_count == 1
    assert gap1.severity == QuestionSupplySeverity.HIGH

    # 3. Verification with 2 probes -> THIN gap (min=2, preferred=3)
    _archive_questions(db_session)
    _make_question(db_session, practice_content, index=1, difficulty=0.35)
    _make_question(db_session, practice_content, index=2, difficulty=0.35)
    diag2 = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        root_concept_id=practice_content.concept.id,
        candidate_concept_id=practice_content.concept.id,
    )
    read2 = svc.start_verification(student_id=student_profile.id, diagnosis_id=diag2.id)
    assert read2.status == RootCauseVerificationStatus.ACTIVE
    assert read2.required_probe_count == 2

    gap2 = db_session.scalar(
        select(QuestionSupplyGap).where(
            QuestionSupplyGap.use_case == QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
            QuestionSupplyGap.concept_id == practice_content.concept.id,
        )
    )
    assert gap2 is not None
    assert gap2.approved_eligible_count == 2
    assert gap2.severity == QuestionSupplySeverity.MEDIUM


def test_shared_auto_evaluation_eligibility_prevents_selection(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    _archive_questions(db_session)
    # Question with invalid MCQ (answer doesn't match options)
    bad_mcq = _make_question(
        db_session,
        practice_content,
        question_type=QuestionType.MULTIPLE_CHOICE,
        correct_answer="NON_EXISTENT_LABEL",
    )
    assert not is_deterministically_auto_evaluable(bad_mcq)

    # Verification should NOT pick bad MCQ
    diag = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        root_concept_id=practice_content.concept.id,
        candidate_concept_id=practice_content.concept.id,
    )
    verification_read = RootCauseVerificationService(db_session).start_verification(
        student_id=student_profile.id, diagnosis_id=diag.id
    )
    assert verification_read.status == RootCauseVerificationStatus.UNAVAILABLE

    # Adaptive repair should NOT pick bad MCQ
    repair_svc = AdaptiveRepairService(db_session)
    diag_supp, target_supp, _ = _supported_diagnosis(
        db_session,
        practice_content,
        student_profile,
        question_count=0,
    )
    student_user = db_session.get(User, student_profile.user_id)
    assert student_user is not None
    with pytest.raises(ApplicationError) as exc:
        repair_svc.start(student_user, diag_supp.id)
    assert exc.value.code == "ADAPTIVE_REPAIR_NO_CANONICAL_QUESTION"


def test_repair_start_invalid_auto_evaluable_bank_records_correct_gap_reason(
    db_client: TestClient,
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
    practice_bearer,
) -> None:
    _archive_questions(db_session)
    student_user = db_session.get(User, student_profile.user_id)
    assert student_user is not None
    headers = practice_bearer(student_user)

    diagnosis, target, _ = _supported_diagnosis(
        db_session,
        practice_content,
        student_profile,
        question_count=0,
    )
    _archive_existing_approved_questions(db_session, practice_content)

    # Populate bank with 4 APPROVED questions, but ALL are OPEN_RESPONSE (not auto-evaluable)
    for i in range(4):
        _make_question(
            db_session,
            practice_content,
            index=i + 1,
            question_type=QuestionType.OPEN_RESPONSE,
            difficulty=0.45,
        )
    db_session.commit()

    # Attempt to start adaptive repair -> fails with 409
    response = db_client.post(
        f"/students/me/diagnostics/{diagnosis.id}/repair",
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ADAPTIVE_REPAIR_NO_CANONICAL_QUESTION"

    # Verify persisted gap has reason_code == NO_AUTO_EVALUABLE_TARGET_QUESTIONS
    db_session.expire_all()
    gap = db_session.scalar(
        select(QuestionSupplyGap).where(
            QuestionSupplyGap.use_case == QuestionSupplyUseCase.ADAPTIVE_REPAIR,
            QuestionSupplyGap.concept_id == target.target_concept_id,
        )
    )
    assert gap is not None
    assert gap.status == QuestionSupplyStatus.OPEN
    assert gap.severity == QuestionSupplySeverity.CRITICAL
    assert gap.reason_code == QuestionSupplyReasonCode.NO_AUTO_EVALUABLE_TARGET_QUESTIONS
    assert gap.approved_eligible_count == 0

    obs = db_session.scalar(
        select(QuestionSupplyGapObservation).where(
            QuestionSupplyGapObservation.gap_id == gap.id
        )
    )
    assert obs is not None
    assert obs.reason_code == QuestionSupplyReasonCode.NO_AUTO_EVALUABLE_TARGET_QUESTIONS


def test_verification_invalid_auto_evaluable_bank_records_correct_gap_reason(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    _archive_questions(db_session)
    # Populate bank with 3 APPROVED questions, but invalid MCQ (options don't match correct_answer)
    for i in range(3):
        _make_question(
            db_session,
            practice_content,
            index=i + 1,
            question_type=QuestionType.MULTIPLE_CHOICE,
            correct_answer="NON_EXISTENT_LABEL",
            difficulty=0.35,
        )
    db_session.flush()

    diag = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        root_concept_id=practice_content.concept.id,
        candidate_concept_id=practice_content.concept.id,
    )
    svc = RootCauseVerificationService(db_session)
    read = svc.start_verification(student_id=student_profile.id, diagnosis_id=diag.id)
    assert read.status == RootCauseVerificationStatus.UNAVAILABLE

    gap = db_session.scalar(
        select(QuestionSupplyGap).where(
            QuestionSupplyGap.use_case == QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
            QuestionSupplyGap.concept_id == practice_content.concept.id,
        )
    )
    assert gap is not None
    assert gap.status == QuestionSupplyStatus.OPEN
    assert gap.reason_code == QuestionSupplyReasonCode.NO_AUTO_EVALUABLE_TARGET_QUESTIONS
    assert gap.approved_eligible_count == 0

    obs = db_session.scalar(
        select(QuestionSupplyGapObservation).where(
            QuestionSupplyGapObservation.gap_id == gap.id
        )
    )
    assert obs is not None
    assert obs.reason_code == QuestionSupplyReasonCode.NO_AUTO_EVALUABLE_TARGET_QUESTIONS

