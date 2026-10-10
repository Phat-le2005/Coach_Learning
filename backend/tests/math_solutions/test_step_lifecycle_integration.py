"""STEP-VERIFY-01: exercise actual migration and solution lifecycle on test database."""
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.database.base import Base
from app.math_solutions.models import SolutionAttempt, SolutionOperation, StepRevision, SolutionStep
from app.math_solutions.schemas import SolutionStepDraft
from app.math_solutions.service import MathSolutionService
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.questions.models import Question, QuestionStatus, QuestionType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.learning_evidence.models import LearningEvidenceEvent
from app.mastery.models import StudentConceptMastery


@pytest.fixture
def solution_domain(db_session):
    users=UserService(db_session)
    student=users.create_user(UserCreate(email="verify-step-student@example.com", password="Verify-Student-Password-2026!", full_name="Student",role=Role.STUDENT))
    outsider=users.create_user(UserCreate(email="verify-step-outsider@example.com", password="Verify-Outsider-Password-2026!", full_name="Outsider",role=Role.STUDENT))
    teacher=users.create_user(UserCreate(email="verify-step-teacher@example.com", password="Verify-Teacher-Password-2026!", full_name="Teacher",role=Role.TEACHER))
    sp=db_session.scalar(select(StudentProfile).where(StudentProfile.user_id==student.id))
    subject=Subject(code="TEST-STEP-12",name="Test Step Mathematics",grade_level=12)
    db_session.add(subject);db_session.flush()
    question=Question(subject_id=subject.id,content="Find increasing intervals for x^3-3x",question_type=QuestionType.OPEN_RESPONSE,difficulty=.5,correct_answer=None,explanation="Test-only fixture",source_type="TEST",exam_weight=.5,status=QuestionStatus.APPROVED,created_by=teacher.id)
    db_session.add(question);db_session.flush()
    practice=PracticeSession(student_id=sp.id,subject_id=subject.id,session_type=PracticeSessionType.PRACTICE,status=PracticeSessionStatus.ACTIVE)
    db_session.add(practice);db_session.commit()
    return {"student":student,"outsider":outsider,"teacher":teacher,"student_profile":sp,"question":question,"practice":practice}


def _create(s, d):
    return s.create(d["student"].id,source_kind="CANONICAL",context_type="SELF_PRACTICE",mode="INDEPENDENT_SOLUTION",create_idempotency_key="step-case-1",question_id=d["question"].id,practice_session_id=d["practice"].id)


def _call(s, name, d, current, **kwargs):
    return getattr(s,name)(d["student"].id, UUID(current["id"]),expected_attempt_revision=current["attempt_revision_number"],client_action_id=uuid4(),**kwargs)


def test_real_schema_supports_reorder_delete_restore_and_submission(db_session, solution_domain):
    d=solution_domain;s=MathSolutionService(db_session)
    current=_create(s,d)
    assert current["attempt_revision_number"]==1
    for formula in ("f'(x)=3x^2-3","x=-1,1","f'(x)>0"):
        current=_call(s,"add_step",d,current,draft=SolutionStepDraft(step_type="CUSTOM",content_latex=formula))
    assert [z["step_index"] for z in current["steps"]]==[1,2,3]
    ordered=[current["steps"][1]["id"],current["steps"][0]["id"],current["steps"][2]["id"]]
    current=_call(s,"reorder_steps",d,current,step_ids=[UUID(k) for k in ordered])
    assert current["steps"][0]["id"]==ordered[0]
    current=_call(s,"delete_step",d,current,step_id=UUID(ordered[0]))
    assert len(current["steps"])==2
    current=_call(s,"restore_step",d,current,step_id=UUID(ordered[0]))
    assert len(current["steps"])==3
    first=UUID(current["steps"][0]["id"])
    current=_call(s,"update_step",d,current,step_id=first,draft=SolutionStepDraft(step_type="CUSTOM",content_latex="revised"))
    history=s.list_revisions(d["student"].id,UUID(current["id"]),first)
    assert len(history)>=2
    current=_call(s,"rollback_step",d,current,step_id=first,to_revision=1)
    assert current["steps"][0]["content_latex"]!="revised"
    current=_call(s,"submit",d,current)
    assert current["status"]=="SUBMITTED"
    with pytest.raises(ApplicationError) as exc:
        _call(s,"add_step",d,current,draft=SolutionStepDraft(step_type="CUSTOM",content_latex="after submit"))
    assert exc.value.code=="SOLUTION_LOCKED"
    assert db_session.scalar(select(LearningEvidenceEvent)) is None
    assert db_session.scalar(select(StudentConceptMastery)) is None


def test_idempotency_and_stale_revision(db_session, solution_domain):
    d=solution_domain;s=MathSolutionService(db_session);current=_create(s,d)
    duplicate=_create(s,d)
    assert duplicate["id"]==current["id"]
    key=uuid4()
    args={"expected_attempt_revision":current["attempt_revision_number"],"client_action_id":key,"draft":SolutionStepDraft(step_type="CUSTOM",content_latex="first")}
    first=s.add_step(d["student"].id,UUID(current["id"]),**args)
    same=s.add_step(d["student"].id,UUID(current["id"]),**args)
    assert same==first
    with pytest.raises(ApplicationError) as exc:
        s.add_step(d["student"].id,UUID(current["id"]),expected_attempt_revision=1,client_action_id=key,draft=SolutionStepDraft(step_type="CUSTOM",content_latex="different"))
    assert exc.value.code=="ACTION_KEY_REUSED"
    with pytest.raises(ApplicationError) as exc:
        s.add_step(d["student"].id,UUID(current["id"]),expected_attempt_revision=1,client_action_id=uuid4(),draft=SolutionStepDraft(step_type="CUSTOM",content_latex="stale"))
    assert exc.value.code=="SOLUTION_REVISION_CONFLICT"
    assert db_session.scalar(select(SolutionOperation).where(SolutionOperation.client_action_id==key)) is not None


def test_cross_student_and_teacher_denied(db_session, solution_domain):
    d=solution_domain;s=MathSolutionService(db_session);current=_create(s,d)
    for actor in (d["outsider"],d["teacher"]):
        with pytest.raises(ApplicationError):
            s.get(actor.id,UUID(current["id"]))
    assert db_session.scalar(select(SolutionAttempt).where(SolutionAttempt.id==UUID(current["id"]))) is not None


def test_pg_math_schema_roundtrip_isolated():
    """Exercise 0046 against an ephemeral PostgreSQL schema, separate from legacy migrations."""
    import os
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.schema import CreateSchema, DropSchema
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from tests.migrations import load_migration

    url = os.getenv("EDUMS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL integration requires EDUMS_TEST_DATABASE_URL")
    if make_url(url).drivername != "postgresql+psycopg":
        pytest.fail("Only PostgreSQL test URLs are allowed")
    engine = create_engine(url, hide_parameters=True)
    schema = "step_verify_" + uuid4().hex
    created = False
    try:
        with engine.begin() as conn:
            conn.execute(CreateSchema(schema))
        created = True
        with engine.begin() as conn:
            conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
            # Minimal foreign-key parents; testing 0046 itself, not legacy migrations.
            for name in (
                "users", "student_profiles", "questions", "assignment_material_items",
                "student_assignment_material_items", "assignment_student_questions",
                "practice_sessions", "assignments", "student_assignments", "misconception_definitions",
                "learning_evidence_events",
            ):
                conn.exec_driver_sql(f"CREATE TABLE {name} (id UUID PRIMARY KEY)")
            with Operations.context(MigrationContext.configure(conn)):
                load_migration("0046_math_solutions").upgrade()
            expected = {name for name in Base.metadata.tables if name.startswith("math_")}
            inspector = inspect(conn)
            assert expected.issubset(set(inspector.get_table_names()))
            assert any(i["name"] == "uq_math_solution_step_active_index" and i["unique"]
                       for i in inspector.get_indexes("math_solution_steps"))
            with Operations.context(MigrationContext.configure(conn)):
                load_migration("0046_math_solutions").downgrade()
            inspector = inspect(conn)
            assert expected.isdisjoint(set(inspector.get_table_names()))
    finally:
        if created:
            with engine.begin() as conn:
                conn.execute(DropSchema(schema, cascade=True))
        engine.dispose()
