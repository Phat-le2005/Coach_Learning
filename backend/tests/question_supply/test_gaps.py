"""Tests for QuestionSupplyGapService gap lifecycle, deduplication, reassessment, and Admin API authorization."""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

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
