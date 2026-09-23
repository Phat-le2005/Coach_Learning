from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_gateway
from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.classes.copilot_schemas import (
    TeacherCopilotAIOutput,
    TeacherCopilotRead,
    TeacherCopilotRequest,
    TeacherCopilotStudentAttentionAI,
)
from app.classes.copilot_service import TeacherCopilotService
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.config import Settings, get_settings
from app.curriculum.models import Chapter, ProblemType, ProblemTypeConcept, Topic
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.misconceptions.models import (
    MisconceptionCategory,
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.planning.models import (
    TeachingPlan,
    TeachingPlanItem,
    TeachingPlanStatus,
)
from app.planning.study_models import StudyPlan, StudyPlanStatus, StudyTask, StudyTaskStatus, StudyTaskType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User


def _setup_curriculum(session: Session, prefix: str = "COP") -> tuple[Subject, Chapter, Topic, ProblemType, Concept]:
    subject = Subject(code=f"{prefix}-SUB", name=f"{prefix} Giải tích", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(subject_id=subject.id, code=f"{prefix}-CHP", name=f"{prefix} Ứng dụng đạo hàm", order_index=0)
    session.add(chapter)
    session.flush()

    topic = Topic(chapter_id=chapter.id, code=f"{prefix}-TOP", name=f"{prefix} Tính đơn điệu hàm số", order_index=0)
    session.add(topic)
    session.flush()

    pt = ProblemType(
        topic_id=topic.id,
        code=f"{prefix}-PT-PARAM",
        name="Tìm tham số về tính đơn điệu",
        order_index=0,
        is_active=True,
    )
    concept = Concept(
        subject_id=subject.id,
        code=f"{prefix}-CON-INEQ",
        name="Giải bất phương trình",
        order_index=0,
    )
    session.add_all([pt, concept])
    session.flush()

    session.add(ProblemTypeConcept(problem_type_id=pt.id, concept_id=concept.id, weight=1.0, is_primary=True))
    session.flush()
    return subject, chapter, topic, pt, concept


# --------------------------------------------------------------------------
# 1. Authorization: Only assigned teachers can consult Copilot
# --------------------------------------------------------------------------


def test_copilot_teacher_authorization_only_allows_own_classroom(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    classroom_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
) -> None:
    t1_user = classroom_user_factory(Role.TEACHER, "t1_cop_auth@example.com")
    t2_user = classroom_user_factory(Role.TEACHER, "t2_cop_auth@example.com")
    t1_prof = teacher_profile(t1_user)
    _ = teacher_profile(t2_user)

    classroom = Classroom(name="12A1 Copilot Auth", academic_year="2026-2027", grade_level=12, created_by=t1_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t1_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.commit()

    payload = {"query": "Lớp đang yếu dạng bài nào?"}

    # T2 tries to consult Copilot for T1's class -> 403 Forbidden
    t2_headers = classroom_bearer(t2_user)
    res_forbidden = db_client.post(f"/teacher/classes/{classroom.id}/copilot", json=payload, headers=t2_headers)
    assert res_forbidden.status_code == 403

    # T1 consults Copilot for own class -> 200 OK
    t1_headers = classroom_bearer(t1_user)
    res_ok = db_client.post(f"/teacher/classes/{classroom.id}/copilot", json=payload, headers=t1_headers)
    assert res_ok.status_code == 200
    data = res_ok.json()
    assert data["classroom_id"] == str(classroom.id)
    assert len(data["observations"]) > 0


# --------------------------------------------------------------------------
# 2. Query 1: 'Lớp đang yếu dạng bài nào?' (AI Success)
# --------------------------------------------------------------------------


def test_copilot_query_weak_problem_types_ai_success(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_cop_q1@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_cop_q1@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, pt_weak, _ = _setup_curriculum(db_session, "Q1")

    classroom = Classroom(name="12A2 Q1", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    # Student is weak in pt_weak (mastery 0.32 < 0.50 after 4 attempts)
    now = datetime.now(timezone.utc)
    db_session.add(
        StudentProblemTypeMastery(
            student_id=s_prof.id,
            problem_type_id=pt_weak.id,
            mastery_score=0.32,
            confidence=0.8,
            attempt_count=4,
            correct_count=1,
            last_practiced_at=now,
        )
    )
    db_session.commit()

    # Mock AI provider with structured output
    mock_provider = MockAIProvider()
    mock_provider.canned_structured = TeacherCopilotAIOutput(
        observations=[
            f"Dạng bài [{pt_weak.name}] đang có điểm thành thạo trung bình 0.32, thấp nhất lớp.",
            "Lớp học có 1 học sinh chưa đạt chuẩn ở dạng bài này sau 4 lượt làm bài.",
        ],
        priorities=[
            f"1. Ưu tiên hàng đầu: Khắc phục điểm yếu ở dạng bài [{pt_weak.name}].",
            "2. Củng cố kỹ năng đạo hàm và bất phương trình liên quan.",
        ],
        recommended_actions=[
            "Dành 15 phút đầu tiết tới hướng dẫn giải mẫu dạng bài tìm tham số theo từng bước chuẩn.",
            "Tổ chức luyện tập có giàn giáo (scaffolded practice) từ mức cơ bản.",
        ],
        students_requiring_attention=[
            TeacherCopilotStudentAttentionAI(
                student_name=s_user.full_name or "Học sinh",
                reason=f"Điểm thành thạo rất thấp ({0.32}) ở dạng bài [{pt_weak.name}]",
                suggested_focus=f"Luyện tập bài tập nhận biết và thông hiểu dạng [{pt_weak.name}]",
            )
        ],
    )
    gateway = AIGateway(provider=mock_provider, settings=get_settings())
    service = TeacherCopilotService(db_session, gateway=gateway)

    req = TeacherCopilotRequest(query="Lớp đang yếu dạng bài nào?")
    res = service.consult_copilot(t_user.id, classroom.id, req)

    assert res.is_fallback is False
    assert len(res.observations) == 2
    assert pt_weak.name in res.observations[0]
    assert len(res.priorities) == 2
    assert len(res.recommended_actions) == 2
    assert len(res.students_requiring_attention) == 1
    assert res.students_requiring_attention[0].student_id == s_prof.id
    assert res.context_summary.weak_problem_types_count >= 1


# --------------------------------------------------------------------------
# 3. Query 2: 'Học sinh nào đang yếu do kiến thức tiền đề?' (AI Success)
# --------------------------------------------------------------------------


def test_copilot_query_prerequisite_gaps_ai_success(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_cop_q2@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_cop_q2@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, pt, concept_prereq = _setup_curriculum(db_session, "Q2")

    # Second concept that depends on concept_prereq
    concept_target = Concept(subject_id=subject.id, code="Q2-CON-MONO", name="Tính đơn điệu hàm số", order_index=1)
    db_session.add(concept_target)
    db_session.flush()

    # Prerequisite relationship: ineq is prerequisite for monotonicity
    db_session.add(
        ConceptRelation(
            source_concept_id=concept_prereq.id,
            target_concept_id=concept_target.id,
            relation_type=RelationType.PREREQUISITE,
        )
    )

    classroom = Classroom(name="12A3 Q2", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    # Student has low concept mastery in prerequisite concept (0.35 < 0.50)
    now = datetime.now(timezone.utc)
    db_session.add(
        StudentConceptMastery(
            student_id=s_prof.id,
            concept_id=concept_prereq.id,
            mastery_score=0.35,
            confidence=0.85,
            attempt_count=5,
            correct_count=1,
            last_practiced_at=now,
        )
    )
    db_session.commit()

    mock_provider = MockAIProvider()
    mock_provider.canned_structured = TeacherCopilotAIOutput(
        observations=[
            f"Phát hiện học sinh {s_user.full_name} hổng khái niệm tiên quyết [{concept_prereq.name}] (điểm: 0.35).",
            f"Khái niệm [{concept_prereq.name}] là điều kiện tiên quyết bắt buộc cho [{concept_target.name}].",
        ],
        priorities=[
            f"1. Củng cố ngay khái niệm tiên quyết [{concept_prereq.name}].",
            f"2. Chưa nên nâng cao dạng bài liên quan đến [{concept_target.name}] cho học sinh này.",
        ],
        recommended_actions=[
            f"Giao phiên sửa lỗi (Repair Session) tập trung vào [{concept_prereq.name}].",
            "Hướng dẫn lại phương pháp xét dấu tam thức bậc 2 và nghiệm bất phương trình.",
        ],
        students_requiring_attention=[
            TeacherCopilotStudentAttentionAI(
                student_name=s_user.full_name or "Học sinh",
                reason=f"Hổng kiến thức tiên quyết [{concept_prereq.name}] (điểm 0.35 < 0.50)",
                suggested_focus=f"Ôn tập và làm bài tập nhận biết về [{concept_prereq.name}]",
            )
        ],
    )
    gateway = AIGateway(provider=mock_provider, settings=get_settings())
    service = TeacherCopilotService(db_session, gateway=gateway)

    req = TeacherCopilotRequest(query="Học sinh nào đang yếu do kiến thức tiền đề?")
    res = service.consult_copilot(t_user.id, classroom.id, req)

    assert res.is_fallback is False
    assert concept_prereq.name in res.observations[0]
    assert len(res.students_requiring_attention) == 1
    assert res.students_requiring_attention[0].student_id == s_prof.id
    assert res.context_summary.prerequisite_gaps_count >= 1


# --------------------------------------------------------------------------
# 4. Query 3: 'Tiết sau nên củng cố phần nào?' with TeachingPlan context
# --------------------------------------------------------------------------


def test_copilot_query_next_lesson_reinforcement(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_cop_q3@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_cop_q3@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, pt, concept = _setup_curriculum(db_session, "Q3")

    classroom = Classroom(name="12A4 Q3", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    # Active TeachingPlan
    tp = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.ACTIVE,
        created_by=t_user.id,
    )
    db_session.add(tp)
    db_session.flush()
    db_session.add(TeachingPlanItem(teaching_plan_id=tp.id, problem_type_id=pt.id, priority=10, order_index=1))

    # Misconception in classroom
    m_def = MisconceptionDefinition(
        code="Q3_MISC_01",
        concept_id=concept.id,
        problem_type_id=pt.id,
        name="Quên điều kiện hệ số a khác 0",
        description="Khi tìm tham số để tam thức bậc 2 không đổi dấu, quên xét a = 0.",
        category=MisconceptionCategory.CONCEPTUAL,
        is_active=True,
    )
    db_session.add(m_def)
    db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add(
        StudentMisconception(
            student_id=s_prof.id,
            misconception_definition_id=m_def.id,
            confidence=0.9,
            occurrence_count=2,
            status=StudentMisconceptionStatus.CONFIRMED,
            first_detected_at=now,
            last_detected_at=now,
        )
    )
    db_session.commit()

    mock_provider = MockAIProvider()
    mock_provider.canned_structured = TeacherCopilotAIOutput(
        observations=[
            f"Kế hoạch giảng dạy đang tập trung vào dạng bài [{pt.name}].",
            f"Lớp học có học sinh mắc bẫy sai lầm [{m_def.name}] đã được xác nhận (CONFIRMED).",
        ],
        priorities=[
            f"1. Nhấn mạnh việc xét trường hợp hệ số a = 0 trong bài toán tìm tham số.",
            f"2. Hoàn thiện các bài tập cơ bản của dạng bài [{pt.name}].",
        ],
        recommended_actions=[
            "Dành 10 phút khởi động bằng 1 bài toán gài bẫy trường hợp a = 0 để học sinh tự thảo luận.",
            "Yêu cầu học sinh gạch chân điều kiện của hệ số trước khi áp dụng định lý về dấu tam thức bậc 2.",
        ],
        students_requiring_attention=[
            TeacherCopilotStudentAttentionAI(
                student_name=s_user.full_name or "Học sinh",
                reason=f"Lặp lại bẫy sai lầm [{m_def.name}] 2 lần",
                suggested_focus="Kiểm tra kỹ điều kiện hệ số a khi giải phương trình/bất phương trình tham số",
            )
        ],
    )
    gateway = AIGateway(provider=mock_provider, settings=get_settings())
    service = TeacherCopilotService(db_session, gateway=gateway)

    req = TeacherCopilotRequest(query="Tiết sau nên củng cố phần nào?")
    res = service.consult_copilot(t_user.id, classroom.id, req)

    assert res.is_fallback is False
    assert res.context_summary.active_teaching_plan is not None
    assert res.context_summary.common_misconceptions_count >= 1
    assert len(res.recommended_actions) >= 1


# --------------------------------------------------------------------------
# 5. Fallback: When AI Gateway fails, return high-quality deterministic response
# --------------------------------------------------------------------------


def test_copilot_deterministic_fallback_when_ai_gateway_fails(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_cop_fb@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_cop_fb@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, pt, concept = _setup_curriculum(db_session, "FB")

    classroom = Classroom(name="12A5 Fallback", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    # Student weak in pt
    now = datetime.now(timezone.utc)
    db_session.add(
        StudentProblemTypeMastery(
            student_id=s_prof.id,
            problem_type_id=pt.id,
            mastery_score=0.28,
            confidence=0.8,
            attempt_count=4,
            correct_count=1,
            last_practiced_at=now,
        )
    )
    db_session.commit()

    # Provider that raises exception simulating offline / timeout
    mock_provider = MockAIProvider(service_unavailable_failures=10)
    gateway = AIGateway(provider=mock_provider, settings=get_settings())
    service = TeacherCopilotService(db_session, gateway=gateway)

    # Test all 3 key questions via fallback
    # 1. Weak problem types
    res1 = service.consult_copilot(t_user.id, classroom.id, TeacherCopilotRequest(query="Lớp đang yếu dạng bài nào?"))
    assert res1.is_fallback is True
    assert len(res1.observations) >= 2
    assert len(res1.priorities) >= 1
    assert len(res1.recommended_actions) >= 1
    assert len(res1.students_requiring_attention) >= 1
    assert pt.name in res1.observations[1]

    # 2. Prerequisite gaps
    res2 = service.consult_copilot(t_user.id, classroom.id, TeacherCopilotRequest(query="Học sinh nào đang yếu do kiến thức tiền đề?"))
    assert res2.is_fallback is True
    assert len(res2.observations) >= 1
    assert len(res2.priorities) >= 1

    # 3. Next lesson reinforcement
    res3 = service.consult_copilot(t_user.id, classroom.id, TeacherCopilotRequest(query="Tiết sau nên củng cố phần nào?"))
    assert res3.is_fallback is True
    assert len(res3.recommended_actions) >= 1


# --------------------------------------------------------------------------
# 6. Safety Guarantee: Copilot NEVER mutates TeachingPlan or creates StudyTasks
# --------------------------------------------------------------------------


def test_copilot_does_not_mutate_teaching_plan_or_assign_tasks(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_cop_safe@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_cop_safe@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, pt, _ = _setup_curriculum(db_session, "SAFE")

    classroom = Classroom(name="12A6 Safe", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    tp = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.ACTIVE,
        created_by=t_user.id,
    )
    db_session.add(tp)
    db_session.flush()
    db_session.add(TeachingPlanItem(teaching_plan_id=tp.id, problem_type_id=pt.id, priority=5, order_index=1))
    db_session.commit()

    # Record initial counts
    initial_tp = db_session.scalar(select(TeachingPlan).where(TeachingPlan.classroom_id == classroom.id))
    assert initial_tp is not None
    initial_tp_id = initial_tp.id
    initial_task_count = db_session.scalar(select(func.count(StudyTask.id))) or 0

    service = TeacherCopilotService(db_session)
    # Perform consultation multiple times
    for q in ["Lớp đang yếu dạng bài nào?", "Tiết sau nên củng cố phần nào?", "Giao bài tập cho học sinh"]:
        _ = service.consult_copilot(t_user.id, classroom.id, TeacherCopilotRequest(query=q))

    # Verify database state after multiple Copilot consultations
    current_tp = db_session.scalar(select(TeachingPlan).where(TeachingPlan.classroom_id == classroom.id))
    assert current_tp is not None
    assert current_tp.id == initial_tp_id
    assert current_tp.start_date == initial_tp.start_date
    assert current_tp.status == TeachingPlanStatus.ACTIVE

    current_task_count = db_session.scalar(select(func.count(StudyTask.id))) or 0
    assert current_task_count == initial_task_count


# --------------------------------------------------------------------------
# 7. Synthetic Data Filtering in Copilot
# --------------------------------------------------------------------------


def test_copilot_synthetic_filtering(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_cop_synth@example.com")
    s_real = classroom_user_factory(Role.STUDENT, "s_cop_real@example.com")
    s_synth = classroom_user_factory(Role.STUDENT, "s_cop_synth@example.com")
    t_prof = teacher_profile(t_user)
    s_real_prof = student_profile(s_real)
    s_synth_prof = student_profile(s_synth)

    # Mark second student as synthetic
    s_synth_prof.is_synthetic = True
    s_synth_prof.synthetic_profile = "WEAK"
    db_session.commit()

    classroom = Classroom(name="12A7 Synth", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add_all([
        StudentEnrollment(student_id=s_real_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE),
        StudentEnrollment(student_id=s_synth_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE),
    ])
    db_session.commit()

    service = TeacherCopilotService(db_session)

    # By default, exclude synthetic: student_count should be 1
    ctx_prod = service.build_context(t_user.id, classroom.id, "Thống kê lớp", include_synthetic=False)
    assert ctx_prod.context_summary.student_count == 1

    # When include_synthetic=True: student_count should be 2
    ctx_test = service.build_context(t_user.id, classroom.id, "Thống kê lớp", include_synthetic=True)
    assert ctx_test.context_summary.student_count == 2


# --------------------------------------------------------------------------
# 8. API Endpoint via TestClient
# --------------------------------------------------------------------------


def test_copilot_api_endpoint_via_client(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    classroom_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_cop_api@example.com")
    t_prof = teacher_profile(t_user)

    classroom = Classroom(name="12A8 API", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.commit()

    headers = classroom_bearer(t_user)
    payload = {"query": "Lớp đang yếu dạng bài nào?", "include_synthetic": False}

    response = db_client.post(f"/teacher/classes/{classroom.id}/copilot", json=payload, headers=headers)
    assert response.status_code == 200, response.text

    data = response.json()
    assert data["classroom_id"] == str(classroom.id)
    assert data["classroom_name"] == "12A8 API"
    assert data["query"] == payload["query"]
    assert isinstance(data["observations"], list)
    assert isinstance(data["priorities"], list)
    assert isinstance(data["recommended_actions"], list)
    assert isinstance(data["students_requiring_attention"], list)
    assert "context_summary" in data
    assert data["context_summary"]["student_count"] == 0
