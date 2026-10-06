from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.config import Settings
from app.curriculum.models import (
    Chapter,
    LearningOutcome,
    ProblemType,
    ProblemTypeConcept,
    Topic,
)
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.planning.models import (
    StudyPlan,
    StudyPlanStatus,
    StudyTask,
    StudyTaskReasonCode,
    StudyTaskStatus,
    StudyTaskType,
    TeachingPlan,
    TeachingPlanItem,
    TeachingPlanStatus,
)
from app.planning.study_service import StudyPlanService
from app.review.service import ReviewScheduleService
from app.students.goal_models import AcademicGoal, AcademicGoalStatus, SubjectGoal
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

TEST_PASSWORD = "StudyPlan-Test-Password-2026!"


def _create_user(session: Session, role: Role, email: str) -> User:
    return UserService(session).create_user(
        UserCreate(email=email, password=TEST_PASSWORD, full_name="Plan Test User", role=role)
    )


def _auth_headers(session: Session, settings: Settings, user: User) -> dict[str, str]:
    tokens = AuthService(session, settings).login(
        LoginRequest(email=user.email, password=TEST_PASSWORD)
    )
    return {"Authorization": f"Bearer {tokens.access_token}"}


def _setup_curriculum(session: Session, code_prefix: str = "STD") -> tuple[Subject, ProblemType, Concept]:
    subject = Subject(code=f"{code_prefix}-SUB", name=f"{code_prefix} Subject", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(subject_id=subject.id, code=f"{code_prefix}-CHP", name="Chapter", order_index=0)
    session.add(chapter)
    session.flush()

    topic = Topic(chapter_id=chapter.id, code=f"{code_prefix}-TOP", name="Topic", order_index=0)
    session.add(topic)
    session.flush()

    pt = ProblemType(topic_id=topic.id, code=f"{code_prefix}-PT", name="Problem Type", order_index=0, is_active=True)
    concept = Concept(subject_id=subject.id, code=f"{code_prefix}-CON", name="Concept", order_index=0)
    session.add_all([pt, concept])
    session.flush()

    session.add(ProblemTypeConcept(problem_type_id=pt.id, concept_id=concept.id, weight=1.0, is_primary=True))
    session.flush()
    return subject, pt, concept


def test_active_lesson_priority(db_session: Session) -> None:
    teacher_user = _create_user(db_session, Role.TEACHER, "active.teacher@example.com")
    student_user = _create_user(db_session, Role.STUDENT, "active.student@example.com")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))

    subject, pt_active, concept = _setup_curriculum(db_session, "ACT")

    # Enroll student in classroom
    classroom = Classroom(
        name="12A1 Active", academic_year="2026-2027", grade_level=12, created_by=teacher_user.id
    )
    db_session.add(classroom)
    db_session.flush()

    teacher_profile = db_session.scalar(select(TeacherProfile).where(TeacherProfile.user_id == teacher_user.id))
    db_session.add(
        TeacherClassroom(teacher_id=teacher_profile.id, classroom_id=classroom.id, role="OWNER")
    )
    db_session.add(
        StudentEnrollment(student_id=student_profile.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE)
    )

    # Active teaching plan with pt_active
    t_plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.ACTIVE,
        created_by=teacher_user.id,
    )
    db_session.add(t_plan)
    db_session.flush()

    db_session.add(
        TeachingPlanItem(
            teaching_plan_id=t_plan.id,
            problem_type_id=pt_active.id,
            priority=5,
            order_index=0,
        )
    )
    db_session.commit()

    service = StudyPlanService(db_session)
    plan_read = service.recalculate_study_plan(student_profile.id, as_of=date.today())

    assert len(plan_read.tasks) > 0
    today_tasks = [t for t in plan_read.tasks if t.planned_date == date.today()]
    assert len(today_tasks) > 0

    # Verify that CURRENT_TEACHING_PLAN task for pt_active is scheduled
    teaching_plan_tasks = [
        t for t in today_tasks if t.reason_code == StudyTaskReasonCode.CURRENT_TEACHING_PLAN
    ]
    assert len(teaching_plan_tasks) > 0
    assert any(t.problem_type_id == pt_active.id for t in teaching_plan_tasks)
    assert any(t.task_type in (StudyTaskType.LEARN, StudyTaskType.PRACTICE) for t in teaching_plan_tasks)


def test_specific_gap(db_session: Session) -> None:
    student_user = _create_user(db_session, Role.STUDENT, "gap.student@example.com")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))

    subject, pt_weak, concept = _setup_curriculum(db_session, "GAP")

    # Add weak problem type mastery (score = 0.25 < 0.50)
    db_session.add(
        StudentProblemTypeMastery(
            student_id=student_profile.id,
            problem_type_id=pt_weak.id,
            mastery_score=0.25,
            confidence=0.8,
            attempt_count=5,
            correct_count=1,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    service = StudyPlanService(db_session)
    plan_read = service.recalculate_study_plan(student_profile.id, as_of=date.today())

    gap_tasks = [
        t for t in plan_read.tasks if t.reason_code == StudyTaskReasonCode.WEAK_PROBLEM_TYPE
    ]
    assert len(gap_tasks) > 0
    assert any(t.problem_type_id == pt_weak.id for t in gap_tasks)
    assert any(t.task_type == StudyTaskType.REPAIR for t in gap_tasks)


def test_prerequisite_weakness(db_session: Session) -> None:
    student_user = _create_user(db_session, Role.STUDENT, "prereq.student@example.com")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))

    subject, pt, concept_target = _setup_curriculum(db_session, "PRQ")

    concept_prereq = Concept(subject_id=subject.id, code="PRQ-BASE", name="Base Concept", order_index=0)
    db_session.add(concept_prereq)
    db_session.flush()

    # concept_prereq is PREREQUISITE of concept_target
    db_session.add(
        ConceptRelation(
            source_concept_id=concept_prereq.id,
            target_concept_id=concept_target.id,
            relation_type=RelationType.PREREQUISITE,
        )
    )

    # Student has weak mastery on concept_prereq (0.30 < 0.60)
    db_session.add(
        StudentConceptMastery(
            student_id=student_profile.id,
            concept_id=concept_prereq.id,
            mastery_score=0.30,
            confidence=0.8,
            attempt_count=5,
            correct_count=1,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    service = StudyPlanService(db_session)
    plan_read = service.recalculate_study_plan(student_profile.id, as_of=date.today())

    prereq_tasks = [
        t for t in plan_read.tasks if t.reason_code == StudyTaskReasonCode.PREREQUISITE_REPAIR
    ]
    assert len(prereq_tasks) > 0
    assert any(t.concept_id == concept_prereq.id for t in prereq_tasks)
    assert any(t.task_type == StudyTaskType.REPAIR for t in prereq_tasks)


def test_review_due(db_session: Session) -> None:
    student_user = _create_user(db_session, Role.STUDENT, "review.student@example.com")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))

    subject, pt, concept = _setup_curriculum(db_session, "REV")

    # Ensure review schedule is DUE (next_review_at was yesterday)
    review_service = ReviewScheduleService(db_session)
    review_service.ensure_problem_type_schedule(
        student_profile.id,
        pt.id,
        as_of=datetime.now(timezone.utc) - timedelta(days=2),
        initial_interval_days=1.0,
    )
    db_session.commit()

    service = StudyPlanService(db_session)
    plan_read = service.recalculate_study_plan(student_profile.id, as_of=date.today())

    review_tasks = [
        t for t in plan_read.tasks if t.reason_code == StudyTaskReasonCode.REVIEW_DUE
    ]
    assert len(review_tasks) > 0
    assert any(t.problem_type_id == pt.id for t in review_tasks)
    assert any(t.task_type == StudyTaskType.REVIEW for t in review_tasks)


def test_time_budget(db_session: Session) -> None:
    student_user = _create_user(db_session, Role.STUDENT, "budget.student@example.com")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))

    subject, pt, concept = _setup_curriculum(db_session, "BDG")

    # Set academic goal with available_daily_minutes = 45
    goal = AcademicGoal(
        student_id=student_profile.id,
        target_exam="THPTQG 2026",
        exam_date=date.today() + timedelta(days=60),
        available_daily_minutes=45,
        status=AcademicGoalStatus.ACTIVE,
    )
    db_session.add(goal)
    db_session.flush()

    db_session.add(
        SubjectGoal(
            academic_goal_id=goal.id,
            subject_id=subject.id,
            target_score=8.5,
        )
    )
    db_session.commit()

    service = StudyPlanService(db_session)
    plan_read = service.recalculate_study_plan(student_profile.id, as_of=date.today(), horizon_days=7)

    assert plan_read.available_daily_minutes == 45

    # Check each day in the horizon: total minutes should respect budget (<= 45 + small tolerance of 15 min)
    tasks_by_date: dict[date, int] = {}
    for task in plan_read.tasks:
        tasks_by_date[task.planned_date] = tasks_by_date.get(task.planned_date, 0) + task.estimated_duration_minutes

    for plan_date, total_minutes in tasks_by_date.items():
        assert total_minutes <= 60, f"Date {plan_date} duration {total_minutes} exceeds reasonable budget limit"


def test_missed_days(db_session: Session) -> None:
    student_user = _create_user(db_session, Role.STUDENT, "missed.student@example.com")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))

    subject, pt, concept = _setup_curriculum(db_session, "MIS")

    # Create plan and manually inject tasks 3 days ago in PENDING status
    plan = StudyPlan(
        student_id=student_profile.id,
        start_date=date.today() - timedelta(days=5),
        status=StudyPlanStatus.ACTIVE,
    )
    db_session.add(plan)
    db_session.flush()

    past_task1 = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.PRACTICE,
        status=StudyTaskStatus.PENDING,
        planned_date=date.today() - timedelta(days=3),
        estimated_duration_minutes=20,
        priority=1,
        order_index=0,
        reason_code=StudyTaskReasonCode.GENERAL_PRACTICE,
    )
    past_task2 = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.REVIEW,
        status=StudyTaskStatus.PENDING,
        planned_date=date.today() - timedelta(days=2),
        estimated_duration_minutes=15,
        priority=1,
        order_index=0,
        reason_code=StudyTaskReasonCode.GENERAL_PRACTICE,
    )
    db_session.add_all([past_task1, past_task2])
    db_session.commit()

    service = StudyPlanService(db_session)
    day_read = service.get_today_plan(student_profile.id, as_of=date.today())

    # Verify that past pending tasks are now marked SKIPPED
    db_session.refresh(past_task1)
    db_session.refresh(past_task2)
    assert past_task1.status == StudyTaskStatus.SKIPPED
    assert past_task2.status == StudyTaskStatus.SKIPPED


def test_exam_approaching(db_session: Session) -> None:
    student_user = _create_user(db_session, Role.STUDENT, "exam.student@example.com")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))

    subject, pt, concept = _setup_curriculum(db_session, "EXM")

    # Goal with exam_date 7 days away (imminent <= 14)
    goal = AcademicGoal(
        student_id=student_profile.id,
        target_exam="THPTQG Imminent",
        exam_date=date.today() + timedelta(days=7),
        available_daily_minutes=60,
        status=AcademicGoalStatus.ACTIVE,
    )
    db_session.add(goal)
    db_session.flush()
    db_session.add(SubjectGoal(academic_goal_id=goal.id, subject_id=subject.id, target_score=9.0))
    db_session.commit()

    service = StudyPlanService(db_session)
    plan_read = service.recalculate_study_plan(student_profile.id, as_of=date.today())

    today_tasks = [t for t in plan_read.tasks if t.planned_date == date.today()]
    exam_prep_tasks = [t for t in today_tasks if t.reason_code == StudyTaskReasonCode.EXAM_PREPARATION]
    assert len(exam_prep_tasks) > 0
    assert any(t.task_type in (StudyTaskType.EXAM, StudyTaskType.MINI_TEST) for t in exam_prep_tasks)

    # Notice message in today view
    today_read = service.get_today_plan(student_profile.id, as_of=date.today())
    assert today_read.notice is not None
    assert "7 ngày" in today_read.notice


def test_no_giant_backlog(db_session: Session) -> None:
    student_user = _create_user(db_session, Role.STUDENT, "backlog.student@example.com")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))

    subject, pt, concept = _setup_curriculum(db_session, "BKL")

    plan = StudyPlan(
        student_id=student_profile.id,
        start_date=date.today() - timedelta(days=10),
        status=StudyPlanStatus.ACTIVE,
    )
    db_session.add(plan)
    db_session.flush()

    # Simulate student missing 5 days with 10 pending tasks created in the past
    past_tasks: list[StudyTask] = []
    for d in range(1, 6):
        past_tasks.append(
            StudyTask(
                study_plan_id=plan.id,
                task_type=StudyTaskType.PRACTICE,
                status=StudyTaskStatus.PENDING,
                planned_date=date.today() - timedelta(days=d),
                estimated_duration_minutes=30,
                priority=1,
                order_index=0,
                reason_code=StudyTaskReasonCode.GENERAL_PRACTICE,
            )
        )
        past_tasks.append(
            StudyTask(
                study_plan_id=plan.id,
                task_type=StudyTaskType.REVIEW,
                status=StudyTaskStatus.PENDING,
                planned_date=date.today() - timedelta(days=d),
                estimated_duration_minutes=20,
                priority=1,
                order_index=1,
                reason_code=StudyTaskReasonCode.GENERAL_PRACTICE,
            )
        )
    db_session.add_all(past_tasks)
    db_session.commit()

    # Student returns today and recalculates
    service = StudyPlanService(db_session)
    plan_read = service.recalculate_study_plan(student_profile.id, as_of=date.today())

    # 1. Past tasks must be SKIPPED, not active
    for pt_task in past_tasks:
        db_session.refresh(pt_task)
        assert pt_task.status == StudyTaskStatus.SKIPPED

    # 2. Today's task list must NOT contain the 10 missed tasks piled up
    today_tasks = [t for t in plan_read.tasks if t.planned_date == date.today()]
    assert len(today_tasks) <= 4, f"Too many tasks on today: {len(today_tasks)}, giant backlog detected!"
    today_duration = sum(t.estimated_duration_minutes for t in today_tasks)
    assert today_duration <= 75, f"Today duration {today_duration} exceeds normal daily limit!"


def test_study_plan_api_endpoints(db_client: TestClient, db_session: Session, settings: Settings) -> None:
    student_user = _create_user(db_session, Role.STUDENT, "api.student@example.com")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))

    subject, pt, concept = _setup_curriculum(db_session, "API")

    goal = AcademicGoal(
        student_id=student_profile.id,
        target_exam="THPTQG 2026",
        exam_date=date.today() + timedelta(days=90),
        available_daily_minutes=60,
        status=AcademicGoalStatus.ACTIVE,
    )
    db_session.add(goal)
    db_session.flush()
    db_session.add(SubjectGoal(academic_goal_id=goal.id, subject_id=subject.id, target_score=8.0))
    db_session.commit()

    headers = _auth_headers(db_session, settings, student_user)

    # 1. GET before plan exists returns 404 without mutating DB
    res_empty_today = db_client.get("/students/me/today", headers=headers)
    assert res_empty_today.status_code == 404
    assert res_empty_today.json()["error"]["code"] == "STUDY_PLAN_NOT_FOUND"

    res_empty_plan = db_client.get("/students/me/study-plan", headers=headers)
    assert res_empty_plan.status_code == 404
    assert res_empty_plan.json()["error"]["code"] == "STUDY_PLAN_NOT_FOUND"

    # 2. POST /students/me/study-plan/recalculate generates the active plan
    res_recalc = db_client.post(
        "/students/me/study-plan/recalculate",
        headers=headers,
        json={"horizon_days": 7},
    )
    assert res_recalc.status_code == 200
    assert res_recalc.headers.get("Cache-Control") == "no-store"
    data_recalc = res_recalc.json()
    assert data_recalc["student_id"] == str(student_profile.id)
    assert len(data_recalc["tasks"]) > 0

    # 3. GET /students/me/today now returns read-only snapshot
    res_today = db_client.get("/students/me/today", headers=headers)
    assert res_today.status_code == 200
    assert res_today.headers.get("Cache-Control") == "no-store"
    data_today = res_today.json()
    assert "date" in data_today
    assert "tasks" in data_today
    assert data_today["available_daily_minutes"] == 60

    # 4. GET /students/me/study-plan now returns active plan snapshot
    res_plan = db_client.get("/students/me/study-plan", headers=headers)
    assert res_plan.status_code == 200
    assert res_plan.headers.get("Cache-Control") == "no-store"
    data_plan = res_plan.json()
    assert data_plan["student_id"] == str(student_profile.id)
    assert data_plan["status"] == "ACTIVE"
    assert len(data_plan["tasks"]) > 0
