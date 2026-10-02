import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignments.models import AssignmentType
from app.assignments.schemas import AnswerSubmitItem, AssignmentCreate, AssignmentSubmissionRequest
from app.assignments.service import AssignmentService
from app.learning_evidence.models import LearningEvidenceEvent
from app.mastery.models import StudentConceptMastery
from tests.teacher_materials.test_teacher_materials import setup_domain, upload_ready


def test_teacher_material_evidence_is_append_only_and_mastery_once(
    db_session: Session, tmp_path
) -> None:
    domain = setup_domain(db_session, tmp_path)
    _, item = upload_ready(domain, db_session)
    service = AssignmentService(db_session)
    assignment = service.create_assignment(
        domain.teacher.id,
        AssignmentCreate(
            classroom_id=domain.classroom.id,
            subject_id=domain.subject.id,
            title="Evidence boundary",
            assignment_type=AssignmentType.SAME_SET,
            teacher_material_item_ids=[item.id],
            question_count=1,
        ),
    )
    service.publish_assignment(domain.teacher.id, assignment.id)
    service.submit_assignment(
        domain.student.id,
        assignment.id,
        AssignmentSubmissionRequest(
            answers=[AnswerSubmitItem(
                teacher_material_item_id=item.id, student_answer="A"
            )]
        ),
    )
    event = db_session.scalar(select(LearningEvidenceEvent))
    assert event is not None
    assert db_session.scalar(select(StudentConceptMastery)).attempt_count == 1

    event_id = event.id
    db_session.delete(event)
    with pytest.raises(ValueError):
        db_session.flush()
    db_session.rollback()
    assert db_session.scalar(select(LearningEvidenceEvent).where(
        LearningEvidenceEvent.id == event_id
    )) is not None
    assert db_session.scalar(select(StudentConceptMastery)).attempt_count == 1
