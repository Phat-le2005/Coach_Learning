"""Tests for QuestionAcquisitionPlanner and acquisition planning lifecycle."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.practice.models import EvaluationStatus, PracticeSession, PracticeSessionStatus, PracticeSessionType, QuestionAttempt
from app.question_acquisition.models import (
    QuestionAcquisitionExistingCandidate,
    QuestionAcquisitionRequest,
    QuestionAcquisitionRequestStatus,
    QuestionAcquisitionStrategy,
)
from app.question_acquisition.service import QuestionAcquisitionService
from app.question_supply.models import (
    QuestionSupplyGap,
    QuestionSupplyHealth,
    QuestionSupplyObservationSourceKind,
    QuestionSupplyReasonCode,
    QuestionSupplyStatus,
    QuestionSupplyTargetType,
    QuestionSupplyUseCase,
)
from app.question_supply.service import (
    QuestionSupplyGapService,
    QuestionSupplyRequirement,
)
from app.questions.models import (
    Question,
    QuestionGroup,
    QuestionGroupType,
    QuestionGroupScoringPolicy,
    QuestionStatus,
    QuestionType,
)
from app.students.models import StudentProfile
from tests.practice.conftest import (
    PracticeContent,
    practice_content,
    practice_students,
    practice_user_factory,
    student_profile,
)
from tests.question_supply.test_sufficiency import _archive_questions, _make_question


def test_planner_strategy_selection(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    gap_svc = QuestionSupplyGapService(db_session)
    acq_svc = QuestionAcquisitionService(db_session)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        desired_difficulty=0.50,
        preferred_count=4,
    )
    # Preferred = 4, approved = 0 -> deficit = 4

    # 1. Zero candidates -> EXTERNAL_SOURCE_REQUIRED
    _, gap = gap_svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ADAPTIVE_REPAIR_START,
        source_entity_id=uuid4(),
    )
    assert gap is not None

    req1 = acq_svc.plan_or_get_active_request(gap.id, commit=False)
    assert req1.strategy == QuestionAcquisitionStrategy.EXTERNAL_SOURCE_REQUIRED
    assert req1.required_new_candidate_count == 4
    assert req1.existing_candidate_count == 0
    assert req1.external_candidate_target_count == 4
    assert req1.status == QuestionAcquisitionRequestStatus.AWAITING_SOURCE

    # Cancel req1 to test second strategy on fresh attempt
    acq_svc.cancel_request(req1.id, commit=False)

    # 2. Add 2 in-band candidates -> MIXED
    _make_question(db_session, practice_content, index=1, status=QuestionStatus.REVIEW, difficulty=0.50)
    _make_question(db_session, practice_content, index=2, status=QuestionStatus.REVIEW, difficulty=0.50)
    db_session.flush()

    req2 = acq_svc.plan_or_get_active_request(gap.id, commit=False)
    assert req2.strategy == QuestionAcquisitionStrategy.MIXED
    assert req2.attempt_index == 2
    assert req2.required_new_candidate_count == 4
    assert req2.existing_candidate_count == 2
    assert req2.external_candidate_target_count == 2  # 4 - 2 = 2
    assert req2.status == QuestionAcquisitionRequestStatus.AWAITING_SOURCE

    acq_svc.cancel_request(req2.id, commit=False)

    # 3. Add 2 more in-band candidates (total 4 in-band, meets required 4) -> REVIEW_EXISTING_PIPELINE
    _make_question(db_session, practice_content, index=3, status=QuestionStatus.REVIEW, difficulty=0.50)
    _make_question(db_session, practice_content, index=4, status=QuestionStatus.REVIEW, difficulty=0.50)
    db_session.flush()

    req3 = acq_svc.plan_or_get_active_request(gap.id, commit=False)
    assert req3.strategy == QuestionAcquisitionStrategy.REVIEW_EXISTING_PIPELINE
    assert req3.attempt_index == 3
    assert req3.required_new_candidate_count == 4
    assert req3.existing_candidate_count == 4
    assert req3.external_candidate_target_count == 0
    assert req3.status == QuestionAcquisitionRequestStatus.READY_FOR_REVIEW


def test_planner_candidate_ranking_order(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    gap_svc = QuestionSupplyGapService(db_session)
    acq_svc = QuestionAcquisitionService(db_session)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        desired_difficulty=0.50,
    )
    _, gap = gap_svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ROOT_CAUSE_VERIFICATION,
        source_entity_id=uuid4(),
    )
    assert gap is not None

    # Candidate 1: DRAFT, 0.50 (in band, runtime eligible, DRAFT)
    q_draft = _make_question(
        db_session,
        practice_content,
        index=1,
        status=QuestionStatus.DRAFT,
        difficulty=0.50,
        question_type=QuestionType.MULTIPLE_CHOICE,
        correct_answer="A",
    )
    # Candidate 2: REVIEW, 0.50 (in band, runtime eligible, REVIEW) -> SHOULD BE RANK 1!
    q_review = _make_question(
        db_session,
        practice_content,
        index=2,
        status=QuestionStatus.REVIEW,
        difficulty=0.50,
        question_type=QuestionType.MULTIPLE_CHOICE,
        correct_answer="A",
    )
    # Candidate 3: REVIEW, 0.90 (out of band, runtime eligible, REVIEW)
    q_out_of_band = _make_question(
        db_session,
        practice_content,
        index=3,
        status=QuestionStatus.REVIEW,
        difficulty=0.90,
        question_type=QuestionType.MULTIPLE_CHOICE,
        correct_answer="A",
    )
    # Candidate 4: REVIEW, 0.50, OPEN_RESPONSE (in band, not runtime eligible for root cause, REVIEW)
    q_non_runtime = _make_question(
        db_session,
        practice_content,
        index=4,
        status=QuestionStatus.REVIEW,
        difficulty=0.50,
        question_type=QuestionType.OPEN_RESPONSE,
        correct_answer=None,
    )
    db_session.flush()

    acq_req = acq_svc.plan_or_get_active_request(gap.id, commit=False)
    candidates = list(
        db_session.scalars(
            select(QuestionAcquisitionExistingCandidate)
            .where(QuestionAcquisitionExistingCandidate.request_id == acq_req.id)
            .order_by(QuestionAcquisitionExistingCandidate.selection_rank)
        )
    )
    assert len(candidates) == 4

    # Rank 1: REVIEW in-band runtime-eligible
    assert candidates[0].question_id == q_review.id
    assert candidates[0].selection_rank == 1
    assert candidates[0].difficulty_in_band is True
    assert candidates[0].runtime_eligible is True

    # Rank 2: DRAFT in-band runtime-eligible
    assert candidates[1].question_id == q_draft.id
    assert candidates[1].selection_rank == 2
    assert candidates[1].difficulty_in_band is True
    assert candidates[1].runtime_eligible is True

    # Rank 3: REVIEW in-band NOT runtime-eligible
    assert candidates[2].question_id == q_non_runtime.id
    assert candidates[2].selection_rank == 3
    assert candidates[2].difficulty_in_band is True
    assert candidates[2].runtime_eligible is False

    # Rank 4: REVIEW OUT-OF-BAND
    assert candidates[3].question_id == q_out_of_band.id
    assert candidates[3].selection_rank == 4
    assert candidates[3].difficulty_in_band is False


def test_pipeline_candidates_linked_and_frozen(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    gap_svc = QuestionSupplyGapService(db_session)
    acq_svc = QuestionAcquisitionService(db_session)

    # Pre-create 2 REVIEW questions
    q1 = _make_question(db_session, practice_content, index=1, status=QuestionStatus.REVIEW, difficulty=0.50)
    q2 = _make_question(db_session, practice_content, index=2, status=QuestionStatus.REVIEW, difficulty=0.50)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )
    _, gap = gap_svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ROOT_CAUSE_VERIFICATION,
        source_entity_id=uuid4(),
    )
    assert gap is not None

    acq_req = acq_svc.plan_or_get_active_request(gap.id, commit=False)
    assert acq_req.existing_candidate_count == 2

    # Later: 3 new questions are added to the bank
    for i in range(3, 6):
        _make_question(db_session, practice_content, index=i, status=QuestionStatus.REVIEW, difficulty=0.50)
    db_session.flush()

    # Re-fetch the acquisition request: snapshot and links MUST remain frozen!
    loaded = acq_svc.get_request(acq_req.id)
    assert loaded is not None
    assert loaded.existing_candidate_count == 2
    assert len(loaded.existing_candidates) == 2
    linked_ids = {c.question_id for c in loaded.existing_candidates}
    assert linked_ids == {q1.id, q2.id}


def test_planner_wrong_target_and_missing_taxonomy_excluded(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    gap_svc = QuestionSupplyGapService(db_session)
    acq_svc = QuestionAcquisitionService(db_session)

    other_concept = Concept(
        subject_id=practice_content.subject.id,
        code="OTHER_CONCEPT_EXCL",
        name="Other Concept",
    )
    db_session.add(other_concept)
    db_session.flush()

    # 1. Wrong concept
    _make_question(db_session, practice_content, status=QuestionStatus.REVIEW, concept_id=other_concept.id)
    # 2. Missing LO
    _make_question(db_session, practice_content, status=QuestionStatus.REVIEW, has_lo=False)
    # 3. Inside group (not standalone)
    grp = QuestionGroup(
        subject_id=practice_content.subject.id,
        content="Group stem",
        difficulty=0.5,
        source_type="TEST",
        exam_weight=0.5,
        created_by=practice_content.mcq.created_by,
        group_type=QuestionGroupType.TRUE_FALSE_FOUR,
        scoring_policy=QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
    )
    db_session.add(grp)
    db_session.flush()
    _make_question(db_session, practice_content, status=QuestionStatus.REVIEW, group_id=grp.id)
    db_session.flush()

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )
    _, gap = gap_svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ROOT_CAUSE_VERIFICATION,
        source_entity_id=uuid4(),
    )
    assert gap is not None

    acq_req = acq_svc.plan_or_get_active_request(gap.id, commit=False)
    assert acq_req.existing_candidate_count == 0
    assert len(acq_req.existing_candidates) == 0


def test_approved_questions_not_linked_as_pipeline_candidates(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    gap_svc = QuestionSupplyGapService(db_session)
    acq_svc = QuestionAcquisitionService(db_session)

    # 2 APPROVED questions, 1 REVIEW question
    q_app1 = _make_question(db_session, practice_content, index=1, status=QuestionStatus.APPROVED, difficulty=0.50)
    q_app2 = _make_question(db_session, practice_content, index=2, status=QuestionStatus.APPROVED, difficulty=0.50)
    q_rev = _make_question(db_session, practice_content, index=3, status=QuestionStatus.REVIEW, difficulty=0.50)
    db_session.flush()

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        desired_difficulty=0.50,
        preferred_count=4,
    )
    _, gap = gap_svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ADAPTIVE_REPAIR_START,
        source_entity_id=uuid4(),
    )
    assert gap is not None

    acq_req = acq_svc.plan_or_get_active_request(gap.id, commit=False)
    assert acq_req.approved_eligible_count_snapshot == 2
    assert acq_req.approved_in_band_count_snapshot == 2
    assert acq_req.existing_candidate_count == 1
    linked_ids = {c.question_id for c in acq_req.existing_candidates}
    assert linked_ids == {q_rev.id}
    assert q_app1.id not in linked_ids
    assert q_app2.id not in linked_ids


def test_student_exposure_exhausted_uses_fresh_deficit(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    _archive_questions(db_session)
    gap_svc = QuestionSupplyGapService(db_session)
    acq_svc = QuestionAcquisitionService(db_session)

    # 4 APPROVED questions in bank (min=4, preferred=6)
    created = [
        _make_question(db_session, practice_content, index=i, difficulty=0.50)
        for i in range(4)
    ]
    # Student attempted all 4
    ps = PracticeSession(
        student_id=student_profile.id,
        subject_id=practice_content.subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(ps)
    db_session.flush()
    for idx, q in enumerate(created, start=1):
        attempt = QuestionAttempt(
            practice_session_id=ps.id,
            student_id=student_profile.id,
            question_id=q.id,
            student_answer="A",
            attempt_number=idx,
            is_correct=True,
            score=1.0,
            evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        )
        db_session.add(attempt)
    db_session.flush()

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        desired_difficulty=0.50,
        preferred_count=6,
    )
    _, gap = gap_svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.LEARNING_FEEDBACK,
        source_entity_id=uuid4(),
        student_id=student_profile.id,
    )
    assert gap is not None
    assert gap.reason_code == QuestionSupplyReasonCode.STUDENT_EXPOSURE_EXHAUSTED

    acq_req = acq_svc.plan_or_get_active_request(gap.id, commit=False)
    # Required new candidate count must account for fresh deficit (preferred 6 - fresh 0 = 6)
    assert acq_req.required_new_candidate_count == 6


def test_plan_or_get_active_request_idempotency(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    gap_svc = QuestionSupplyGapService(db_session)
    acq_svc = QuestionAcquisitionService(db_session)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )
    _, gap = gap_svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ROOT_CAUSE_VERIFICATION,
        source_entity_id=uuid4(),
    )
    assert gap is not None

    req1 = acq_svc.plan_or_get_active_request(gap.id, commit=False)
    req2 = acq_svc.plan_or_get_active_request(gap.id, commit=False)
    assert req1.id == req2.id
    assert req1.attempt_index == 1


def test_resolved_gap_cannot_plan_acquisition(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    gap_svc = QuestionSupplyGapService(db_session)
    acq_svc = QuestionAcquisitionService(db_session)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )
    _, gap = gap_svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ROOT_CAUSE_VERIFICATION,
        source_entity_id=uuid4(),
    )
    assert gap is not None

    # Now add 3 APPROVED questions to satisfy ROOT_CAUSE_VERIFICATION (preferred=3)
    for i in range(3):
        _make_question(db_session, practice_content, index=i)
    db_session.flush()

    # Reassess resolves gap
    gap_resolved = gap_svc.reassess_gap(gap.id, commit=False)
    assert gap_resolved.status == QuestionSupplyStatus.RESOLVED

    with pytest.raises(ApplicationError) as exc:
        acq_svc.plan_or_get_active_request(gap.id, commit=False)
    assert exc.value.status_code == 409
    assert exc.value.code == "QUESTION_SUPPLY_GAP_ALREADY_RESOLVED"


def test_gap_status_lifecycle(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    gap_svc = QuestionSupplyGapService(db_session)
    acq_svc = QuestionAcquisitionService(db_session)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )
    _, gap = gap_svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ROOT_CAUSE_VERIFICATION,
        source_entity_id=uuid4(),
    )
    assert gap is not None
    assert gap.status == QuestionSupplyStatus.OPEN

    # 1. Plan request -> gap becomes IN_PROGRESS
    acq_req = acq_svc.plan_or_get_active_request(gap.id, commit=False)
    assert gap.status == QuestionSupplyStatus.IN_PROGRESS

    # 2. Cancel request -> gap returns to OPEN (because no other active request)
    acq_svc.cancel_request(acq_req.id, commit=False)
    assert gap.status == QuestionSupplyStatus.OPEN
