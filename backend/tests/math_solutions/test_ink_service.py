from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import pytest
from sqlalchemy import func, select
from app.core.exceptions import ApplicationError
from app.math_ink.models import MathInkDocument, MathInkOperation, MathInkPage
from app.math_ink.prune_operations import prune_expired_operations
from app.math_ink.schemas import InkPageWrite, InkStroke, InkPoint
from app.math_ink.service import MathInkService
from app.math_solutions.service import MathSolutionService
from app.questions.models import Question, QuestionStatus, QuestionType
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService


def test_ink_save_replay_stale_and_ownership(db_session):
    users = UserService(db_session)
    owner = users.create_user(UserCreate(email="ink-owner@example.com",password="Ink-Test-Password-2026!",full_name="Ink Owner",role=Role.STUDENT))
    outsider = users.create_user(UserCreate(email="ink-outsider@example.com",password="Ink-Test-Password-2026!",full_name="Ink Outsider",role=Role.STUDENT))
    teacher = users.create_user(UserCreate(email="ink-teacher@example.com",password="Ink-Test-Password-2026!",full_name="Ink Teacher",role=Role.TEACHER))
    profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == owner.id))
    subject = Subject(code="MATH-INK-12",name="Math Ink",grade_level=12)
    db_session.add(subject)
    db_session.flush()
    question = Question(subject_id=subject.id,content="Ink test question",question_type=QuestionType.OPEN_RESPONSE,difficulty=0.5,correct_answer=None,explanation="Test",source_type="TEST",exam_weight=0.5,status=QuestionStatus.APPROVED,created_by=teacher.id)
    db_session.add(question)
    db_session.flush()
    practice = PracticeSession(student_id=profile.id,subject_id=subject.id,session_type=PracticeSessionType.PRACTICE,status=PracticeSessionStatus.ACTIVE)
    db_session.add(practice)
    db_session.commit()
    attempt = MathSolutionService(db_session).create(owner.id,source_kind="CANONICAL",context_type="SELF_PRACTICE",mode="INDEPENDENT_SOLUTION",create_idempotency_key="ink-attempt",question_id=question.id,practice_session_id=practice.id)
    aid = UUID(attempt["id"])
    ink = MathInkService(db_session)
    assert ink.get_document(owner.id,aid).document_revision == 0
    assert db_session.scalar(select(MathInkDocument)) is None
    payload = InkPageWrite(expected_document_revision=0,client_action_id=uuid4(),strokes=[InkStroke(id=uuid4(),tool="PEN",color="#225544",width=2,points=[InkPoint(x=0.2,y=0.3)])])
    first = ink.save_page(owner.id,aid,0,payload)
    assert first.document_revision == 1
    assert ink.save_page(owner.id,aid,0,payload) == first
    assert ink.get_page(owner.id,aid,0).strokes == payload.strokes
    assert db_session.scalar(select(MathInkPage)).stroke_count == 1
    no_op = ink.save_page(owner.id, aid, 0, payload.model_copy(update={
        "expected_document_revision": 1, "client_action_id": uuid4(),
    }))
    assert no_op.document_revision == 1
    assert ink.get_document(owner.id, aid).document_revision == 1
    with pytest.raises(ApplicationError) as err:
        ink.save_page(owner.id,aid,0,payload.model_copy(update={"client_action_id":uuid4()}))
    assert err.value.code == "INK_REVISION_CONFLICT"
    with pytest.raises(ApplicationError) as err:
        ink.get_document(outsider.id,aid)
    assert err.value.status_code == 404
    # Expired idempotency records are removed in bounded batches. Replaying an
    # expired action must conflict on the document revision instead of overwriting.
    operations = db_session.scalars(select(MathInkOperation)).all()
    assert len(operations) == 2
    expired_at = datetime.now(timezone.utc) - timedelta(days=8)
    for operation in operations:
        operation.created_at = expired_at
    db_session.commit()

    removed = prune_expired_operations(
        db_session, now=datetime.now(timezone.utc), batch_size=10
    )
    assert removed == 2
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(MathInkOperation)) == 0

    with pytest.raises(ApplicationError) as err:
        ink.save_page(owner.id, aid, 0, payload)
    assert err.value.code == "INK_REVISION_CONFLICT"

