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
    subject=Subject(code=f"STEP-{uuid4().hex[:10].upper()}",name="Fixture mathematics",grade_level=12)
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


def _pdf_fixture(db):
    """Create genuine source/snapshot records in two distinct test classrooms."""
    from app.practice.models import EvaluationStatus

    owner, student, outsider, other_profile, teacher, subject, _question, _practice = _domain(db)
    a = Classroom(name="PDF Class A", academic_year="2026-2027", grade_level=12, created_by=teacher.id)
    b = Classroom(name="PDF Class B", academic_year="2026-2027", grade_level=12, created_by=teacher.id)
    db.add_all([a, b]); db.flush()
    db.add_all([
        StudentEnrollment(student_id=student.id, classroom_id=a.id, status=EnrollmentStatus.ACTIVE),
        StudentEnrollment(student_id=other_profile.id, classroom_id=b.id, status=EnrollmentStatus.ACTIVE),
    ])
    now = datetime.now(timezone.utc)
    assignments = [
        Assignment(classroom_id=room.id, subject_id=subject.id, title=f"PDF {tag}",
            assignment_type=AssignmentType.SAME_SET, status=AssignmentStatus.PUBLISHED,
            question_count=1, start_at=now-timedelta(days=1),
            due_at=now+timedelta(days=1), created_by=teacher.id)
        for room, tag in ((a, "A"), (b, "B"))
    ]
    db.add_all(assignments); db.flush()
    materials = [
        TeacherMaterial(
            classroom_id=room.id, subject_id=subject.id, uploaded_by=teacher.id,
            title=f"Material {tag}", original_file_name=f"{tag}.pdf",
            mime_type="application/pdf", storage_key=f"test/{uuid4().hex}.pdf",
            sha256=tag.lower()*64, file_size_bytes=128, page_count=1,
            status=TeacherMaterialStatus.READY,
        )
        for room, tag in ((a, "A"), (b, "B"))
    ]
    db.add_all(materials); db.flush()
    originals = [
        TeacherMaterialItem(
            teacher_material_id=material.id, order_index=0, page_start=1,
            page_end=1, content=f"Derivative PDF question {tag}",
            content_hash=tag.lower()*64, question_type=QuestionType.OPEN_RESPONSE,
            extraction_status=MaterialItemExtractionStatus.READY,
            evaluation_mode=MaterialEvaluationMode.TEACHER_REVIEW, raw_metadata={},
        )
        for material,tag in zip(materials,("A","B"))
    ]
    db.add_all(originals); db.flush()
    snapshots = [
        AssignmentMaterialItem(
            assignment_id=assignment.id, teacher_material_item_id=source.id,
            teacher_material_id=material.id, source_content_hash=tag.lower()*64,
            content=f"Immutable PDF snapshot {tag}", order_index=0,
            snapshotted_at=now, question_type=QuestionType.OPEN_RESPONSE,
            evaluation_mode=MaterialEvaluationMode.TEACHER_REVIEW,
        )
        for assignment,source,material,tag in zip(assignments,originals,materials,("A","B"))
    ]
    db.add_all(snapshots); db.flush()
    student_assignments = [
        StudentAssignment(assignment_id=assignment.id,student_id=profile.id,
                          status=StudentAssignmentStatus.NOT_STARTED)
        for assignment, profile in zip(assignments,(student,other_profile))
    ]
    db.add_all(student_assignments); db.flush()
    # Deliberately mismatch the first student's source item to verify the new guard.
    first = StudentAssignmentMaterialItem(
        student_assignment_id=student_assignments[0].id,
        teacher_material_item_id=originals[1].id,
        assignment_material_item_id=snapshots[0].id, order_index=0,
        evaluation_status=EvaluationStatus.NEEDS_EVALUATION,
    )
    second = StudentAssignmentMaterialItem(
        student_assignment_id=student_assignments[1].id,
        teacher_material_item_id=originals[1].id,
        assignment_material_item_id=snapshots[1].id, order_index=0,
        evaluation_status=EvaluationStatus.NEEDS_EVALUATION,
    )
    db.add_all([first,second]);db.commit()
    return {
        "owner":owner,"outsider":outsider,"assignments":student_assignments,
        "originals":originals,"snapshots":snapshots,"items":[first,second],
    }


def test_pdf_snapshot_real_source_identity_and_classroom_isolation(db_session):
    d=_pdf_fixture(db_session)
    service=MathSolutionService(db_session)
    student_assignment=d["assignments"][0]
    own_item=d["items"][0]
    def create_for(actor, student_assignment_id, item_id, key):
        return service.create(
            actor, source_kind="TEACHER_MATERIAL", context_type="CLASSROOM_ASSIGNMENT",
            mode="INDEPENDENT_SOLUTION", create_idempotency_key=key,
            student_assignment_id=student_assignment_id,
            student_assignment_material_item_id=item_id,
        )
    # A student item linking source-B to snapshot-A must fail even if its FK rows exist.
    with pytest.raises(ApplicationError) as e:
        create_for(d["owner"].id,student_assignment.id,own_item.id,"mismatch")
    assert e.value.code == "MATERIAL_ITEM_SNAPSHOT_MISMATCH"
    db_session.rollback()
    # Fix the controlled test fixture; only the source from class A now matches.
    own_item=db_session.get(StudentAssignmentMaterialItem, own_item.id)
    own_item.teacher_material_item_id=d["originals"][0].id
    db_session.commit()
    result=create_for(d["owner"].id,student_assignment.id,own_item.id,"valid-own")
    assert result["source_kind"]=="TEACHER_MATERIAL"
    attempt=db_session.get(SolutionAttempt,UUID(result["id"]))
    assert attempt.assignment_material_item_id==d["snapshots"][0].id
    assert attempt.student_assignment_material_item_id==own_item.id
    # Foreign student, other classroom, and foreign assigned PDF item cannot read/create.
    with pytest.raises(ApplicationError) as e:
        service.get(d["outsider"].id,attempt.id)
    assert e.value.code=="SOLUTION_ATTEMPT_NOT_FOUND"
    with pytest.raises(ApplicationError) as e:
        create_for(d["outsider"].id,student_assignment.id,own_item.id,"foreign-student")
    assert e.value.code=="ASSIGNMENT_NOT_ACCESSIBLE"
    with pytest.raises(ApplicationError) as e:
        create_for(d["owner"].id,student_assignment.id,d["items"][1].id,"foreign-item")
    assert e.value.code=="MATERIAL_ITEM_NOT_ACCESSIBLE"
    # A new assigned row can still point at another class's existing snapshot;
    # the service must compare Assignment.id rather than trusting its foreign key.
    contaminated=StudentAssignmentMaterialItem(
        student_assignment_id=student_assignment.id,
        teacher_material_item_id=d["originals"][1].id,
        assignment_material_item_id=d["snapshots"][1].id,
        order_index=1, evaluation_status="NEEDS_EVALUATION",
    )
    db_session.add(contaminated);db_session.commit()
    with pytest.raises(ApplicationError) as e:
        create_for(d["owner"].id,student_assignment.id,contaminated.id,"wrong-parent")
    assert e.value.code=="MATERIAL_SNAPSHOT_MISMATCH"


def test_create_idempotency_rejects_omitted_source_fields(db_session):
    d=_pdf_fixture(db_session)
    own=d["items"][0]
    own.teacher_material_item_id=d["originals"][0].id
    db_session.commit()
    service=MathSolutionService(db_session)
    args=dict(source_kind="TEACHER_MATERIAL",context_type="CLASSROOM_ASSIGNMENT",
              mode="INDEPENDENT_SOLUTION",create_idempotency_key="stable-create",
              student_assignment_id=d["assignments"][0].id,
              student_assignment_material_item_id=own.id)
    attempt=service.create(d["owner"].id,**args)
    assert service.create(d["owner"].id,**args)["id"]==attempt["id"]
    # Reuse the same transport key with omitted source is not an equivalent request.
    with pytest.raises(ApplicationError) as e:
        service.create(d["owner"].id,source_kind="TEACHER_MATERIAL",
                       context_type="CLASSROOM_ASSIGNMENT",
                       mode="INDEPENDENT_SOLUTION",
                       create_idempotency_key="stable-create")
    assert e.value.code=="CREATE_KEY_REUSED"
