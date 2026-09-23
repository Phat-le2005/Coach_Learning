from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.misconceptions.models import (
    MisconceptionCategory,
    MisconceptionDefinition,
    StudentMisconceptionStatus,
)
from app.misconceptions.service import MisconceptionPolicy, MisconceptionService
from app.students.models import StudentProfile
from tests.practice.conftest import PracticeContent


@pytest.fixture
def misconception_definition(
    db_session: Session, practice_content: PracticeContent
) -> MisconceptionDefinition:
    definition = MisconceptionDefinition(
        code="TEST_DERIVATIVE_SIGN",
        concept_id=practice_content.concept.id,
        problem_type_id=practice_content.problem_type.id,
        name="Derivative sign reversed",
        description="Reverses the monotonic direction implied by a derivative sign.",
        category=MisconceptionCategory.CONCEPTUAL,
        is_active=True,
    )
    db_session.add(definition)
    db_session.commit()
    return definition


def test_single_wrong_answer_never_confirms_persistent_misconception(
    db_session: Session,
    student_profile: StudentProfile,
    misconception_definition: MisconceptionDefinition,
) -> None:
    service = MisconceptionService(db_session)
    first = service.record_evidence(
        student_profile.id,
        misconception_definition.id,
        confidence_increment=1.0,
    )

    assert first.status == StudentMisconceptionStatus.SUSPECTED
    assert first.occurrence_count == 1
    assert first.confidence == 1.0

    second = service.record_evidence(
        student_profile.id,
        misconception_definition.id,
        confidence_increment=0.1,
    )
    assert second.status == StudentMisconceptionStatus.CONFIRMED
    assert second.occurrence_count == 2
    assert second.confidence == 1.0


def test_default_evidence_progression_is_deterministic(
    db_session: Session,
    student_profile: StudentProfile,
    misconception_definition: MisconceptionDefinition,
) -> None:
    service = MisconceptionService(db_session)
    first = service.record_evidence(student_profile.id, misconception_definition.id)
    assert first.confidence == 0.35
    assert first.status == StudentMisconceptionStatus.SUSPECTED

    second = service.record_evidence(student_profile.id, misconception_definition.id)
    assert second.confidence == 0.7
    assert second.status == StudentMisconceptionStatus.CONFIRMED


def test_increase_confidence_is_bounded_and_does_not_invent_occurrences(
    db_session: Session,
    student_profile: StudentProfile,
    misconception_definition: MisconceptionDefinition,
) -> None:
    service = MisconceptionService(db_session)
    state = service.record_evidence(student_profile.id, misconception_definition.id)
    increased = service.increase_confidence(
        student_profile.id, misconception_definition.id, 0.9
    )

    assert increased.confidence == 1.0
    assert increased.occurrence_count == state.occurrence_count == 1
    assert increased.status == StudentMisconceptionStatus.SUSPECTED
    with pytest.raises(ApplicationError) as invalid:
        service.increase_confidence(
            student_profile.id, misconception_definition.id, 0.0
        )
    assert invalid.value.code == "INVALID_CONFIDENCE_INCREMENT"


def test_confirm_if_threshold_requires_confidence_and_repeated_occurrence(
    db_session: Session,
    student_profile: StudentProfile,
    misconception_definition: MisconceptionDefinition,
) -> None:
    service = MisconceptionService(
        db_session,
        policy=MisconceptionPolicy(confirmation_threshold=0.9),
    )
    service.record_evidence(student_profile.id, misconception_definition.id)
    service.increase_confidence(
        student_profile.id, misconception_definition.id, 0.55
    )
    one_occurrence = service.confirm_if_threshold(
        student_profile.id, misconception_definition.id
    )
    assert one_occurrence.confidence == 0.9
    assert one_occurrence.status == StudentMisconceptionStatus.SUSPECTED

    confirmed = service.record_evidence(
        student_profile.id,
        misconception_definition.id,
        confidence_increment=0.01,
    )
    assert confirmed.occurrence_count == 2
    assert confirmed.status == StudentMisconceptionStatus.CONFIRMED


def test_resolve_and_later_evidence_reopens_as_suspected(
    db_session: Session,
    student_profile: StudentProfile,
    misconception_definition: MisconceptionDefinition,
) -> None:
    service = MisconceptionService(db_session)
    detected = datetime(2026, 1, 10, tzinfo=timezone.utc)
    service.record_evidence(
        student_profile.id,
        misconception_definition.id,
        detected_at=detected,
    )
    resolution = detected + timedelta(days=2)
    resolved = service.resolve(
        student_profile.id,
        misconception_definition.id,
        resolved_at=resolution,
    )
    assert resolved.status == StudentMisconceptionStatus.RESOLVED
    assert resolved.resolved_at == resolution

    with pytest.raises(ApplicationError) as stale:
        service.record_evidence(
            student_profile.id,
            misconception_definition.id,
            detected_at=resolution - timedelta(hours=1),
        )
    assert stale.value.code == "MISCONCEPTION_EVIDENCE_STALE"
    db_session.rollback()

    reopened = service.record_evidence(
        student_profile.id,
        misconception_definition.id,
        detected_at=resolution + timedelta(days=1),
    )
    assert reopened.status == StudentMisconceptionStatus.SUSPECTED
    assert reopened.resolved_at is None
    assert reopened.confidence == 0.35
    assert reopened.occurrence_count == 2


def test_inactive_definition_rejects_evidence(
    db_session: Session,
    student_profile: StudentProfile,
    misconception_definition: MisconceptionDefinition,
) -> None:
    misconception_definition.is_active = False
    db_session.commit()

    with pytest.raises(ApplicationError) as inactive:
        MisconceptionService(db_session).record_evidence(
            student_profile.id, misconception_definition.id
        )
    assert inactive.value.code == "MISCONCEPTION_DEFINITION_INACTIVE"


def test_policy_cannot_allow_confirmation_from_one_occurrence() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        MisconceptionPolicy(minimum_occurrences=1)
