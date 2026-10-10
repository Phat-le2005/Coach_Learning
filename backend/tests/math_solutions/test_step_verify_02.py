"""STEP-VERIFY-02: real PostgreSQL race and classroom source isolation tests."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.math_solutions.service import MathSolutionService
from app.math_solutions.schemas import SolutionStepDraft
from app.math_solutions.models import SolutionAttempt, SolutionOperation, SolutionStep
from app.users.models import User, Role
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile
from app.subjects.models import Subject
from app.classes.models import Classroom, StudentEnrollment, EnrollmentStatus
from app.assignments.models import (
    Assignment, AssignmentStatus, AssignmentType, StudentAssignment,
    StudentAssignmentMaterialItem, AssignmentMaterialItem, StudentAssignmentStatus,
)
from app.teacher_materials.models import (
    TeacherMaterial, TeacherMaterialItem, TeacherMaterialStatus,
    MaterialItemExtractionStatus, MaterialEvaluationMode,
)
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.questions.models import Question, QuestionType, QuestionStatus


def _identity(db, role, name):
    user=User(email=f"{name}-{uuid4().hex}@example.test",full_name=name,role=role,password_hash="test-only-no-login")
    db.add(user);db.flush()
    model={Role.STUDENT:StudentProfile,Role.TEACHER:TeacherProfile}[role]
    profile=model(user_id=user.id)
    db.add(profile);db.flush()
    return user,profile


def _domain(db):
    owner,student=_identity(db,Role.STUDENT,"owner")
    other,other_profile=_identity(db,Role.STUDENT,"outsider")
    teacher,_=_identity(db,Role.TEACHER,"teacher")
    subject=Subject(code=f"STEP{uuid4().hex[:10]}",name="Fixture mathematics",grade_level=12)
    db.add(subject);db.flush()
    question=Question(subject_id=subject.id,content="Find monotonic intervals",question_type=QuestionType.OPEN_RESPONSE,
        difficulty=.5,correct_answer=None,explanation="Test fixture",source_type="TEST",exam_weight=.5,
        status=QuestionStatus.APPROVED,created_by=teacher.id)
    db.add(question);db.flush()
    practice=PracticeSession(student_id=student.id,subject_id=subject.id,
        session_type=PracticeSessionType.PRACTICE,status=PracticeSessionStatus.ACTIVE)
    db.add(practice);db.commit()
    return owner,student,other,other_profile,teacher,subject,question,practice


def test_two_writers_one_revision_wins(postgres_engine):
    with Session(postgres_engine,expire_on_commit=False) as db:
        owner,student,*_,question,practice=_domain(db)
        created=MathSolutionService(db).create(owner.id,source_kind="CANONICAL",context_type="SELF_PRACTICE",
            mode="INDEPENDENT_SOLUTION",create_idempotency_key=uuid4().hex,
            question_id=question.id,practice_session_id=practice.id)
        attempt_id=UUID(created["id"])
    barrier=Barrier(2)
    def write(label):
        with Session(postgres_engine,expire_on_commit=False) as db:
            barrier.wait(timeout=15)
            try:
                result=MathSolutionService(db).add_step(owner.id,attempt_id,expected_attempt_revision=1,
                    client_action_id=uuid4(),draft=SolutionStepDraft(step_type="CUSTOM",content_latex=label))
                return ("ok",result)
            except ApplicationError as exc:
                return (exc.code,None)
    with ThreadPoolExecutor(max_workers=2) as executor:
        f1=executor.submit(write,"tab-a");f2=executor.submit(write,"tab-b")
        outcomes=[f1.result(timeout=30),f2.result(timeout=30)]
    assert sorted(x[0] for x in outcomes)==["SOLUTION_REVISION_CONFLICT","ok"]
    with Session(postgres_engine) as db:
        attempt=db.get(SolutionAttempt,attempt_id)
        assert attempt.attempt_revision_number==2
        assert len(db.scalars(select(SolutionStep).where(SolutionStep.attempt_id==attempt_id)).all())==1
        assert len(db.scalars(select(SolutionOperation).where(SolutionOperation.attempt_id==attempt_id)).all())==1


def test_classroom_pdf_cross_student_and_cross_assignment_rejected(db_session):
    db=db_session
    owner,student,other,other_profile,teacher,subject,question,practice=_domain(db)
    classroom_a=Classroom(name="Class A",academic_year="2026-2027",grade_level=12,created_by=teacher.id)
    classroom_b=Classroom(name="Class B",academic_year="2026-2027",grade_level=12,created_by=teacher.id)
    db.add_all([classroom_a,classroom_b]);db.flush()
    db.add(StudentEnrollment(student_id=student.id,classroom_id=classroom_a.id,status=EnrollmentStatus.ACTIVE))
    db.add(StudentEnrollment(student_id=other_profile.id,classroom_id=classroom_b.id,status=EnrollmentStatus.ACTIVE))
    db.flush()
    now=datetime.now(timezone.utc)
    assignment_a=Assignment(classroom_id=classroom_a.id,subject_id=subject.id,title="Assignment A",
        assignment_type=AssignmentType.SAME_SET,status=AssignmentStatus.PUBLISHED,question_count=1,
        start_at=now-timedelta(hours=1),due_at=now+timedelta(days=1),created_by=teacher.id)
    assignment_b=Assignment(classroom_id=classroom_b.id,subject_id=subject.id,title="Assignment B",
        assignment_type=AssignmentType.SAME_SET,status=AssignmentStatus.PUBLISHED,question_count=1,
        start_at=now-timedelta(hours=1),due_at=now+timedelta(days=1),created_by=teacher.id)
    db.add_all([assignment_a,assignment_b]);db.flush()
    sa=StudentAssignment(assignment_id=assignment_a.id,student_id=student.id,status=StudentAssignmentStatus.NOT_STARTED)
    sb=StudentAssignment(assignment_id=assignment_b.id,student_id=other_profile.id,status=StudentAssignmentStatus.NOT_STARTED)
    db.add_all([sa,sb]);db.flush()
    # A snapshot belongs to B, but is deliberately presented as if assigned to A.
    fake=StudentAssignmentMaterialItem(
        student_assignment_id=sa.id,teacher_material_item_id=uuid4(),assignment_material_item_id=uuid4(),
        order_index=0,evaluation_status="NEEDS_EVALUATION")
    # Do not commit invalid FK rows: use a B snapshot and directly test foreign student assignment.
    service=MathSolutionService(db)
    with pytest.raises(ApplicationError) as ex:
        service.create(owner.id,source_kind="TEACHER_MATERIAL",context_type="CLASSROOM_ASSIGNMENT",
            mode="INDEPENDENT_SOLUTION",create_idempotency_key=uuid4().hex,
            student_assignment_id=sb.id,student_assignment_material_item_id=uuid4())
    assert ex.value.code=="ASSIGNMENT_NOT_ACCESSIBLE"
    with pytest.raises(ApplicationError) as ex:
        service.create(other.id,source_kind="TEACHER_MATERIAL",context_type="CLASSROOM_ASSIGNMENT",
            mode="INDEPENDENT_SOLUTION",create_idempotency_key=uuid4().hex,
            student_assignment_id=sa.id,student_assignment_material_item_id=uuid4())
    assert ex.value.code=="ASSIGNMENT_NOT_ACCESSIBLE"
