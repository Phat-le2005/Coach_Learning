from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.types import AIMessage, AIResponse, AIRoutingTier
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, ProblemTypeConcept, Topic
from app.exams.ai_explanation_service import ExamAIExplanationService
from app.exams.ai_schemas import (
    ExamAIExplanationRead,
    ExamAIInputContext,
    ExamAIStructuredOutput,
)
from app.exams.models import (
    Exam,
    ExamAttempt,
    ExamAttemptStatus,
    ExamQuestion,
    ExamResponse,
    ExamStatus,
    ExamType,
)
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.misconceptions.models import (
    MisconceptionCategory,
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.questions.fingerprint import question_content_hash
from app.questions.models import (
    CognitiveLevel,
    Question,
    QuestionConcept,
    QuestionOption,
    QuestionProblemType,
    QuestionType,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User


def _setup_curriculum(db_session: Session, prefix: str = "AI_EXP"):
    subject = Subject(name=f"{prefix} Toán Học", code=f"{prefix}_MATH", grade_level=12)
    db_session.add(subject)
    db_session.flush()

    chapter = Chapter(subject_id=subject.id, code=f"{prefix}_CHAP1", name=f"{prefix} Khảo Sát Hàm Số", order_index=1)
    db_session.add(chapter)
    db_session.flush()

    topic = Topic(chapter_id=chapter.id, code=f"{prefix}_TOPIC1", name=f"{prefix} Cực Trị Hàm Số", order_index=1)
    db_session.add(topic)
    db_session.flush()

    pt1 = ProblemType(topic_id=topic.id, code=f"{prefix}_PT1", name=f"{prefix} Tìm Cực Trị Bậc 3", order_index=1, default_difficulty=0.3)
    pt2 = ProblemType(topic_id=topic.id, code=f"{prefix}_PT2", name=f"{prefix} Cực Trị Có Tham Số", order_index=2, default_difficulty=0.7)
    db_session.add_all([pt1, pt2])
    db_session.flush()

    c_target = Concept(subject_id=subject.id, code=f"{prefix}_CONC_TARGET", name=f"{prefix} Đạo Hàm Bậc 1", grade_level=12)
    c_prereq = Concept(subject_id=subject.id, code=f"{prefix}_CONC_PREREQ", name=f"{prefix} Dấu Tam Thức Bậc 2", grade_level=10)
    db_session.add_all([c_target, c_prereq])
    db_session.flush()

    rel = ConceptRelation(
        source_concept_id=c_prereq.id,
        target_concept_id=c_target.id,
        relation_type=RelationType.PREREQUISITE,
    )
    db_session.add(rel)
    db_session.flush()

    return subject, chapter, topic, pt1, pt2, c_target, c_prereq


def _create_question(
    db_session: Session,
    subject_id: UUID,
    author_id: UUID,
    title: str,
    qtype: QuestionType,
    difficulty: float,
    correct_ans: str,
    pt_id: UUID,
    concept_id: UUID,
) -> Question:
    q = Question(
        subject_id=subject_id,
        created_by=author_id,
        content=f"Nội dung câu hỏi: {title}",
        question_type=qtype,
        difficulty=difficulty,
        cognitive_level=CognitiveLevel.UNDERSTAND,
        correct_answer=correct_ans,
        status="APPROVED",
        source_type="CURRICULUM",
        exam_weight=1.0,
        content_hash=question_content_hash(f"Nội dung câu hỏi: {title}"),
    )
    db_session.add(q)
    db_session.flush()

    opt_a = QuestionOption(question_id=q.id, label="A", content="Đáp án A", order_index=0)
    opt_b = QuestionOption(question_id=q.id, label="B", content="Đáp án B", order_index=1)
    db_session.add_all([opt_a, opt_b])

    db_session.add(QuestionProblemType(question_id=q.id, problem_type_id=pt_id, is_primary=True))
    db_session.add(QuestionConcept(question_id=q.id, concept_id=concept_id, weight=1.0))
    db_session.commit()
    return q


# --------------------------------------------------------------------------
# 1. Context Assembly from all 6 sources
# --------------------------------------------------------------------------

def test_context_assembly_all_sources(
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_ctx_exp@example.com")
    student_user = exam_user_factory(Role.STUDENT, "s_ctx_exp@example.com")
    s_prof = student_profile(student_user)

    subject, chapter, topic, pt1, pt2, c_target, c_prereq = _setup_curriculum(db_session, "CTX")
    q1 = _create_question(db_session, subject.id, teacher.id, "Q1 Dễ", QuestionType.MULTIPLE_CHOICE, 0.2, "A", pt1.id, c_target.id)
    q2 = _create_question(db_session, subject.id, teacher.id, "Q2 Khó", QuestionType.MULTIPLE_CHOICE, 0.7, "B", pt2.id, c_prereq.id)

    # Prior Mastery
    db_session.add(
        StudentProblemTypeMastery(
            student_id=s_prof.id,
            problem_type_id=pt1.id,
            mastery_score=0.85,
            confidence=0.9,
            attempt_count=10,
            correct_count=9,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        StudentConceptMastery(
            student_id=s_prof.id,
            concept_id=c_target.id,
            mastery_score=0.80,
            confidence=0.85,
            attempt_count=8,
            correct_count=7,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )

    # Known Misconception
    misc_def = MisconceptionDefinition(
        code="MISC_CTX_01",
        name="Quên điều kiện tam thức",
        description="Bỏ qua delta > 0 khi xét cực trị",
        category=MisconceptionCategory.CONCEPTUAL,
        concept_id=c_prereq.id,
        problem_type_id=pt2.id,
    )
    db_session.add(misc_def)
    db_session.flush()

    db_session.add(
        StudentMisconception(
            student_id=s_prof.id,
            misconception_definition_id=misc_def.id,
            status=StudentMisconceptionStatus.CONFIRMED,
            confidence=0.88,
            occurrence_count=3,
            first_detected_at=datetime.now(timezone.utc) - timedelta(days=5),
            last_detected_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )

    # Exam
    exam = Exam(
        subject_id=subject.id,
        title="Đề Thi Chẩn Đoán AI",
        duration_minutes=30,
        exam_type=ExamType.REAL_SIMULATION,
        status=ExamStatus.PUBLISHED,
        created_by=teacher.id,
        total_questions=2,
        total_points=10.0,
    )
    db_session.add(exam)
    db_session.flush()
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q1.id, order_index=0, points=5.0))
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q2.id, order_index=1, points=5.0))

    attempt = ExamAttempt(
        exam_id=exam.id,
        student_id=s_prof.id,
        status=ExamAttemptStatus.SUBMITTED,
        total_points=10.0,
        score=5.0,
        accuracy=0.5,
        duration_seconds=90,
    )
    db_session.add(attempt)
    db_session.flush()

    # Q1: student answered "B" (wrong), took 10s -> careless condition met! (difficulty=0.2, time=10s, prior=0.85)
    db_session.add(
        ExamResponse(
            attempt_id=attempt.id,
            question_id=q1.id,
            student_answer="B",
            is_correct=False,
            score_awarded=0.0,
            response_time_seconds=10.0,
            order_answered=1,
        )
    )
    # Q2: student answered "B" (correct), took 80s
    db_session.add(
        ExamResponse(
            attempt_id=attempt.id,
            question_id=q2.id,
            student_answer="B",
            is_correct=True,
            score_awarded=5.0,
            response_time_seconds=80.0,
            order_answered=2,
        )
    )
    db_session.commit()

    service = ExamAIExplanationService(db_session)
    ctx = service.build_explanation_context(attempt.id)

    assert ctx.attempt_id == attempt.id
    assert ctx.exam_title == "Đề Thi Chẩn Đoán AI"
    assert ctx.score == 5.0
    assert ctx.score_10 == 5.0
    assert ctx.total_questions == 2
    assert ctx.correct_count == 1
    assert ctx.incorrect_count == 1
    # Check prior mastery
    assert len(ctx.prior_problem_type_mastery) == 1
    assert ctx.prior_problem_type_mastery[0]["mastery_score"] == 0.85
    # Check known misconceptions
    assert len(ctx.known_misconceptions) == 1
    assert ctx.known_misconceptions[0]["code"] == "MISC_CTX_01"
    # Check careless evidence is True because Q1 was diff < 0.35, time < 15s, prior >= 0.70
    assert ctx.has_strong_careless_evidence is True
    # Check curriculum node validation set contains real nodes
    assert chapter.name in ctx.valid_curriculum_nodes
    assert pt1.name in ctx.valid_curriculum_nodes


# --------------------------------------------------------------------------
# 2. End-to-End AI Explanation API Generation
# --------------------------------------------------------------------------

def test_ai_explanation_generation_success(
    db_client: TestClient,
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    exam_bearer: Callable[[User], dict[str, str]],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_ai_gen@example.com")
    student_user = exam_user_factory(Role.STUDENT, "s_ai_gen@example.com")
    s_prof = student_profile(student_user)

    subject, chapter, topic, pt1, _, c_target, _ = _setup_curriculum(db_session, "GEN")
    q1 = _create_question(db_session, subject.id, teacher.id, "Q1 Gen", QuestionType.MULTIPLE_CHOICE, 0.4, "A", pt1.id, c_target.id)

    exam = Exam(
        subject_id=subject.id,
        title="Đề Thi Thử Tốt Nghiệp",
        duration_minutes=45,
        exam_type=ExamType.REAL_SIMULATION,
        status=ExamStatus.PUBLISHED,
        created_by=teacher.id,
        total_questions=1,
        total_points=10.0,
    )
    db_session.add(exam)
    db_session.flush()
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q1.id, order_index=0, points=10.0))

    attempt = ExamAttempt(
        exam_id=exam.id,
        student_id=s_prof.id,
        status=ExamAttemptStatus.SUBMITTED,
        total_points=10.0,
        score=10.0,
        accuracy=1.0,
        duration_seconds=120,
    )
    db_session.add(attempt)
    db_session.flush()
    db_session.add(
        ExamResponse(
            attempt_id=attempt.id,
            question_id=q1.id,
            student_answer="A",
            is_correct=True,
            score_awarded=10.0,
            response_time_seconds=120.0,
            order_answered=1,
        )
    )
    db_session.commit()

    headers = exam_bearer(student_user)

    mock_ai_output = ExamAIStructuredOutput(
        strengths=["Làm chủ rất tốt dạng bài Tìm Cực Trị Bậc 3."],
        weak_problem_types=[],
        possible_prerequisite_weaknesses=[],
        recurring_errors=[],
        possible_time_management_issue="Phân bổ thời gian 120s cho câu hỏi là hợp lý.",
        review_priorities=["Tiếp tục duy trì tốc độ và làm thêm các bài toán vận dụng cao."],
        exam_strategy_suggestions=["Kiểm tra lại kết quả trước khi chuyển câu."],
        student_friendly_summary="Em đã hoàn thành xuất sắc bài thi với điểm số tuyệt đối 10/10!",
    )

    # Patch gateway generate_structured to return mock response
    mock_resp = MagicMock()
    mock_resp.data = mock_ai_output

    with patch("app.exams.ai_explanation_service.get_ai_gateway_singleton") as mock_gw_factory:
        mock_gateway = MagicMock()
        mock_gateway.generate_structured = AsyncMock(return_value=mock_resp)
        mock_gw_factory.return_value = mock_gateway

        res = db_client.post(f"/exams/attempts/{attempt.id}/ai-explanation", headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert data["attempt_id"] == str(attempt.id)
        assert data["score"] == 10.0
        assert data["score_10"] == 10.0
        assert len(data["strengths"]) >= 1
        assert "Tìm Cực Trị Bậc 3" in data["strengths"][0]
        assert data["is_fallback"] is False
        assert "xuất sắc" in data["student_friendly_summary"]


# --------------------------------------------------------------------------
# 3. Score Immutability Guardrail
# --------------------------------------------------------------------------

def test_score_immutability_guardrail(
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_immut@example.com")
    student_user = exam_user_factory(Role.STUDENT, "s_immut@example.com")
    s_prof = student_profile(student_user)

    subject, _, _, pt1, _, c_target, _ = _setup_curriculum(db_session, "IMM")
    q1 = _create_question(db_session, subject.id, teacher.id, "Q1 Immut", QuestionType.MULTIPLE_CHOICE, 0.5, "A", pt1.id, c_target.id)

    exam = Exam(
        subject_id=subject.id,
        title="Đề Thi Immutability",
        duration_minutes=30,
        exam_type=ExamType.REAL_SIMULATION,
        status=ExamStatus.PUBLISHED,
        created_by=teacher.id,
        total_questions=1,
        total_points=10.0,
    )
    db_session.add(exam)
    db_session.flush()
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q1.id, order_index=0, points=10.0))

    attempt = ExamAttempt(
        exam_id=exam.id,
        student_id=s_prof.id,
        status=ExamAttemptStatus.SUBMITTED,
        total_points=10.0,
        score=7.0,
        accuracy=0.7,
        duration_seconds=60,
    )
    db_session.add(attempt)
    db_session.flush()
    db_session.add(
        ExamResponse(
            attempt_id=attempt.id,
            question_id=q1.id,
            student_answer="A",
            is_correct=True,
            score_awarded=7.0,
            response_time_seconds=60.0,
            order_answered=1,
        )
    )
    db_session.commit()

    service = ExamAIExplanationService(db_session)
    # Generate explanation (mocking AI or via fallback)
    exp = service.generate_explanation(attempt.id, student_user.id)

    # Score MUST remain exactly 7.0 (and 7.0/10.0), never altered
    assert exp.score == 7.0
    assert exp.score_10 == 7.0


# --------------------------------------------------------------------------
# 4. Careless Accusation Guardrail Enforcement
# --------------------------------------------------------------------------

def test_careless_guardrail_sanitizes_weak_evidence(
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_careless@example.com")
    student_user = exam_user_factory(Role.STUDENT, "s_careless@example.com")
    s_prof = student_profile(student_user)

    subject, _, _, pt1, _, c_target, _ = _setup_curriculum(db_session, "CAR")
    # Hard question (diff=0.8), took 90s -> NOT careless!
    q1 = _create_question(db_session, subject.id, teacher.id, "Q1 Hard", QuestionType.MULTIPLE_CHOICE, 0.8, "A", pt1.id, c_target.id)

    exam = Exam(
        subject_id=subject.id,
        title="Đề Thi Kiểm Tra Careless",
        duration_minutes=30,
        exam_type=ExamType.REAL_SIMULATION,
        status=ExamStatus.PUBLISHED,
        created_by=teacher.id,
        total_questions=1,
        total_points=10.0,
    )
    db_session.add(exam)
    db_session.flush()
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q1.id, order_index=0, points=10.0))

    attempt = ExamAttempt(
        exam_id=exam.id,
        student_id=s_prof.id,
        status=ExamAttemptStatus.SUBMITTED,
        total_points=10.0,
        score=0.0,
        accuracy=0.0,
        duration_seconds=90,
    )
    db_session.add(attempt)
    db_session.flush()
    db_session.add(
        ExamResponse(
            attempt_id=attempt.id,
            question_id=q1.id,
            student_answer="B",
            is_correct=False,
            score_awarded=0.0,
            response_time_seconds=90.0,
            order_answered=1,
        )
    )
    db_session.commit()

    # Suppose AI LLM improperly outputs accusatory text
    mock_ai_output = ExamAIStructuredOutput(
        strengths=["Có cố gắng làm bài."],
        weak_problem_types=["Học sinh rất ẩu khi làm dạng bài này."],
        possible_prerequisite_weaknesses=[],
        recurring_errors=["Do bất cẩn nên chọn nhầm."],
        possible_time_management_issue="Quá ẩu tả trong khâu tính toán.",
        review_priorities=["Học lại lý thuyết."],
        exam_strategy_suggestions=["Tập trung hơn."],
        student_friendly_summary="Em bị điểm kém vì quá bất cẩn và thiếu tập trung.",
    )

    mock_gateway = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = mock_ai_output
    mock_gateway.generate_structured = AsyncMock(return_value=mock_resp)

    service = ExamAIExplanationService(db_session, gateway=mock_gateway)
    exp = service.generate_explanation(attempt.id, student_user.id)

    # Since has_strong_careless_evidence is False, guardrail MUST sanitize accusatory words
    assert exp.has_strong_careless_evidence is False
    assert "bất cẩn" not in exp.student_friendly_summary
    assert "thiếu tập trung" not in exp.student_friendly_summary
    assert "ẩu tả" not in exp.possible_time_management_issue


# --------------------------------------------------------------------------
# 5. Teacher and Student Authorization Rules
# --------------------------------------------------------------------------

def test_teacher_and_student_authorization_rules(
    db_client: TestClient,
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    exam_bearer: Callable[[User], dict[str, str]],
    student_profile: Callable[[User], StudentProfile],
    teacher_profile: Callable[[User], TeacherProfile],
) -> None:
    t_enrolled = exam_user_factory(Role.TEACHER, "t_enrolled@example.com")
    t_enrolled_prof = teacher_profile(t_enrolled)

    t_stranger = exam_user_factory(Role.TEACHER, "t_stranger@example.com")
    _ = teacher_profile(t_stranger)

    s_owner = exam_user_factory(Role.STUDENT, "s_owner@example.com")
    s_owner_prof = student_profile(s_owner)

    s_stranger = exam_user_factory(Role.STUDENT, "s_stranger@example.com")
    _ = student_profile(s_stranger)

    # Create Classroom and enroll s_owner with t_enrolled
    classroom = Classroom(
        name="Lớp 12A1 Ôn Thi",
        academic_year="2025-2026",
        grade_level=12,
        created_by=t_enrolled.id,
    )
    db_session.add(classroom)
    db_session.flush()

    db_session.add(
        TeacherClassroom(
            teacher_id=t_enrolled_prof.id,
            classroom_id=classroom.id,
            role="TEACHER",
        )
    )
    db_session.add(
        StudentEnrollment(
            student_id=s_owner_prof.id,
            classroom_id=classroom.id,
            status=EnrollmentStatus.ACTIVE,
        )
    )

    subject, _, _, pt1, _, c_target, _ = _setup_curriculum(db_session, "AUTH")
    q1 = _create_question(db_session, subject.id, t_enrolled.id, "Q1 Auth", QuestionType.MULTIPLE_CHOICE, 0.5, "A", pt1.id, c_target.id)

    exam = Exam(
        subject_id=subject.id,
        title="Đề Thi Authorization",
        duration_minutes=30,
        exam_type=ExamType.REAL_SIMULATION,
        status=ExamStatus.PUBLISHED,
        created_by=t_enrolled.id,
        total_questions=1,
        total_points=10.0,
    )
    db_session.add(exam)
    db_session.flush()
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q1.id, order_index=0, points=10.0))

    attempt = ExamAttempt(
        exam_id=exam.id,
        student_id=s_owner_prof.id,
        status=ExamAttemptStatus.SUBMITTED,
        total_points=10.0,
        score=10.0,
        accuracy=1.0,
        duration_seconds=50,
    )
    db_session.add(attempt)
    db_session.flush()
    db_session.add(
        ExamResponse(
            attempt_id=attempt.id,
            question_id=q1.id,
            student_answer="A",
            is_correct=True,
            score_awarded=10.0,
            response_time_seconds=50.0,
            order_answered=1,
        )
    )
    db_session.commit()

    # 1. Student owner -> 200 OK
    h_owner = exam_bearer(s_owner)
    res1 = db_client.post(f"/exams/attempts/{attempt.id}/ai-explanation", headers=h_owner)
    assert res1.status_code == 200

    # 2. Other student -> 404 Not Found (privacy guard: hide attempt existence)
    h_s_stranger = exam_bearer(s_stranger)
    res2 = db_client.post(f"/exams/attempts/{attempt.id}/ai-explanation", headers=h_s_stranger)
    assert res2.status_code == 404

    # 3. Enrolled teacher -> 200 OK
    h_t_enrolled = exam_bearer(t_enrolled)
    res3 = db_client.post(f"/exams/attempts/{attempt.id}/ai-explanation", headers=h_t_enrolled)
    assert res3.status_code == 200

    # 4. Stranger teacher (not teaching this student) -> 403 Forbidden
    h_t_stranger = exam_bearer(t_stranger)
    res4 = db_client.post(f"/exams/attempts/{attempt.id}/ai-explanation", headers=h_t_stranger)
    assert res4.status_code == 403


# --------------------------------------------------------------------------
# 6. AI Unavailable Fallback
# --------------------------------------------------------------------------

def test_ai_unavailable_deterministic_fallback(
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_fb@example.com")
    student_user = exam_user_factory(Role.STUDENT, "s_fb@example.com")
    s_prof = student_profile(student_user)

    subject, _, _, pt1, _, c_target, _ = _setup_curriculum(db_session, "FB")
    q1 = _create_question(db_session, subject.id, teacher.id, "Q1 Fallback", QuestionType.MULTIPLE_CHOICE, 0.4, "A", pt1.id, c_target.id)

    exam = Exam(
        subject_id=subject.id,
        title="Đề Thi Fallback Test",
        duration_minutes=30,
        exam_type=ExamType.REAL_SIMULATION,
        status=ExamStatus.PUBLISHED,
        created_by=teacher.id,
        total_questions=1,
        total_points=10.0,
    )
    db_session.add(exam)
    db_session.flush()
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q1.id, order_index=0, points=10.0))

    attempt = ExamAttempt(
        exam_id=exam.id,
        student_id=s_prof.id,
        status=ExamAttemptStatus.SUBMITTED,
        total_points=10.0,
        score=0.0,
        accuracy=0.0,
        duration_seconds=75,
    )
    db_session.add(attempt)
    db_session.flush()
    db_session.add(
        ExamResponse(
            attempt_id=attempt.id,
            question_id=q1.id,
            student_answer="B",
            is_correct=False,
            score_awarded=0.0,
            response_time_seconds=75.0,
            order_answered=1,
        )
    )
    db_session.commit()

    # Simulate Gateway Exception / Network error
    mock_failing_gateway = MagicMock()
    mock_failing_gateway.generate_structured = AsyncMock(side_effect=RuntimeError("AI Provider 503 Service Unavailable"))

    service = ExamAIExplanationService(db_session, gateway=mock_failing_gateway)
    exp = service.generate_explanation(attempt.id, student_user.id)

    # Fallback guarantees:
    assert exp.is_fallback is True
    assert exp.score == 0.0
    assert len(exp.weak_problem_types) >= 1
    assert len(exp.review_priorities) >= 1
    assert len(exp.exam_strategy_suggestions) >= 1
    assert "Đề Thi Fallback Test" in exp.student_friendly_summary
