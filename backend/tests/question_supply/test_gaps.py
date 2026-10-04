"""Tests for QuestionSupplyGapService gap lifecycle, deduplication, reassessment, and Admin API authorization."""

from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)

from app.question_supply.models import (
    QuestionSupplyGap,
    QuestionSupplyGapObservation,
    QuestionSupplyHealth,
    QuestionSupplyObservationSourceKind,
    QuestionSupplyReasonCode,
    QuestionSupplySeverity,
    QuestionSupplyStatus,
    QuestionSupplyTargetType,
    QuestionSupplyUseCase,
)
from app.question_supply.service import (
    QuestionSupplyGapService,
    QuestionSupplyRequirement,
)
from app.questions.models import Question, QuestionStatus
from app.students.models import StudentProfile
from app.users.models import Role, User
from tests.practice.conftest import (
    PracticeContent,
    practice_bearer,
    practice_content,
    practice_students,
    practice_user_factory,
    student_profile,
)
from tests.question_supply.test_sufficiency import _archive_questions, _make_question


def test_gap_deduplication_and_observation_idempotency(
    db_session: Session, practice_content: PracticeContent, student_profile: StudentProfile
) -> None:
    _archive_questions(db_session)
    svc = QuestionSupplyGapService(db_session)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        desired_difficulty=0.40,
    )

    # Student 1 observes shortage
    decision_id_1 = uuid4()
    report1, gap1 = svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.LEARNING_FEEDBACK,
        source_entity_id=decision_id_1,
        student_id=student_profile.id,
    )
    assert gap1 is not None
    assert gap1.demand_count == 1

    # Student 2 observes shortage with same requirement
    user2 = User(
        email=f"s2_{uuid4().hex[:8]}@example.com",
        password_hash="hash",
        full_name="Student 2",
        role=Role.STUDENT,
    )
    db_session.add(user2)
    db_session.flush()
    profile2 = StudentProfile(user_id=user2.id, grade_level=12)
    db_session.add(profile2)
    db_session.flush()

    decision_id_2 = uuid4()
    report2, gap2 = svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.LEARNING_FEEDBACK,
        source_entity_id=decision_id_2,
        student_id=profile2.id,
    )
    assert gap2 is not None
    assert gap2.id == gap1.id  # Same deduplicated gap
    assert gap2.demand_count == 2

    # Student 3 observes shortage with same requirement
    user3 = User(
        email=f"s3_{uuid4().hex[:8]}@example.com",
        password_hash="hash",
        full_name="Student 3",
        role=Role.STUDENT,
    )
    db_session.add(user3)
    db_session.flush()
    profile3 = StudentProfile(user_id=user3.id, grade_level=12)
    db_session.add(profile3)
    db_session.flush()

    decision_id_3 = uuid4()
    report3, gap3 = svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.LEARNING_FEEDBACK,
        source_entity_id=decision_id_3,
        student_id=profile3.id,
    )
    assert gap3.id == gap1.id
    assert gap3.demand_count == 3

    # Total observations should be 3
    observations = list(
        db_session.scalars(
            select(QuestionSupplyGapObservation).where(
                QuestionSupplyGapObservation.gap_id == gap1.id
            )
        )
    )
    assert len(observations) == 3

    # Idempotency check: Repeated call with SAME decision_id_1 should NOT create duplicate observation
    _, gap_repeat = svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.LEARNING_FEEDBACK,
        source_entity_id=decision_id_1,
        student_id=student_profile.id,
    )
    assert gap_repeat.demand_count == 3
    observations_after = list(
        db_session.scalars(
            select(QuestionSupplyGapObservation).where(
                QuestionSupplyGapObservation.gap_id == gap1.id
            )
        )
    )
    assert len(observations_after) == 3


def test_gap_reassessment_and_reopen(
    db_session: Session, practice_content: PracticeContent, student_profile: StudentProfile
) -> None:
    _archive_questions(db_session)
    svc = QuestionSupplyGapService(db_session)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )

    # 1. 0 questions -> Gap OPEN, CRITICAL
    _, gap = svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ROOT_CAUSE_VERIFICATION,
        source_entity_id=uuid4(),
        student_id=student_profile.id,
    )
    assert gap is not None
    assert gap.status == QuestionSupplyStatus.OPEN
    assert gap.severity == QuestionSupplySeverity.CRITICAL
    first_obs_at = gap.first_observed_at

    # 2. Add 2 questions (meets min=2, but < preferred=3) -> reassess
    _make_question(db_session, practice_content, index=1)
    _make_question(db_session, practice_content, index=2)

    gap = svc.reassess_gap(gap.id, commit=False)
    assert gap.approved_eligible_count == 2
    assert gap.status == QuestionSupplyStatus.OPEN

    # 3. Add 1 more question (meets preferred=3) -> reassess resolves gap!
    _make_question(db_session, practice_content, index=3)
    gap = svc.reassess_gap(gap.id, commit=False)
    assert gap.approved_eligible_count == 3
    assert gap.status == QuestionSupplyStatus.RESOLVED

    # 4. Future shortage occurs (e.g. 2 questions get archived)
    for q in list(db_session.scalars(select(Question).where(Question.status == QuestionStatus.APPROVED)))[:2]:
        q.status = QuestionStatus.ARCHIVED
    db_session.flush()

    # New shortage observation on same requirement
    _, gap_reopened = svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ROOT_CAUSE_VERIFICATION,
        source_entity_id=uuid4(),
        student_id=student_profile.id,
    )
    assert gap_reopened.id == gap.id
    assert gap_reopened.status == QuestionSupplyStatus.OPEN  # REOPENED!
    assert gap_reopened.first_observed_at == first_obs_at  # first_observed_at preserved


def test_reassess_open_gaps_batch(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    svc = QuestionSupplyGapService(db_session)

    req1 = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )
    svc.assess_and_record(
        requirement=req1,
        source_kind=QuestionSupplyObservationSourceKind.ROOT_CAUSE_VERIFICATION,
        source_entity_id=uuid4(),
    )

    reassessed = svc.reassess_open_gaps(commit=False)
    assert len(reassessed) >= 1


def test_admin_api_authorization_and_endpoints(
    db_client: TestClient,
    db_session: Session,
    practice_content: PracticeContent,
    practice_user_factory,
    practice_bearer,
) -> None:
    _archive_questions(db_session)

    # Setup roles
    student_user = practice_user_factory(Role.STUDENT, f"student_{uuid4().hex[:8]}@example.com")
    teacher_user = practice_user_factory(Role.TEACHER, f"teacher_{uuid4().hex[:8]}@example.com")
    admin_user = practice_user_factory(Role.ADMIN, f"admin_{uuid4().hex[:8]}@example.com")

    student_headers = practice_bearer(student_user)
    teacher_headers = practice_bearer(teacher_user)
    admin_headers = practice_bearer(admin_user)

    # 1. Non-admin access to /question-supply/gaps is forbidden
    resp_student = db_client.get(
        "/question-supply/gaps",
        headers=student_headers,
    )
    assert resp_student.status_code == 403

    resp_teacher = db_client.get(
        "/question-supply/gaps",
        headers=teacher_headers,
    )
    assert resp_teacher.status_code == 403

    # 2. Admin access is allowed
    resp_admin = db_client.get(
        "/question-supply/gaps",
        headers=admin_headers,
    )
    assert resp_admin.status_code == 200
    assert isinstance(resp_admin.json(), list)

    # 3. Create a gap to test detail and reassess endpoints
    svc = QuestionSupplyGapService(db_session)
    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )
    _, gap = svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ROOT_CAUSE_VERIFICATION,
        source_entity_id=uuid4(),
        commit=True,
    )
    assert gap is not None

    resp_detail = db_client.get(
        f"/question-supply/gaps/{gap.id}",
        headers=admin_headers,
    )
    assert resp_detail.status_code == 200
    detail_data = resp_detail.json()
    assert detail_data["id"] == str(gap.id)
    assert "observations" in detail_data
    assert len(detail_data["observations"]) == 1

    # Reassess endpoint
    resp_reassess = db_client.post(
        f"/question-supply/gaps/{gap.id}/reassess",
        headers=admin_headers,
    )
    assert resp_reassess.status_code == 200

    # Reassess open gaps
    resp_reassess_open = db_client.post(
        "/question-supply/gaps/reassess-open",
        headers=admin_headers,
    )
    assert resp_reassess_open.status_code == 200

    # Read-only assess endpoint
    resp_assess = db_client.post(
        "/question-supply/assess",
        json={
            "subject_id": str(practice_content.subject.id),
            "use_case": "ROOT_CAUSE_VERIFICATION",
            "target_type": "CONCEPT",
            "concept_id": str(practice_content.concept.id),
        },
        headers=admin_headers,
    )
    assert resp_assess.status_code == 200
    assess_data = resp_assess.json()
    assert assess_data["subject_id"] == str(practice_content.subject.id)
    assert "is_startable" in assess_data
    assert "health" in assess_data


def test_gap_reassess_requires_difficulty_coverage(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    svc = QuestionSupplyGapService(db_session)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        desired_difficulty=0.50,
    )

    # 1. 0 questions -> Gap OPEN, reason NO_APPROVED_TARGET_QUESTIONS
    _, gap = svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ADAPTIVE_REPAIR_START,
        source_entity_id=uuid4(),
    )
    assert gap is not None
    assert gap.status == QuestionSupplyStatus.OPEN
    assert gap.reason_code == QuestionSupplyReasonCode.NO_APPROVED_TARGET_QUESTIONS

    # 2. Add 8 questions OUTSIDE difficulty band (difficulty=0.20 < 0.35)
    for i in range(8):
        _make_question(db_session, practice_content, index=i + 1, difficulty=0.20)
    db_session.flush()

    # Reassess gap -> total count is 8 (>= pref=6), BUT in-band is 0 (< min=4)!
    # Must NOT resolve! Remains OPEN with INSUFFICIENT_DIFFICULTY_COVERAGE
    gap = svc.reassess_gap(gap.id, commit=False)
    assert gap.approved_eligible_count == 8
    assert gap.approved_in_band_count == 0
    assert gap.status == QuestionSupplyStatus.OPEN
    assert gap.reason_code == QuestionSupplyReasonCode.INSUFFICIENT_DIFFICULTY_COVERAGE

    # 3. Add 4 questions IN BAND (0.50) -> in-band meets min=4, but < pref=6
    for i in range(8, 12):
        _make_question(db_session, practice_content, index=i + 1, difficulty=0.50)
    db_session.flush()

    gap = svc.reassess_gap(gap.id, commit=False)
    assert gap.approved_eligible_count == 12
    assert gap.approved_in_band_count == 4
    assert gap.status == QuestionSupplyStatus.OPEN
    assert gap.reason_code == QuestionSupplyReasonCode.THIN_DIFFICULTY_COVERAGE

    # 4. Add 4 more questions IN BAND (0.50) -> in-band is 8 (>= pref=8)
    for i in range(12, 16):
        _make_question(db_session, practice_content, index=i + 1, difficulty=0.50)
    db_session.flush()

    gap = svc.reassess_gap(gap.id, commit=False)
    assert gap.approved_eligible_count == 16
    assert gap.approved_in_band_count == 8
    assert gap.status == QuestionSupplyStatus.RESOLVED


def test_student_exposure_gap_not_resolved_by_global_count_alone(
    db_session: Session, practice_content: PracticeContent, student_profile: StudentProfile
) -> None:
    _archive_questions(db_session)
    svc = QuestionSupplyGapService(db_session)

    # Create 8 in-band questions (global supply is SUFFICIENT: 8 >= pref=8)
    questions = [
        _make_question(db_session, practice_content, index=i + 1, difficulty=0.50)
        for i in range(8)
    ]
    db_session.flush()

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        desired_difficulty=0.50,
    )

    # Global assessment is SUFFICIENT
    report_global = svc.sufficiency_service.assess(req)
    assert report_global.health == QuestionSupplyHealth.SUFFICIENT

    # Now simulate student having attempted all 8 questions in practice attempts
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

    for idx, q in enumerate(questions, start=1):
        attempt = QuestionAttempt(
            practice_session_id=ps.id,
            question_id=q.id,
            student_id=student_profile.id,
            attempt_number=idx,
            student_answer="wrong",
            is_correct=False,
            score=0.0,
            evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        )
        db_session.add(attempt)
    db_session.flush()

    # When student is evaluated, fresh count is 0 -> STUDENT_EXPOSURE_EXHAUSTED
    obs_id = uuid4()
    report_student, gap = svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.LEARNING_FEEDBACK,
        source_entity_id=obs_id,
        student_id=student_profile.id,
    )
    assert gap is not None
    assert gap.status == QuestionSupplyStatus.OPEN
    assert gap.reason_code == QuestionSupplyReasonCode.STUDENT_EXPOSURE_EXHAUSTED

    # Reassessing gap must use the latest observation student context:
    # Since student still has 0 fresh questions, gap remains OPEN and reason remains STUDENT_EXPOSURE_EXHAUSTED!
    gap = svc.reassess_gap(gap.id, commit=False)
    assert gap.status == QuestionSupplyStatus.OPEN
    assert gap.reason_code == QuestionSupplyReasonCode.STUDENT_EXPOSURE_EXHAUSTED

    # Add 8 NEW questions to the bank that student has NOT attempted
    for i in range(8, 16):
        _make_question(db_session, practice_content, index=i + 1, difficulty=0.50)
    db_session.flush()

    # Now reassess gap -> student fresh count is 8 (>= pref=8) -> RESOLVED!
    gap = svc.reassess_gap(gap.id, commit=False)
    assert gap.status == QuestionSupplyStatus.RESOLVED


def test_concurrent_gap_creation_recovers_unique_race(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    svc = QuestionSupplyGapService(db_session)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        desired_difficulty=0.50,
    )

    # Pre-create the gap aggregate in the database
    first_obs_id = uuid4()
    _, existing_gap = svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ADAPTIVE_REPAIR_START,
        source_entity_id=first_obs_id,
    )
    assert existing_gap is not None
    assert existing_gap.demand_count == 1

    # Simulate race condition: Worker B queries for existing gap and gets None
    # (as if checking concurrently before Worker A committed), so it attempts
    # to insert duplicate QuestionSupplyGap into DB. Nested savepoint catches
    # IntegrityError on unique signature constraint, rolls back, reloads existing gap,
    # increments demand_count to 2, and records Worker B's observation.
    real_scalar = db_session.scalar
    first_query = True

    def mocked_scalar(statement, *args, **kwargs):
        nonlocal first_query
        stmt_str = str(statement)
        if "question_supply_gaps" in stmt_str and "signature" in stmt_str and first_query:
            first_query = False
            return None
        return real_scalar(statement, *args, **kwargs)

    second_obs_id = uuid4()
    with patch.object(db_session, "scalar", side_effect=mocked_scalar):
        report, recovered_gap = svc.assess_and_record(
            requirement=req,
            source_kind=QuestionSupplyObservationSourceKind.LEARNING_FEEDBACK,
            source_entity_id=second_obs_id,
        )

    assert recovered_gap.id == existing_gap.id
    assert recovered_gap.demand_count == 2

    observations = list(
        db_session.scalars(
            select(QuestionSupplyGapObservation).where(
                QuestionSupplyGapObservation.gap_id == recovered_gap.id
            )
        )
    )
    assert len(observations) == 2


def test_duplicate_observation_race_is_idempotent(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    svc = QuestionSupplyGapService(db_session)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        desired_difficulty=0.50,
    )

    source_id = uuid4()
    _, gap = svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ADAPTIVE_REPAIR_START,
        source_entity_id=source_id,
    )
    assert gap is not None
    assert gap.demand_count == 1

    # Simulate observation race: check for existing observation returns None once,
    # causing an attempted insert that hits IntegrityError on uq_question_supply_obs_source.
    # Savepoint rolls back and demand_count is NOT incremented.
    real_scalar = db_session.scalar
    race_simulated = False

    def mocked_scalar(statement, *args, **kwargs):
        nonlocal race_simulated
        stmt_str = str(statement)
        if (
            "question_supply_gap_observations" in stmt_str
            and "source_entity_id" in stmt_str
            and not race_simulated
        ):
            race_simulated = True
            return None
        return real_scalar(statement, *args, **kwargs)

    with patch.object(db_session, "scalar", side_effect=mocked_scalar):
        _, gap_after = svc.assess_and_record(
            requirement=req,
            source_kind=QuestionSupplyObservationSourceKind.ADAPTIVE_REPAIR_START,
            source_entity_id=source_id,
        )

    assert gap_after.id == gap.id
    assert gap_after.demand_count == 1
    observations = list(
        db_session.scalars(
            select(QuestionSupplyGapObservation).where(
                QuestionSupplyGapObservation.gap_id == gap.id
            )
        )
    )
    assert len(observations) == 1


def test_demand_count_matches_unique_observations(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    svc = QuestionSupplyGapService(db_session)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )

    source_ids = [uuid4() for _ in range(3)]
    for src in source_ids:
        svc.assess_and_record(
            requirement=req,
            source_kind=QuestionSupplyObservationSourceKind.ROOT_CAUSE_VERIFICATION,
            source_entity_id=src,
        )

    # Repeat with same source_ids
    for src in source_ids[:2]:
        svc.assess_and_record(
            requirement=req,
            source_kind=QuestionSupplyObservationSourceKind.ROOT_CAUSE_VERIFICATION,
            source_entity_id=src,
        )

    gap = db_session.scalar(
        select(QuestionSupplyGap).where(
            QuestionSupplyGap.subject_id == practice_content.subject.id,
            QuestionSupplyGap.concept_id == practice_content.concept.id,
            QuestionSupplyGap.use_case == QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        )
    )
    assert gap is not None
    assert gap.demand_count == 3
    observations = list(
        db_session.scalars(
            select(QuestionSupplyGapObservation).where(
                QuestionSupplyGapObservation.gap_id == gap.id
            )
        )
    )
    assert len(observations) == 3

