from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge_gap.models import RootCauseDiagnosis
from app.knowledge_gap.root_cause import RootCauseDiagnosticService
from app.learning_evidence.models import LearningEvidenceEvent
from app.mastery.models import StudentConceptMastery
from app.students.models import StudentProfile
from tests.knowledge_gap.test_root_cause import _publish_practice
from tests.practice.conftest import (
    PracticeContent,
    practice_content,
    practice_students,
    practice_user_factory,
    student_profile,
)


def test_diagnostic_failure_does_not_discard_evidence_or_mastery(
    db_session: Session,
    monkeypatch,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("diagnostic consumer failure")

    monkeypatch.setattr(RootCauseDiagnosticService, "diagnose_event", fail)
    event, diagnosis = _publish_practice(db_session, practice_content, student_profile)
    assert diagnosis is None
    assert db_session.get(LearningEvidenceEvent, event.id) is not None
    mastery = db_session.scalar(
        select(StudentConceptMastery).where(
            StudentConceptMastery.student_id == student_profile.id,
            StudentConceptMastery.concept_id == practice_content.concept.id,
        )
    )
    assert mastery is not None and mastery.attempt_count == 1
    assert db_session.scalar(select(RootCauseDiagnosis)) is None
