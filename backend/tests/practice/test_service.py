from dataclasses import dataclass, field
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.practice.evidence import AttemptEvaluatedEvidence
from app.practice.models import QuestionAttempt
from app.practice.schemas import PracticeAnswerCreate, PracticeSessionCreate
from app.practice.service import PracticeService
from app.users.models import User
from tests.practice.conftest import PracticeContent


@dataclass
class RecordingPublisher:
    events: list[AttemptEvaluatedEvidence] = field(default_factory=list)

    def publish(self, evidence: AttemptEvaluatedEvidence, session: Session) -> None:
        self.events.append(evidence)


class FailingPublisher:
    def publish(self, evidence: AttemptEvaluatedEvidence, session: Session) -> None:
        raise RuntimeError("simulated downstream failure")


def create_practice(
    service: PracticeService, student: User, content: PracticeContent
) -> UUID:
    practice = service.create_session(
        student,
        PracticeSessionCreate(
            subject_id=content.subject.id,
            session_type="PRACTICE",
            problem_type_ids=[content.problem_type.id],
            concept_ids=[content.concept.id],
        ),
    )
    return practice.id


def test_auto_evaluation_publishes_classified_attempt_evidence(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    publisher = RecordingPublisher()
    service = PracticeService(db_session, evidence_publisher=publisher)
    practice_id = create_practice(service, student, practice_content)
    attempt = service.answer(
        student,
        practice_id,
        PracticeAnswerCreate(question_id=practice_content.mcq.id, student_answer="B"),
    )

    assert len(publisher.events) == 1
    evidence = publisher.events[0]
    assert evidence.attempt_id == attempt.id
    assert evidence.problem_type_ids == (practice_content.problem_type.id,)
    assert evidence.concept_ids == (practice_content.concept.id,)
    assert evidence.learning_outcome_ids == (practice_content.learning_outcome.id,)


def test_evidence_failure_rolls_back_attempt_transaction(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    service = PracticeService(db_session, evidence_publisher=FailingPublisher())
    practice_id = create_practice(service, student, practice_content)

    with pytest.raises(RuntimeError, match="simulated downstream failure"):
        service.answer(
            student,
            practice_id,
            PracticeAnswerCreate(question_id=practice_content.mcq.id, student_answer="B"),
        )

    count = db_session.scalar(
        select(func.count()).select_from(QuestionAttempt).where(
            QuestionAttempt.practice_session_id == practice_id
        )
    )
    assert count == 0


def test_open_response_does_not_publish_evaluated_evidence(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    publisher = RecordingPublisher()
    service = PracticeService(db_session, evidence_publisher=publisher)
    practice_id = create_practice(service, student, practice_content)
    service.answer(
        student,
        practice_id,
        PracticeAnswerCreate(
            question_id=practice_content.open_response.id,
            student_answer="A reasoned response",
        ),
    )
    assert publisher.events == []

