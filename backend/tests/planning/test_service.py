from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classes.models import Classroom, TeacherClassroom
from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import (
    Chapter,
    LearningOutcome,
    ProblemType,
    ProblemTypeConcept,
    Topic,
)
from app.planning.models import TeachingPlanStatus
from app.planning.schemas import (
    TeachingPlanCreate,
    TeachingPlanItemCreate,
    TeachingPlanPatch,
)
from app.planning.service import TeachingPlanService
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

TEST_PASSWORD = "Teacher-Plan-Test-2026!"


def _create_user(session: Session, role: Role, email: str) -> User:
    return UserService(session).create_user(
        UserCreate(email=email, password=TEST_PASSWORD, full_name="Plan User", role=role)
    )


def _setup_curriculum(
    session: Session, code_prefix: str = "P"
) -> tuple[Subject, Chapter, Topic, ProblemType, Concept, LearningOutcome]:
    subject = Subject(code=f"{code_prefix}-SUB", name=f"{code_prefix} Subject", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(
        subject_id=subject.id,
        code=f"{code_prefix}-CHP",
        name="Chapter",
        order_index=0,
    )
    session.add(chapter)
    session.flush()

    topic = Topic(chapter_id=chapter.id, code=f"{code_prefix}-TOP", name="Topic", order_index=0)
    session.add(topic)
    session.flush()

    pt = ProblemType(
        topic_id=topic.id,
        code=f"{code_prefix}-PT",
        name="Problem Type",
        order_index=0,
        is_active=True,
    )
    session.add(pt)
    session.flush()

    concept = Concept(subject_id=subject.id, code=f"{code_prefix}-CON", name="Concept", order_index=0)
    session.add(concept)
    session.flush()

    session.add(
        ProblemTypeConcept(
            problem_type_id=pt.id,
            concept_id=concept.id,
            weight=1.0,
            is_primary=True,
        )
    )

    lo = LearningOutcome(
        subject_id=subject.id,
        code=f"{code_prefix}-LO",
        description="Learning outcome",
        grade_level=12,
        order_index=0,
    )
    session.add(lo)
    session.commit()
    return subject, chapter, topic, pt, concept, lo


def _setup_classroom(session: Session, teacher_user: User) -> Classroom:
    teacher = session.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == teacher_user.id)
    )
    classroom = Classroom(
        name="12A1",
        academic_year="2025-2026",
        grade_level=12,
        created_by=teacher_user.id,
    )
    classroom.teacher_assignments.append(
        TeacherClassroom(teacher_id=teacher.id, role="OWNER")
    )
    session.add(classroom)
    session.commit()
    session.refresh(classroom)
    return classroom


def test_ownership_teacher_assigned_can_manage_plans(db_session: Session) -> None:
    t1 = _create_user(db_session, Role.TEACHER, "t1.ownership@example.com")
    t2 = _create_user(db_session, Role.TEACHER, "t2.ownership@example.com")
    classroom = _setup_classroom(db_session, t1)
    subject, _, _, pt, _, _ = _setup_curriculum(db_session, "OWN")

    service = TeachingPlanService(db_session)
    data = TeachingPlanCreate(
        subject_id=subject.id,
        start_date=date.today(),
        items=[TeachingPlanItemCreate(problem_type_id=pt.id, priority=1)],
    )

    plan = service.create_plan(t1.id, classroom.id, data)
    assert plan.classroom_id == classroom.id
    assert plan.status == TeachingPlanStatus.PLANNED

    with pytest.raises(ApplicationError) as exc:
        service.create_plan(t2.id, classroom.id, data)
    assert exc.value.status_code == 403
    assert exc.value.code == "CLASSROOM_ACCESS_DENIED"

    with pytest.raises(ApplicationError) as exc:
        service.get_plan(t2.id, plan.id)
    assert exc.value.status_code == 403

    student = _create_user(db_session, Role.STUDENT, "s.ownership@example.com")
    with pytest.raises(ApplicationError) as exc:
        service.create_plan(student.id, classroom.id, data)
    assert exc.value.status_code == 404
    assert exc.value.code == "PROFILE_NOT_FOUND"


def test_active_plan_uniqueness_and_historical_plans(db_session: Session) -> None:
    teacher_user = _create_user(db_session, Role.TEACHER, "t.active@example.com")
    classroom = _setup_classroom(db_session, teacher_user)
    subject, _, topic, pt1, _, _ = _setup_curriculum(db_session, "ACT")

    pt2 = ProblemType(
        topic_id=topic.id,
        code="ACT-PT2",
        name="Problem Type 2",
        order_index=1,
        is_active=True,
    )
    db_session.add(pt2)
    db_session.commit()

    service = TeachingPlanService(db_session)
    plan1 = service.create_plan(
        teacher_user.id,
        classroom.id,
        TeachingPlanCreate(
            subject_id=subject.id,
            start_date=date.today(),
            status=TeachingPlanStatus.ACTIVE,
            items=[TeachingPlanItemCreate(problem_type_id=pt1.id, priority=1)],
        ),
    )
    assert plan1.status == TeachingPlanStatus.ACTIVE

    with pytest.raises(ApplicationError) as exc:
        service.create_plan(
            teacher_user.id,
            classroom.id,
            TeachingPlanCreate(
                subject_id=subject.id,
                start_date=date.today(),
                status=TeachingPlanStatus.ACTIVE,
                items=[TeachingPlanItemCreate(problem_type_id=pt2.id, priority=1)],
            ),
        )
    assert exc.value.status_code == 409
    assert exc.value.code == "ACTIVE_PLAN_CONFLICT"

    plan2 = service.create_plan(
        teacher_user.id,
        classroom.id,
        TeachingPlanCreate(
            subject_id=subject.id,
            start_date=date.today() + timedelta(days=14),
            status=TeachingPlanStatus.PLANNED,
            items=[TeachingPlanItemCreate(problem_type_id=pt2.id, priority=1)],
        ),
    )
    assert plan2.status == TeachingPlanStatus.PLANNED

    with pytest.raises(ApplicationError) as exc:
        service.activate_plan(teacher_user.id, plan2.id)
    assert exc.value.status_code == 409
    assert exc.value.code == "ACTIVE_PLAN_CONFLICT"

    completed_plan1 = service.complete_plan(teacher_user.id, plan1.id)
    assert completed_plan1.status == TeachingPlanStatus.COMPLETED

    activated_plan2 = service.activate_plan(teacher_user.id, plan2.id)
    assert activated_plan2.status == TeachingPlanStatus.ACTIVE


def test_plan_cannot_be_activated_without_items(db_session: Session) -> None:
    teacher_user = _create_user(db_session, Role.TEACHER, "t.empty@example.com")
    classroom = _setup_classroom(db_session, teacher_user)
    subject, _, _, _, _, _ = _setup_curriculum(db_session, "EMP")

    service = TeachingPlanService(db_session)
    with pytest.raises(ApplicationError) as exc:
        service.create_plan(
            teacher_user.id,
            classroom.id,
            TeachingPlanCreate(
                subject_id=subject.id,
                start_date=date.today(),
                status=TeachingPlanStatus.ACTIVE,
                items=[],
            ),
        )
    assert exc.value.status_code == 422
    assert exc.value.code == "EMPTY_TEACHING_PLAN"

    plan = service.create_plan(
        teacher_user.id,
        classroom.id,
        TeachingPlanCreate(
            subject_id=subject.id,
            start_date=date.today(),
            status=TeachingPlanStatus.PLANNED,
            items=[],
        ),
    )
    with pytest.raises(ApplicationError) as exc:
        service.activate_plan(teacher_user.id, plan.id)
    assert exc.value.status_code == 422
    assert exc.value.code == "EMPTY_TEACHING_PLAN"


def test_multiple_items_and_concept_derivation(db_session: Session) -> None:
    teacher_user = _create_user(db_session, Role.TEACHER, "t.multi@example.com")
    classroom = _setup_classroom(db_session, teacher_user)
    subject, _, topic, pt1, con1, lo = _setup_curriculum(db_session, "MUL")

    pt2 = ProblemType(
        topic_id=topic.id,
        code="MUL-PT2",
        name="Problem Type 2",
        order_index=1,
        is_active=True,
    )
    con2 = Concept(subject_id=subject.id, code="MUL-CON2", name="Concept 2", order_index=1)
    db_session.add_all([pt2, con2])
    db_session.flush()

    db_session.add(
        ProblemTypeConcept(
            problem_type_id=pt2.id,
            concept_id=con2.id,
            weight=1.0,
            is_primary=True,
        )
    )
    db_session.commit()

    service = TeachingPlanService(db_session)
    plan = service.create_plan(
        teacher_user.id,
        classroom.id,
        TeachingPlanCreate(
            subject_id=subject.id,
            start_date=date.today(),
            items=[
                TeachingPlanItemCreate(
                    problem_type_id=pt1.id,
                    learning_outcome_id=lo.id,
                    priority=2,
                    order_index=0,
                ),
                TeachingPlanItemCreate(
                    problem_type_id=pt2.id,
                    learning_outcome_id=None,
                    priority=1,
                    order_index=1,
                ),
            ],
        ),
    )

    assert len(plan.items) == 2
    item1 = next(item for item in plan.items if item.problem_type_id == pt1.id)
    item2 = next(item for item in plan.items if item.problem_type_id == pt2.id)

    assert item1.priority == 2
    assert item1.learning_outcome_id == lo.id
    assert item1.derived_concept_ids == [con1.id]

    assert item2.priority == 1
    assert item2.learning_outcome_id is None
    assert item2.derived_concept_ids == [con2.id]


def test_problem_type_validation(db_session: Session) -> None:
    teacher_user = _create_user(db_session, Role.TEACHER, "t.ptval@example.com")
    classroom = _setup_classroom(db_session, teacher_user)
    subject, _, topic, pt, _, _ = _setup_curriculum(db_session, "PTV")

    inactive_pt = ProblemType(
        topic_id=topic.id,
        code="PTV-INACTIVE",
        name="Inactive PT",
        order_index=1,
        is_active=False,
    )
    db_session.add(inactive_pt)
    db_session.commit()

    service = TeachingPlanService(db_session)

    with pytest.raises(ApplicationError) as exc:
        service.create_plan(
            teacher_user.id,
            classroom.id,
            TeachingPlanCreate(
                subject_id=subject.id,
                start_date=date.today(),
                items=[
                    TeachingPlanItemCreate(problem_type_id=pt.id, priority=1),
                    TeachingPlanItemCreate(problem_type_id=pt.id, priority=2),
                ],
            ),
        )
    assert exc.value.status_code == 422
    assert exc.value.code == "DUPLICATE_PROBLEM_TYPE"

    with pytest.raises(ApplicationError) as exc:
        service.create_plan(
            teacher_user.id,
            classroom.id,
            TeachingPlanCreate(
                subject_id=subject.id,
                start_date=date.today(),
                items=[TeachingPlanItemCreate(problem_type_id=uuid4(), priority=1)],
            ),
        )
    assert exc.value.status_code == 404
    assert exc.value.code == "PROBLEM_TYPE_NOT_FOUND"

    with pytest.raises(ApplicationError) as exc:
        service.create_plan(
            teacher_user.id,
            classroom.id,
            TeachingPlanCreate(
                subject_id=subject.id,
                start_date=date.today(),
                items=[TeachingPlanItemCreate(problem_type_id=inactive_pt.id, priority=1)],
            ),
        )
    assert exc.value.status_code == 422
    assert exc.value.code == "PROBLEM_TYPE_SUBJECT_MISMATCH"


def test_subject_consistency(db_session: Session) -> None:
    teacher_user = _create_user(db_session, Role.TEACHER, "t.subcon@example.com")
    classroom = _setup_classroom(db_session, teacher_user)
    subject_a, _, _, pt_a, _, lo_a = _setup_curriculum(db_session, "SCA")
    subject_b, _, _, pt_b, _, lo_b = _setup_curriculum(db_session, "SCB")

    service = TeachingPlanService(db_session)

    with pytest.raises(ApplicationError) as exc:
        service.create_plan(
            teacher_user.id,
            classroom.id,
            TeachingPlanCreate(
                subject_id=subject_a.id,
                start_date=date.today(),
                items=[TeachingPlanItemCreate(problem_type_id=pt_b.id, priority=1)],
            ),
        )
    assert exc.value.status_code == 422
    assert exc.value.code == "PROBLEM_TYPE_SUBJECT_MISMATCH"

    with pytest.raises(ApplicationError) as exc:
        service.create_plan(
            teacher_user.id,
            classroom.id,
            TeachingPlanCreate(
                subject_id=subject_a.id,
                start_date=date.today(),
                items=[
                    TeachingPlanItemCreate(
                        problem_type_id=pt_a.id,
                        learning_outcome_id=lo_b.id,
                        priority=1,
                    )
                ],
            ),
        )
    assert exc.value.status_code == 422
    assert exc.value.code == "LEARNING_OUTCOME_SUBJECT_MISMATCH"


def test_date_validation(db_session: Session) -> None:
    teacher_user = _create_user(db_session, Role.TEACHER, "t.dates@example.com")
    classroom = _setup_classroom(db_session, teacher_user)
    subject, _, _, pt, _, _ = _setup_curriculum(db_session, "DAT")

    service = TeachingPlanService(db_session)
    with pytest.raises(ApplicationError) as exc:
        service.create_plan(
            teacher_user.id,
            classroom.id,
            TeachingPlanCreate(
                subject_id=subject.id,
                start_date=date.today(),
                target_end_date=date.today() - timedelta(days=1),
                items=[TeachingPlanItemCreate(problem_type_id=pt.id, priority=1)],
            ),
        )
    assert exc.value.status_code == 422
    assert exc.value.code == "INVALID_DATE_RANGE"


def test_immutable_terminal_states(db_session: Session) -> None:
    teacher_user = _create_user(db_session, Role.TEACHER, "t.term@example.com")
    classroom = _setup_classroom(db_session, teacher_user)
    subject, _, _, pt, _, _ = _setup_curriculum(db_session, "TRM")

    service = TeachingPlanService(db_session)
    plan = service.create_plan(
        teacher_user.id,
        classroom.id,
        TeachingPlanCreate(
            subject_id=subject.id,
            start_date=date.today(),
            status=TeachingPlanStatus.ACTIVE,
            items=[TeachingPlanItemCreate(problem_type_id=pt.id, priority=1)],
        ),
    )

    completed = service.complete_plan(teacher_user.id, plan.id)
    assert completed.status == TeachingPlanStatus.COMPLETED

    with pytest.raises(ApplicationError) as exc:
        service.patch_plan(
            teacher_user.id,
            plan.id,
            TeachingPlanPatch(target_end_date=date.today() + timedelta(days=10)),
        )
    assert exc.value.status_code == 422
    assert exc.value.code == "TEACHING_PLAN_IMMUTABLE"

    with pytest.raises(ApplicationError) as exc:
        service.activate_plan(teacher_user.id, plan.id)
    assert exc.value.status_code == 422
    assert exc.value.code == "INVALID_STATUS_TRANSITION"
