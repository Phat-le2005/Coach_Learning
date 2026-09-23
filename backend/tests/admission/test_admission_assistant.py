from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admission.ai_schemas import (
    AdmissionAIStructuredOutput,
    AdmissionEstimateItem,
    AdmissionFactItem,
    AdmissionRecommendationItem,
)
from app.admission.ai_service import AdmissionAssistantService
from app.admission.models import (
    AdmissionDataSource,
    AdmissionMethod,
    AdmissionRule,
    AdmissionTarget,
    AdmissionTargetType,
    Major,
    University,
)
from app.curriculum.models import Chapter, ProblemType, Topic
from app.exams.models import Exam, ExamAttempt, ExamAttemptStatus, ExamType
from app.mastery.models import StudentProblemTypeMastery
from app.students.goal_models import AcademicGoal, AcademicGoalStatus, SubjectGoal
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role, User


def _seed_student_admission_environment(
    db_session: Session, student_user: User, student_prof: StudentProfile
) -> tuple[University, Major, AdmissionMethod, AdmissionRule, AdmissionTarget]:
    # 1. Subjects & Curriculum
    s_math = Subject(code="AI_MATH", name="Toán 12", grade_level=12)
    s_phys = Subject(code="AI_PHYS", name="Vật lí 12", grade_level=12)
    db_session.add_all([s_math, s_phys])
    db_session.flush()

    chap_math = Chapter(subject_id=s_math.id, code="AI_CHP_MATH1", name="Khảo sát hàm số", order_index=1)
    db_session.add(chap_math)
    db_session.flush()

    top_math = Topic(chapter_id=chap_math.id, code="AI_TOP_MATH1", name="Cực trị hàm số", order_index=1)
    db_session.add(top_math)
    db_session.flush()

    pt_weak = ProblemType(topic_id=top_math.id, code="AI_PT_WEAK", name="Cực trị chứa tham số m", order_index=1)
    pt_strong = ProblemType(topic_id=top_math.id, code="AI_PT_STRONG", name="Đơn điệu hàm đa thức", order_index=2)
    db_session.add_all([pt_weak, pt_strong])
    db_session.flush()

    # 2. ProblemType Mastery
    m_weak = StudentProblemTypeMastery(
        student_id=student_prof.id,
        problem_type_id=pt_weak.id,
        mastery_score=0.45,
        confidence=0.8,
        attempt_count=5,
        correct_count=2,
        last_practiced_at=datetime.now(timezone.utc),
    )
    m_strong = StudentProblemTypeMastery(
        student_id=student_prof.id,
        problem_type_id=pt_strong.id,
        mastery_score=0.85,
        confidence=0.9,
        attempt_count=12,
        correct_count=10,
        last_practiced_at=datetime.now(timezone.utc),
    )
    db_session.add_all([m_weak, m_strong])

    # 3. Academic Goal
    goal = AcademicGoal(
        student_id=student_prof.id,
        target_exam="THPT Quốc Gia 2026",
        exam_date=date(2026, 6, 25),
        available_daily_minutes=180,
        status=AcademicGoalStatus.ACTIVE,
        target_university="Đại học Bách Khoa Hà Nội",
        target_major="Khoa học Máy tính",
    )
    db_session.add(goal)
    db_session.flush()

    sg_math = SubjectGoal(
        academic_goal_id=goal.id,
        subject_id=s_math.id,
        current_score=8.0,
        target_score=9.2,
        priority=1,
    )
    sg_phys = SubjectGoal(
        academic_goal_id=goal.id,
        subject_id=s_phys.id,
        current_score=7.5,
        target_score=8.8,
        priority=2,
    )
    db_session.add_all([sg_math, sg_phys])

    # 4. University, Major, Method, DataSource, Verified Rule
    univ = University(
        code="BKHN",
        name="Đại học Bách Khoa Hà Nội",
        short_name="HUST",
        region="MIEN_BAC",
    )
    db_session.add(univ)
    db_session.flush()

    major = Major(
        university_id=univ.id,
        code="IT1",
        name="Khoa học Máy tính",
    )
    method = AdmissionMethod(
        code="THPT",
        name="Xét điểm thi tốt nghiệp THPT",
    )
    ds = AdmissionDataSource(
        name="Đề án tuyển sinh ĐHBKHN 2026",
        published_year=2026,
        source_url="https://ts.hust.edu.vn",
        verified_at=datetime.now(timezone.utc),
    )
    db_session.add_all([major, method, ds])
    db_session.flush()

    rule_2025 = AdmissionRule(
        university_id=univ.id,
        major_id=major.id,
        year=2025,
        method_id=method.id,
        subject_combination="A00",
        quota=150,
        historical_score=29.42,
        requirements={"floor_score": 25.0, "math_min": 8.0},
        source_reference="Đề án Tuyển sinh 2025 ĐHBKHN, Mục 2",
        data_source_id=ds.id,
        verified_at=datetime.now(timezone.utc),
    )
    rule_2026 = AdmissionRule(
        university_id=univ.id,
        major_id=major.id,
        year=2026,
        method_id=method.id,
        subject_combination="A00",
        quota=160,
        historical_score=None,  # Not published yet
        requirements={"floor_score": 25.0},
        source_reference="Đề án Tuyển sinh 2026 ĐHBKHN, Mục 1.1",
        data_source_id=ds.id,
        verified_at=datetime.now(timezone.utc),
    )
    db_session.add_all([rule_2025, rule_2026])

    # 5. Student Admission Target (DREAM)
    target = AdmissionTarget(
        student_id=student_prof.id,
        university_id=univ.id,
        major_id=major.id,
        target_type=AdmissionTargetType.DREAM,
        target_year=2026,
        priority_order=1,
        notes="Nguyện vọng 1 mơ ước ngành IT1",
    )
    db_session.add(target)

    # 6. Recent Exam Attempt
    exam = Exam(
        subject_id=s_math.id,
        title="Đề thi thử THPT Toán số 01",
        duration_minutes=90,
        total_points=10.0,
        exam_type=ExamType.REAL_SIMULATION,
        created_by=student_user.id,
    )
    db_session.add(exam)
    db_session.flush()

    attempt = ExamAttempt(
        exam_id=exam.id,
        student_id=student_prof.id,
        status=ExamAttemptStatus.SUBMITTED,
        total_points=10.0,
        score=8.5,
        accuracy=0.85,
        duration_seconds=5000,
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(attempt)
    db_session.commit()

    return univ, major, method, rule_2026, target


# --------------------------------------------------------------------------
# 1. Compact Context Assembly Test
# --------------------------------------------------------------------------

def test_context_assembly_compact_no_mastery_graph(
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    student_user = admission_user_factory(Role.STUDENT, "student_ctx_test@example.com")
    prof = student_profile(student_user)
    univ, major, method, rule, target = _seed_student_admission_environment(db_session, student_user, prof)

    service = AdmissionAssistantService(db_session)
    ctx = service.build_admission_context(student_profile_id=prof.id)

    # 1. Verify student basic info
    assert ctx.student_grade == "Lớp 12"

    # 2. Verify Academic Goals present
    assert len(ctx.academic_goals) >= 1
    assert ctx.academic_goals[0]["target_exam"] == "THPT Quốc Gia 2026"

    # 3. Verify Admission Targets present with DREAM classification
    assert len(ctx.admission_targets) == 1
    assert ctx.admission_targets[0]["target_type"] == "DREAM"
    assert ctx.admission_targets[0]["major_code"] == "IT1"
    assert ctx.admission_targets[0]["university_code"] == "BKHN"

    # 4. Verify Verified Admission Rules present with source reference
    assert len(ctx.verified_rules) >= 1
    rule_info = next(r for r in ctx.verified_rules if r["year"] == 2025)
    assert rule_info["historical_score"] == 29.42
    assert "Đề án Tuyển sinh 2025 ĐHBKHN" in rule_info["source_reference"]

    # 5. Verify Compact Academic Context (ProblemTypes and Chapter summaries, NOT full graph)
    assert len(ctx.subject_performances) >= 1
    math_perf = next(p for p in ctx.subject_performances if "Toán" in p["subject_name"])
    assert any("Cực trị chứa tham số m" in pt for pt in math_perf["major_weak_problem_types"])
    assert any("Đơn điệu hàm đa thức" in pt for pt in math_perf["major_strong_problem_types"])
    assert "Khảo sát hàm số" in math_perf["weak_chapters"]

    # 6. Verify Recent Mock Exams
    assert len(ctx.recent_mock_exams) == 1
    assert ctx.recent_mock_exams[0]["score_10"] == 8.5

    # 7. Verify Missing Data Notices (A00 requires Math, Phys, Chem; Chem is missing!)
    assert any("Hóa Học" in notice for notice in ctx.missing_data_notices)
    assert any("2026 chưa có điểm chuẩn" in notice for notice in ctx.missing_data_notices)


# --------------------------------------------------------------------------
# 2. API Generation Success Test
# --------------------------------------------------------------------------

def test_ai_admission_assistant_generation_success(
    db_client: TestClient,
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    student_user = admission_user_factory(Role.STUDENT, "student_gen_success@example.com")
    prof = student_profile(student_user)
    _seed_student_admission_environment(db_session, student_user, prof)

    headers = admission_bearer(student_user)

    mock_ai_output = AdmissionAIStructuredOutput(
        facts=[
            AdmissionFactItem(
                institution_major="Đại học Bách Khoa Hà Nội - Khoa học Máy tính (IT1)",
                year=2025,
                method="Xét điểm thi tốt nghiệp THPT",
                subject_combination="A00",
                criteria_summary="Chỉ tiêu 150, Điểm sàn 25.0, Điểm chuẩn tham khảo 29.42",
                historical_score=29.42,
                source_reference="Đề án Tuyển sinh 2025 ĐHBKHN, Mục 2",
            ),
            AdmissionFactItem(
                institution_major="Đại học Bách Khoa Hà Nội - Khoa học Máy tính (IT1)",
                year=2026,
                method="Xét điểm thi tốt nghiệp THPT",
                subject_combination="A00",
                criteria_summary="Chỉ tiêu dự kiến 160, Điểm chuẩn chính thức: Chưa công bố",
                historical_score=None,
                source_reference="Đề án Tuyển sinh 2026 ĐHBKHN, Mục 1.1",
            ),
        ],
        estimates=[
            AdmissionEstimateItem(
                target_type="DREAM",
                institution_major="Đại học Bách Khoa Hà Nội - Khoa học Máy tính",
                subject_combination="A00",
                current_estimated_total_score=25.5,
                historical_benchmark=29.42,
                gap_analysis="Hiện tại điểm ước tính đạt khoảng 25.5/30, còn cách điểm chuẩn 2025 khoảng 3.92 điểm.",
                feasibility_assessment="Đây là mục tiêu DREAM có độ cạnh tranh rất cao, đòi hỏi nỗ lực bứt phá ở môn Toán và Lý.",
                missing_information_note="Chưa có dữ liệu bài thi môn Hóa học.",
            ),
        ],
        recommendations=[
            AdmissionRecommendationItem(
                target_focus="Môn Toán 12",
                subject_or_chapter="Chương Khảo sát hàm số",
                action_plan="Tập trung rèn luyện dạng bài 'Cực trị chứa tham số m' để nâng điểm số từ 8.0 lên 9.0+.",
                strategic_advice="Xem xét thi thêm bài thi Đánh giá tư duy (ĐGTD) của ĐHBKHN để tăng cơ hội xét tuyển sớm.",
            ),
        ],
        missing_data_summary=["Chưa có điểm kiểm tra môn Hóa học thuộc tổ hợp A00."],
        student_friendly_advice="Mục tiêu vào IT1 Bách Khoa rất thử thách nhưng em đã có nền tảng Toán 8.5 khá vững. Hãy kiên trì khắc phục các dạng bài còn hổng!",
    )

    mock_resp = MagicMock()
    mock_resp.data = mock_ai_output

    with patch("app.admission.ai_service.get_ai_gateway_singleton") as mock_gw_factory:
        mock_gateway = MagicMock()
        mock_gateway.generate_structured = AsyncMock(return_value=mock_resp)
        mock_gw_factory.return_value = mock_gateway

        res = db_client.post("/students/me/admission-assistant", headers=headers, json={})
        assert res.status_code == 200, res.text
        data = res.json()

        assert data["is_fallback"] is False
        assert len(data["facts"]) == 2
        assert len(data["estimates"]) == 1
        assert len(data["recommendations"]) == 1
        assert data["estimates"][0]["target_type"] == "DREAM"


# --------------------------------------------------------------------------
# 3. Facts Must Have Year & Source Reference Guarantee Test
# --------------------------------------------------------------------------

def test_facts_must_have_year_and_source_reference(
    db_client: TestClient,
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    student_user = admission_user_factory(Role.STUDENT, "student_facts_test@example.com")
    prof = student_profile(student_user)
    _seed_student_admission_environment(db_session, student_user, prof)

    headers = admission_bearer(student_user)

    mock_ai_output = AdmissionAIStructuredOutput(
        facts=[
            AdmissionFactItem(
                institution_major="ĐHBKHN - IT1",
                year=2026,
                method="THPT",
                subject_combination="A00",
                criteria_summary="Chỉ tiêu 160",
                historical_score=None,
                source_reference="Đề án Tuyển sinh 2026 ĐHBKHN",
            )
        ],
        estimates=[],
        recommendations=[],
        missing_data_summary=[],
        student_friendly_advice="Lời khuyên tổng quát.",
    )

    mock_resp = MagicMock()
    mock_resp.data = mock_ai_output

    with patch("app.admission.ai_service.get_ai_gateway_singleton") as mock_gw_factory:
        mock_gateway = MagicMock()
        mock_gateway.generate_structured = AsyncMock(return_value=mock_resp)
        mock_gw_factory.return_value = mock_gateway

        res = db_client.post("/students/me/admission-assistant", headers=headers, json={})
        assert res.status_code == 200
        facts = res.json()["facts"]
        assert len(facts) >= 1
        for f in facts:
            assert f["year"] >= 2000
            assert f["source_reference"] is not None
            assert len(f["source_reference"].strip()) > 0


# --------------------------------------------------------------------------
# 4. Certainty Guardrail: No 'Chắc chắn đậu'
# --------------------------------------------------------------------------

def test_certainty_guardrail_sanitizes_chac_chan_dau(
    db_client: TestClient,
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    student_user = admission_user_factory(Role.STUDENT, "student_certainty@example.com")
    prof = student_profile(student_user)
    _seed_student_admission_environment(db_session, student_user, prof)

    headers = admission_bearer(student_user)

    # Simulate AI output that violates the certainty rule
    mock_ai_output = AdmissionAIStructuredOutput(
        facts=[],
        estimates=[
            AdmissionEstimateItem(
                target_type="DREAM",
                institution_major="ĐHBKHN - IT1",
                subject_combination="A00",
                current_estimated_total_score=29.5,
                historical_benchmark=29.42,
                gap_analysis="Điểm của em cao hơn điểm chuẩn, chắc chắn đậu vào ngành này!",
                feasibility_assessment="Em chắc chắn trúng tuyển 100%, không cần lo lắng!",
            ),
        ],
        recommendations=[
            AdmissionRecommendationItem(
                target_focus="Môn Toán",
                subject_or_chapter="Hàm số",
                action_plan="Giữ phong độ hiện tại là đảm bảo 100% đậu.",
                strategic_advice="Đỗ là cái chắc rồi.",
            )
        ],
        missing_data_summary=[],
        student_friendly_advice="Chúc mừng em, bạn chắc chắn đậu đại học!",
    )

    mock_resp = MagicMock()
    mock_resp.data = mock_ai_output

    with patch("app.admission.ai_service.get_ai_gateway_singleton") as mock_gw_factory:
        mock_gateway = MagicMock()
        mock_gateway.generate_structured = AsyncMock(return_value=mock_resp)
        mock_gw_factory.return_value = mock_gateway

        res = db_client.post("/students/me/admission-assistant", headers=headers, json={})
        assert res.status_code == 200
        res_text = res.text

        # Strict check: NEVER say "chắc chắn đậu" or similar false guarantees
        assert "chắc chắn đậu" not in res_text.lower()
        assert "chắc chắn trúng tuyển" not in res_text.lower()
        assert "đảm bảo 100% đậu" not in res_text.lower()
        assert "đỗ là cái chắc" not in res_text.lower()

        # Replaced with probabilistic / objective phrasing
        data = res.json()
        assert "triển vọng cạnh tranh tốt" in data["estimates"][0]["feasibility_assessment"]
        assert "triển vọng cạnh tranh tốt" in data["student_friendly_advice"]


# --------------------------------------------------------------------------
# 5. Missing Data Transparency & Target Invariance
# --------------------------------------------------------------------------

def test_missing_data_transparency_and_target_invariance(
    db_client: TestClient,
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    student_user = admission_user_factory(Role.STUDENT, "student_missing_test@example.com")
    prof = student_profile(student_user)
    univ, major, method, rule, target = _seed_student_admission_environment(db_session, student_user, prof)

    target_id_before = target.id
    target_type_before = target.target_type

    headers = admission_bearer(student_user)

    mock_ai_output = AdmissionAIStructuredOutput(
        facts=[],
        estimates=[],
        recommendations=[],
        missing_data_summary=["Chưa có điểm thi thử môn Hóa học."],
        student_friendly_advice="Cần làm thêm bài thi môn Hóa.",
    )

    mock_resp = MagicMock()
    mock_resp.data = mock_ai_output

    with patch("app.admission.ai_service.get_ai_gateway_singleton") as mock_gw_factory:
        mock_gateway = MagicMock()
        mock_gateway.generate_structured = AsyncMock(return_value=mock_resp)
        mock_gw_factory.return_value = mock_gateway

        res = db_client.post("/students/me/admission-assistant", headers=headers, json={})
        assert res.status_code == 200
        missing = res.json()["missing_data_summary"]

        # Missing data is clearly communicated
        assert len(missing) >= 1
        assert any("Hóa" in item for item in missing)

    # Verify Target Invariance: Database target has NOT been modified or altered
    db_session.expire_all()
    target_in_db = db_session.get(AdmissionTarget, target_id_before)
    assert target_in_db is not None
    assert target_in_db.target_type == target_type_before
    assert target_in_db.target_type == AdmissionTargetType.DREAM


# --------------------------------------------------------------------------
# 6. Deterministic Fallback Test (AI Offline)
# --------------------------------------------------------------------------

def test_deterministic_fallback_when_ai_offline(
    db_client: TestClient,
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    student_user = admission_user_factory(Role.STUDENT, "student_fallback@example.com")
    prof = student_profile(student_user)
    _seed_student_admission_environment(db_session, student_user, prof)

    headers = admission_bearer(student_user)

    # Simulate AI Gateway failure
    with patch("app.admission.ai_service.get_ai_gateway_singleton") as mock_gw_factory:
        mock_gateway = MagicMock()
        mock_gateway.generate_structured = AsyncMock(side_effect=RuntimeError("AI Gateway Timeout"))
        mock_gw_factory.return_value = mock_gateway

        res = db_client.post("/students/me/admission-assistant", headers=headers, json={})
        assert res.status_code == 200, res.text
        data = res.json()

        # Fallback flag is True
        assert data["is_fallback"] is True
        # Facts derived deterministically from verified rules in DB
        assert len(data["facts"]) >= 1
        assert data["facts"][0]["source_reference"] is not None
        # Estimates generated deterministically
        assert len(data["estimates"]) >= 1
        assert data["estimates"][0]["target_type"] == "DREAM"
        # Recommendations generated deterministically from weak problem types
        assert len(data["recommendations"]) >= 1
        assert any("Cực trị chứa tham số m" in rec["action_plan"] for rec in data["recommendations"])


# --------------------------------------------------------------------------
# 7. Authorization Tests
# --------------------------------------------------------------------------

def test_admission_assistant_authorization(
    db_client: TestClient,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
) -> None:
    teacher_user = admission_user_factory(Role.TEACHER, "teacher_assistant@example.com")
    t_headers = admission_bearer(teacher_user)

    # 1. Unauthenticated -> 401
    res_anon = db_client.post("/students/me/admission-assistant", json={})
    assert res_anon.status_code == 401

    # 2. Teacher -> 403 (Only students can access /students/me/admission-assistant)
    res_teacher = db_client.post("/students/me/admission-assistant", headers=t_headers, json={})
    assert res_teacher.status_code == 403
