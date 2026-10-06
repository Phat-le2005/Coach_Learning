from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.config import Settings, get_settings
from app.curriculum.models import Chapter, ProblemType, ProblemTypeConcept, Topic
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
from app.planning.study_explanation_schemas import (
    StudyPlanExplanationInput,
    StudyPlanExplanationItem,
    StudyPlanExplanationOutput,
    StudyPlanExplanationRead,
)
from app.planning.study_explanation_service import StudyPlanExplanationService
from app.planning.study_service import StudyPlanService
from app.students.goal_models import AcademicGoal, AcademicGoalStatus
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

TEST_PASSWORD = "StudyPlan-Explanation-Test-2026!"


def _create_user(session: Session, role: Role, email: str) -> User:
    return UserService(session).create_user(
        UserCreate(email=email, password=TEST_PASSWORD, full_name="Explanation Test User", role=role)
    )


def _auth_headers(session: Session, settings: Settings, user: User) -> dict[str, str]:
    tokens = AuthService(session, settings).login(
        LoginRequest(email=user.email, password=TEST_PASSWORD)
    )
    return {"Authorization": f"Bearer {tokens.access_token}"}


def _setup_curriculum(session: Session, code_prefix: str = "EXP") -> tuple[Subject, ProblemType, Concept]:
    subject = Subject(code=f"{code_prefix}-SUB", name=f"{code_prefix} Toán học", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(subject_id=subject.id, code=f"{code_prefix}-CHP", name="Chương 1", order_index=0)
    session.add(chapter)
    session.flush()

    topic = Topic(chapter_id=chapter.id, code=f"{code_prefix}-TOP", name="Chủ đề 1", order_index=0)
    session.add(topic)
    session.flush()

    pt = ProblemType(
        topic_id=topic.id,
        code=f"{code_prefix}-PT",
        name="Tìm tham số về tính đơn điệu",
        order_index=0,
        is_active=True,
    )
    concept = Concept(
        subject_id=subject.id,
        code=f"{code_prefix}-CON",
        name="Giải bất phương trình",
        order_index=0,
    )
    session.add_all([pt, concept])
    session.flush()

    session.add(ProblemTypeConcept(problem_type_id=pt.id, concept_id=concept.id, weight=1.0, is_primary=True))
    session.flush()
    return subject, pt, concept


# --------------------------------------------------------------------------
# 1. Test AI Success: Generates all 3 components properly
# --------------------------------------------------------------------------


def test_study_plan_explanation_ai_success(db_session: Session) -> None:
    user = _create_user(db_session, Role.STUDENT, "ai_success@example.com")
    profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    subject, pt, concept = _setup_curriculum(db_session, "AIS")

    # Mock AI provider with canned response
    mock_provider = MockAIProvider()
    mock_provider.canned_structured = StudyPlanExplanationOutput(
        concise_daily_overview="Hôm nay bạn có 2 nhiệm vụ học tập quan trọng trong khoảng 45 phút.",
        priority_reasoning=(
            "Hôm nay ưu tiên dạng tìm tham số về tính đơn điệu vì kết quả gần đây ở dạng này còn yếu; "
            "một phần bài tập cũng củng cố kỹ năng giải bất phương trình."
        ),
        getting_started_guide=(
            "Hãy bắt đầu với nhiệm vụ tìm tham số về tính đơn điệu trong 25 phút. "
            "Nhớ kiểm tra kỹ điều kiện đạo hàm không đổi dấu trên khoảng."
        ),
    )
    settings = get_settings()
    gateway = AIGateway(provider=mock_provider, settings=settings)

    explainer = StudyPlanExplanationService(db_session, gateway=gateway)

    input_data = StudyPlanExplanationInput(
        student_name="Nguyễn Văn A",
        today_tasks=[
            StudyPlanExplanationItem(
                id=uuid4(),
                title="Tìm tham số về tính đơn điệu",
                task_type=StudyTaskType.PRACTICE,
                priority=100,
                estimated_duration_minutes=25,
                reason_code="WEAK_PROBLEM_TYPE",
                problem_type_id=pt.id,
                problem_type_name=pt.name,
                concept_id=concept.id,
                concept_name=concept.name,
            )
        ],
        academic_goal_title="Mục tiêu thi tốt nghiệp THPT",
        days_remaining=30,
        recent_progress_summary="Đã hoàn thành 5/6 nhiệm vụ trong 7 ngày qua.",
        weak_problem_types=["Tìm tham số về tính đơn điệu"],
        relevant_weak_concepts=["Giải bất phương trình"],
    )

    result = explainer.explain_study_plan(input_data, user_id=user.id)

    assert result.is_fallback is False
    assert "Hôm nay bạn có 2 nhiệm vụ" in result.concise_daily_overview
    assert "ưu tiên dạng tìm tham số về tính đơn điệu" in result.priority_reasoning
    assert "củng cố kỹ năng giải bất phương trình" in result.priority_reasoning
    assert "Bắt đầu" in result.getting_started_guide or "bắt đầu" in result.getting_started_guide


# --------------------------------------------------------------------------
# 2. Test Fallback when AI fails or is unavailable
# --------------------------------------------------------------------------


def test_study_plan_explanation_fallback_when_ai_fails(db_session: Session) -> None:
    user = _create_user(db_session, Role.STUDENT, "ai_fail@example.com")
    subject, pt, concept = _setup_curriculum(db_session, "AIF")

    # Mock AI provider configured to fail
    mock_provider = MockAIProvider(service_unavailable_failures=3)
    settings = get_settings()
    gateway = AIGateway(provider=mock_provider, settings=settings)

    explainer = StudyPlanExplanationService(db_session, gateway=gateway)

    input_data = StudyPlanExplanationInput(
        student_name="Trần Văn B",
        today_tasks=[
            StudyPlanExplanationItem(
                id=uuid4(),
                title="Tìm tham số về tính đơn điệu",
                task_type=StudyTaskType.PRACTICE,
                priority=120,
                estimated_duration_minutes=25,
                reason_code="WEAK_PROBLEM_TYPE",
                problem_type_id=pt.id,
                problem_type_name=pt.name,
            )
        ],
        weak_problem_types=["Tìm tham số về tính đơn điệu"],
        relevant_weak_concepts=["Giải bất phương trình"],
    )

    result = explainer.explain_study_plan(input_data)

    # Fallback must be triggered cleanly without error
    assert result.is_fallback is True
    assert "Tìm tham số về tính đơn điệu" in result.priority_reasoning
    assert "Giải bất phương trình" in result.priority_reasoning
    assert "25 phút" in result.getting_started_guide or "Tìm tham số về tính đơn điệu" in result.getting_started_guide


# --------------------------------------------------------------------------
# 3. Test Guardrail: AI does NOT mutate StudyTasks
# --------------------------------------------------------------------------


def test_study_plan_explanation_does_not_mutate_study_tasks(db_session: Session) -> None:
    user = _create_user(db_session, Role.STUDENT, "no_mutate@example.com")
    profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    subject, pt, concept = _setup_curriculum(db_session, "NOM")

    plan_service = StudyPlanService(db_session)
    plan = plan_service.get_or_create_active_plan(profile.id)

    today = date.today()
    task = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.PRACTICE,
        status=StudyTaskStatus.PENDING,
        planned_date=today,
        problem_type_id=pt.id,
        concept_id=concept.id,
        estimated_duration_minutes=25,
        priority=80,
        order_index=0,
        reason_code="WEAK_PROBLEM_TYPE",
    )
    db_session.add(task)
    db_session.commit()

    # Capture initial task state
    original_task_id = task.id
    original_priority = task.priority
    original_duration = task.estimated_duration_minutes
    original_status = task.status
    original_date = task.planned_date

    explainer = StudyPlanExplanationService(db_session)
    ctx = explainer.build_context(profile.id, today)
    explanation = explainer.explain_study_plan(ctx)

    # Verify task state in database remains 100% UNCHANGED
    db_session.expire_all()
    queried_task = db_session.get(StudyTask, original_task_id)
    assert queried_task is not None
    assert queried_task.priority == original_priority
    assert queried_task.estimated_duration_minutes == original_duration
    assert queried_task.status == original_status
    assert queried_task.planned_date == original_date


# --------------------------------------------------------------------------
# 4. Test Context Gathering: weak ProblemTypes, weak Concepts, TeachingPlan
# --------------------------------------------------------------------------


def test_study_plan_explanation_build_context(db_session: Session) -> None:
    teacher = _create_user(db_session, Role.TEACHER, "teacher_ctx@example.com")
    student = _create_user(db_session, Role.STUDENT, "student_ctx@example.com")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student.id))
    teacher_profile = db_session.scalar(select(TeacherProfile).where(TeacherProfile.user_id == teacher.id))

    subject, pt, concept = _setup_curriculum(db_session, "CTX")

    # 1. Setup weak ProblemType mastery
    pt_mastery = StudentProblemTypeMastery(
        student_id=student_profile.id,
        problem_type_id=pt.id,
        mastery_score=0.35,  # Weak (< 0.50)
        confidence=0.8,
        attempt_count=5,
        correct_count=1,
        last_practiced_at=datetime.now(timezone.utc),
    )
    # 2. Setup weak Concept mastery
    c_mastery = StudentConceptMastery(
        student_id=student_profile.id,
        concept_id=concept.id,
        mastery_score=0.40,  # Weak (< 0.60)
        confidence=0.8,
        attempt_count=5,
        correct_count=2,
        last_practiced_at=datetime.now(timezone.utc),
    )
    # 3. Setup AcademicGoal
    goal = AcademicGoal(
        student_id=student_profile.id,
        target_exam="Đại Học Bách Khoa",
        target_university="Đại Học Bách Khoa",
        available_daily_minutes=60,
        exam_date=date.today() + timedelta(days=60),
        status=AcademicGoalStatus.ACTIVE,
    )
    db_session.add_all([pt_mastery, c_mastery, goal])

    # 4. Setup Classroom & Teaching Plan
    classroom = Classroom(name="12A2", academic_year="2026-2027", grade_level=12, created_by=teacher.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=teacher_profile.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(
        StudentEnrollment(
            student_id=student_profile.id,
            classroom_id=classroom.id,
            status=EnrollmentStatus.ACTIVE,
        )
    )
    t_plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        created_by=teacher.id,
        status=TeachingPlanStatus.ACTIVE,
    )
    db_session.add(t_plan)
    db_session.flush()
    db_session.add(
        TeachingPlanItem(
            teaching_plan_id=t_plan.id,
            problem_type_id=pt.id,
            order_index=0,
            priority=10,
        )
    )
    db_session.commit()

    explainer = StudyPlanExplanationService(db_session)
    ctx = explainer.build_context(student_profile.id, date.today())

    assert pt.name in ctx.weak_problem_types
    assert concept.name in ctx.relevant_weak_concepts
    assert ctx.academic_goal_title is not None
    assert "Bách Khoa" in ctx.academic_goal_title
    assert ctx.days_remaining == 60
    assert ctx.teaching_plan_context is not None
    assert pt.name in ctx.teaching_plan_context


# --------------------------------------------------------------------------
# 5. Test Empty Tasks Today: Friendly Rest Notice
# --------------------------------------------------------------------------


def test_study_plan_explanation_empty_tasks(db_session: Session) -> None:
    user = _create_user(db_session, Role.STUDENT, "empty_tasks@example.com")
    profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))

    explainer = StudyPlanExplanationService(db_session)
    ctx = explainer.build_context(profile.id, date.today())
    assert len(ctx.today_tasks) == 0

    res = explainer.explain_study_plan(ctx)
    assert res.is_fallback is False
    assert "không có nhiệm vụ" in res.concise_daily_overview


# --------------------------------------------------------------------------
# 6. Test API Endpoints
# --------------------------------------------------------------------------


def test_api_today_plan_with_explanation_flag(
    db_client: TestClient,
    db_session: Session,
    settings: Settings,
) -> None:
    user = _create_user(db_session, Role.STUDENT, "api_today_flag@example.com")
    profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    subject, pt, concept = _setup_curriculum(db_session, "APIF")

    plan_service = StudyPlanService(db_session)
    plan = plan_service.get_or_create_active_plan(profile.id)

    task = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.PRACTICE,
        status=StudyTaskStatus.PENDING,
        planned_date=date.today(),
        problem_type_id=pt.id,
        estimated_duration_minutes=20,
        priority=100,
        order_index=0,
        reason_code="CURRENT_TEACHING_PLAN",
    )
    db_session.add(task)
    db_session.commit()

    headers = _auth_headers(db_session, settings, user)

    # 1. Call GET /students/me/today: read-only, explanation is None
    res_no_exp = db_client.get("/students/me/today", headers=headers)
    assert res_no_exp.status_code == 200
    assert res_no_exp.json()["explanation"] is None

    # 2. AI generation requires explicit POST
    res_with_exp = db_client.post("/students/me/today/explanation", headers=headers)
    assert res_with_exp.status_code == 200
    data = res_with_exp.json()
    assert "concise_daily_overview" in data
    assert "priority_reasoning" in data
    assert "getting_started_guide" in data


def test_api_get_today_explanation_endpoint(
    db_client: TestClient,
    db_session: Session,
    settings: Settings,
) -> None:
    user = _create_user(db_session, Role.STUDENT, "api_exp_endpoint@example.com")
    profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    subject, pt, concept = _setup_curriculum(db_session, "APIE")

    plan_service = StudyPlanService(db_session)
    plan = plan_service.get_or_create_active_plan(profile.id)

    task = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.PRACTICE,
        status=StudyTaskStatus.PENDING,
        planned_date=date.today(),
        problem_type_id=pt.id,
        estimated_duration_minutes=25,
        priority=90,
        order_index=0,
        reason_code="CURRENT_TEACHING_PLAN",
    )
    db_session.add(task)
    db_session.commit()

    headers = _auth_headers(db_session, settings, user)

    res = db_client.post("/students/me/today/explanation", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "concise_daily_overview" in data
    assert "priority_reasoning" in data
    assert "getting_started_guide" in data
    assert "is_fallback" in data
