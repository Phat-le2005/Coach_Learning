from sqlalchemy.orm import Session

from app.ai.tutor_context_builder import TutorContextBuilder
from app.digital_twin.service import StudentDigitalTwinService
from app.misconceptions.models import (
    MisconceptionCategory,
    MisconceptionDefinition,
)
from app.misconceptions.service import MisconceptionService
from app.students.models import StudentProfile
from tests.practice.conftest import PracticeContent


def test_digital_twin_and_tutor_context_read_active_relational_state(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    definition = MisconceptionDefinition(
        code="TEST_TWIN_SIGN_REVERSAL",
        concept_id=practice_content.concept.id,
        problem_type_id=practice_content.problem_type.id,
        name="Sign reversal",
        description="Reverses the sign interpretation in a monotonicity problem.",
        category=MisconceptionCategory.CONCEPTUAL,
        is_active=True,
    )
    db_session.add(definition)
    db_session.commit()
    service = MisconceptionService(db_session)
    service.record_evidence(student_profile.id, definition.id)
    service.record_evidence(student_profile.id, definition.id)

    snapshot = StudentDigitalTwinService(db_session).get_snapshot(student_profile.id)
    assert [item.code for item in snapshot.known_misconceptions] == [definition.code]
    assert snapshot.known_misconceptions[0].status == "CONFIRMED"

    context = TutorContextBuilder(db_session)._build_misconceptions_context(
        student_profile.id, [practice_content.concept.id]
    )
    assert definition.code in context
    assert "CONFIRMED" in context

    service.resolve(student_profile.id, definition.id)
    assert (
        StudentDigitalTwinService(db_session)
        .get_snapshot(student_profile.id)
        .known_misconceptions
        == []
    )
