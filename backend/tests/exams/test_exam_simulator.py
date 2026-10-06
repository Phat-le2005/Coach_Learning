from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, ProblemTypeConcept, Topic
from app.exams.analytics_service import ExamAnalyticsService
from app.exams.blueprint_service import ExamBlueprintService
from app.exams.models import (
    Exam,
    ExamAttempt,
    ExamAttemptStatus,
    ExamQuestion,
    ExamResponse,
    ExamSection,
    ExamStatus,
    ExamType,
)
from app.exams.schemas import (
    ExamBlueprintConfig,
    ExamBlueprintRule,
    ExamCreate,
    ExamResponseSubmitRequest,
    ExamSectionCreate,
)
from app.exams.scoring_service import ExamScoringService
from app.exams.simulation_service import ExamSimulationService
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.questions.fingerprint import question_content_hash
from app.questions.models import (
    CognitiveLevel,
    Question,
    QuestionConcept,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User


def _setup_curriculum(
    session: Session, prefix: str = "EXM"
) -> tuple[Subject, Chapter, Topic, ProblemType, ProblemType, Concept, Concept]:
    subject = Subject(code=f"{prefix}-MATH", name=f"{prefix} Toán 12", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(subject_id=subject.id, code=f"{prefix}-CHP1", name=f"{prefix} Khảo sát hàm số", order_index=0)
    session.add(chapter)
    session.flush()

    topic = Topic(chapter_id=chapter.id, code=f"{prefix}-TOP1", name=f"{prefix} Tính đơn điệu", order_index=0)
    session.add(topic)
    session.flush()

    pt1 = ProblemType(
        topic_id=topic.id,
        code=f"{prefix}-PT-PARAM",
        name="Tìm tham số về tính đơn điệu",
        order_index=0,
        is_active=True,
    )
    pt2 = ProblemType(
        topic_id=topic.id,
        code=f"{prefix}-PT-INTERVAL",
        name="Xét tính đơn điệu trên khoảng",
        order_index=1,
        is_active=True,
    )

    c_target = Concept(
        subject_id=subject.id,
        code=f"{prefix}-CON-INEQ",
        name="Giải bất phương trình",
        order_index=0,
    )
    c_prereq = Concept(
        subject_id=subject.id,
        code=f"{prefix}-CON-DERIV",
        name="Quy tắc đạo hàm",
        order_index=1,
    )
    session.add_all([pt1, pt2, c_target, c_prereq])
    session.flush()

    # Target concept depends on prerequisite concept
    session.add(ConceptRelation(source_concept_id=c_prereq.id, target_concept_id=c_target.id, relation_type=RelationType.PREREQUISITE))
    session.add(ProblemTypeConcept(problem_type_id=pt1.id, concept_id=c_target.id, weight=1.0, is_primary=True))
    session.add(ProblemTypeConcept(problem_type_id=pt2.id, concept_id=c_prereq.id, weight=1.0, is_primary=True))
    session.flush()

    return subject, chapter, topic, pt1, pt2, c_target, c_prereq


def _create_question(
    session: Session,
    subject_id: UUID,
    creator_id: UUID,
    content: str,
    q_type: QuestionType,
    difficulty: float,
    correct_answer: str,
    problem_type_id: UUID,
    concept_id: UUID,
    status: QuestionStatus = QuestionStatus.APPROVED,
) -> Question:
    q = Question(
        subject_id=subject_id,
        content=content,
        content_hash=question_content_hash(content),
        question_type=q_type,
        difficulty=difficulty,
        correct_answer=correct_answer,
        explanation=f"Giải thích cho {content}",
        source_type="CURRICULUM",
        exam_weight=1.0,
        status=status,
        created_by=creator_id,
    )
    session.add(q)
    session.flush()

    if q_type == QuestionType.MULTIPLE_CHOICE:
        for idx, label in enumerate(["A", "B", "C", "D"]):
            session.add(
                QuestionOption(
                    question_id=q.id,
                    label=label,
                    content=f"Phương án {label} của {content}",
                    order_index=idx,
                )
            )
    elif q_type == QuestionType.TRUE_FALSE:
        session.add(QuestionOption(question_id=q.id, label="Đúng", content="Khẳng định đúng", order_index=0))
        session.add(QuestionOption(question_id=q.id, label="Sai", content="Khẳng định sai", order_index=1))

    session.add(QuestionProblemType(question_id=q.id, problem_type_id=problem_type_id, weight=1.0, is_primary=True))
    session.add(QuestionConcept(question_id=q.id, concept_id=concept_id, weight=1.0))
    session.flush()
    return q


# --------------------------------------------------------------------------
# 1. Exam Blueprint & Section Assembly (Data-driven, Not hardcoded)
# --------------------------------------------------------------------------

def test_exam_blueprint_assembly(
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_bp@example.com")
    subject, chapter, topic, pt1, pt2, c_target, c_prereq = _setup_curriculum(db_session, "BP")

    # Create approved questions for pt1 and pt2
    q1 = _create_question(db_session, subject.id, teacher.id, "Câu 1: Tham số m để đồng biến", QuestionType.MULTIPLE_CHOICE, 0.3, "A", pt1.id, c_target.id)
    q2 = _create_question(db_session, subject.id, teacher.id, "Câu 2: Tham số m để nghịch biến", QuestionType.MULTIPLE_CHOICE, 0.5, "B", pt1.id, c_target.id)
    q3 = _create_question(db_session, subject.id, teacher.id, "Câu 3: Xét tính đơn điệu câu đúng sai", QuestionType.TRUE_FALSE, 0.4, "Đúng", pt2.id, c_prereq.id)
    q4 = _create_question(db_session, subject.id, teacher.id, "Câu 4: Giá trị m nhỏ nhất là số nguyên", QuestionType.SHORT_ANSWER, 0.8, "5", pt1.id, c_target.id)

    # 1. Create Exam
    exam = Exam(
        subject_id=subject.id,
        title="Đề thi thử Tốt nghiệp THPT Chuẩn hóa 2026",
        duration_minutes=90,
        exam_type=ExamType.REAL_SIMULATION,
        total_points=10.0,
        created_by=teacher.id,
        blueprint_config={
            "rules": [
                {"problem_type_id": str(pt1.id), "question_type": "MULTIPLE_CHOICE", "count": 2, "points_per_question": 2.5},
                {"problem_type_id": str(pt2.id), "question_type": "TRUE_FALSE", "count": 1, "points_per_question": 2.5},
                {"problem_type_id": str(pt1.id), "question_type": "SHORT_ANSWER", "count": 1, "points_per_question": 2.5},
            ]
        },
    )
    db_session.add(exam)
    db_session.flush()

    # 2. Assemble questions from blueprint
    bp_service = ExamBlueprintService(db_session)
    assembled = bp_service.assemble_exam_questions(exam.id)
    db_session.commit()

    assert len(assembled) == 4
    assert exam.total_questions == 4
    assert exam.total_points == 10.0

    # Verify no duplicates
    q_ids = [eq.question_id for eq in assembled]
    assert len(set(q_ids)) == 4
    assert q1.id in q_ids
    assert q2.id in q_ids
    assert q3.id in q_ids
    assert q4.id in q_ids


# --------------------------------------------------------------------------
# 2. Student Simulation Flow (Start -> Answer -> Submit -> Graded)
# --------------------------------------------------------------------------

def test_student_simulation_flow(
    db_client: TestClient,
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    exam_bearer: Callable[[User], dict[str, str]],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_flow@example.com")
    student_user = exam_user_factory(Role.STUDENT, "s_flow@example.com")
    s_prof = student_profile(student_user)

    subject, chapter, topic, pt1, pt2, c_target, c_prereq = _setup_curriculum(db_session, "FLW")

    q1 = _create_question(db_session, subject.id, teacher.id, "Câu 1: FLW MC", QuestionType.MULTIPLE_CHOICE, 0.25, "A", pt1.id, c_target.id)
    q2 = _create_question(db_session, subject.id, teacher.id, "Câu 2: FLW TF", QuestionType.TRUE_FALSE, 0.45, "Đúng", pt2.id, c_prereq.id)
    q3 = _create_question(db_session, subject.id, teacher.id, "Câu 3: FLW SA", QuestionType.SHORT_ANSWER, 0.75, "12.5", pt1.id, c_target.id)

    exam = Exam(
        subject_id=subject.id,
        title="Đề kiểm tra thực chiến",
        duration_minutes=60,
        exam_type=ExamType.REAL_SIMULATION,
        status=ExamStatus.PUBLISHED,
        created_by=teacher.id,
        total_points=10.0,
        total_questions=3,
    )
    db_session.add(exam)
    db_session.flush()

    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q1.id, order_index=0, points=3.0))
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q2.id, order_index=1, points=3.0))
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q3.id, order_index=2, points=4.0))
    db_session.commit()

    headers = exam_bearer(student_user)

    # 1. Start exam
    res_start = db_client.post(f"/exams/{exam.id}/start", headers=headers)
    assert res_start.status_code == 200
    data_start = res_start.json()
    attempt_id = data_start["attempt_id"]
    assert data_start["total_questions"] == 3
    assert data_start["time_remaining_seconds"] > 0

    # Ensure questions are sanitized (no answers exposed)
    for q_san in data_start["questions"]:
        assert "correct_answer" not in q_san
        assert "explanation" not in q_san

    # 2. Answer Question 1 (Correct)
    res_ans1 = db_client.post(
        f"/exams/attempts/{attempt_id}/answer",
        json={"question_id": str(q1.id), "student_answer": "A", "response_time_seconds": 45.0},
        headers=headers,
    )
    assert res_ans1.status_code == 200
    assert res_ans1.json()["order_answered"] == 1

    # 3. Answer Question 3 (Skipping Q2 first - testing order behavior)
    res_ans3 = db_client.post(
        f"/exams/attempts/{attempt_id}/answer",
        json={"question_id": str(q3.id), "student_answer": "12.50", "response_time_seconds": 60.0},
        headers=headers,
    )
    assert res_ans3.status_code == 200
    assert res_ans3.json()["order_answered"] == 2

    # 4. Answer Question 2 (Wrong answer: "Sai" instead of "Đúng")
    res_ans2 = db_client.post(
        f"/exams/attempts/{attempt_id}/answer",
        json={"question_id": str(q2.id), "student_answer": "Sai", "response_time_seconds": 30.0},
        headers=headers,
    )
    assert res_ans2.status_code == 200
    assert res_ans2.json()["order_answered"] == 3

    # 5. Check attempt status
    res_check = db_client.get(f"/exams/attempts/{attempt_id}", headers=headers)
    assert res_check.status_code == 200
    assert res_check.json()["answered_count"] == 3

    # 6. Submit exam
    res_sub = db_client.post(f"/exams/attempts/{attempt_id}/submit", headers=headers)
    assert res_sub.status_code == 200
    data_sub = res_sub.json()
    assert data_sub["status"] == "GRADED"
    # Q1 correct (3.0), Q3 correct (4.0), Q2 wrong (0.0) -> Score = 7.0 / 10.0
    assert data_sub["score"] == 7.0
    assert data_sub["total_points"] == 10.0
    assert data_sub["accuracy"] == round(2 / 3, 4)
    assert data_sub["score_10"] == 7.0


# --------------------------------------------------------------------------
# 3. REAL_SIMULATION Guardrails: No Hints and No Tutor Allowed
# --------------------------------------------------------------------------

def test_real_simulation_guardrails_no_hints_no_tutor(
    db_client: TestClient,
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    exam_bearer: Callable[[User], dict[str, str]],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_guard@example.com")
    student_user = exam_user_factory(Role.STUDENT, "s_guard@example.com")
    s_prof = student_profile(student_user)

    subject, _, _, pt1, _, c_target, _ = _setup_curriculum(db_session, "GUA")
    q1 = _create_question(db_session, subject.id, teacher.id, "Câu 1 Guard", QuestionType.MULTIPLE_CHOICE, 0.3, "A", pt1.id, c_target.id)

    exam = Exam(
        subject_id=subject.id,
        title="Đề thi Real Simulation Chặn Hint & Tutor",
        duration_minutes=45,
        exam_type=ExamType.REAL_SIMULATION,
        status=ExamStatus.PUBLISHED,
        created_by=teacher.id,
        total_questions=1,
    )
    db_session.add(exam)
    db_session.flush()
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q1.id, order_index=0, points=10.0))
    db_session.commit()

    headers = exam_bearer(student_user)

    # Start simulation
    res_start = db_client.post(f"/exams/{exam.id}/start", headers=headers)
    attempt_id = res_start.json()["attempt_id"]

    # 1. Attempt to request a hint -> 403 Forbidden
    res_hint = db_client.get(f"/exams/attempts/{attempt_id}/hint", headers=headers)
    assert res_hint.status_code == 403
    assert res_hint.json()["error"]["code"] == "HINTS_NOT_ALLOWED_IN_REAL_SIMULATION"

    # 2. Service level assertion for tutor
    sim_service = ExamSimulationService(db_session)
    with pytest.raises(ApplicationError) as exc_tutor:
        sim_service.assert_tutor_allowed(UUID(attempt_id))
    assert exc_tutor.value.code == "TUTOR_NOT_ALLOWED_IN_REAL_SIMULATION"


# --------------------------------------------------------------------------
# 4. Timer Expiration and Auto-Submit
# --------------------------------------------------------------------------

def test_exam_timer_expiration_auto_submit(
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_timer@example.com")
    student_user = exam_user_factory(Role.STUDENT, "s_timer@example.com")
    s_prof = student_profile(student_user)

    subject, _, _, pt1, _, c_target, _ = _setup_curriculum(db_session, "TMR")
    q1 = _create_question(db_session, subject.id, teacher.id, "Câu 1 Timer", QuestionType.MULTIPLE_CHOICE, 0.3, "B", pt1.id, c_target.id)

    exam = Exam(
        subject_id=subject.id,
        title="Đề thi đếm giờ",
        duration_minutes=30,
        exam_type=ExamType.REAL_SIMULATION,
        status=ExamStatus.PUBLISHED,
        created_by=teacher.id,
        total_questions=1,
    )
    db_session.add(exam)
    db_session.flush()
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q1.id, order_index=0, points=10.0))
    db_session.commit()

    sim_service = ExamSimulationService(db_session)
    start_info = sim_service.start_exam(student_user.id, exam.id)
    attempt_id = start_info.attempt_id

    # Manipulate started_at to be 40 minutes in the past (> 30 min duration)
    past_time = datetime.now(timezone.utc) - timedelta(minutes=40)
    attempt = db_session.get(ExamAttempt, attempt_id)
    assert attempt is not None
    attempt.started_at = past_time
    db_session.commit()

    # Calling get_attempt_status detects expiration and auto-submits
    status_read = sim_service.get_attempt_status(student_user.id, attempt_id)
    assert status_read.time_remaining_seconds == 0
    assert status_read.status == ExamAttemptStatus.TIMED_OUT


# --------------------------------------------------------------------------
# 5. Deterministic Scoring Service (Zero LLM, Numeric Tolerance)
# --------------------------------------------------------------------------

def test_exam_scoring_service_deterministic(
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_score@example.com")
    student_user = exam_user_factory(Role.STUDENT, "s_score@example.com")
    s_prof = student_profile(student_user)

    subject, _, _, pt1, pt2, c_target, c_prereq = _setup_curriculum(db_session, "SCR")

    q_mc = _create_question(db_session, subject.id, teacher.id, "MC Q", QuestionType.MULTIPLE_CHOICE, 0.3, "C", pt1.id, c_target.id)
    q_tf = _create_question(db_session, subject.id, teacher.id, "TF Q", QuestionType.TRUE_FALSE, 0.4, "Sai", pt2.id, c_prereq.id)
    q_sa_num = _create_question(db_session, subject.id, teacher.id, "SA Num Q", QuestionType.SHORT_ANSWER, 0.6, "3.1415", pt1.id, c_target.id)
    q_unans = _create_question(db_session, subject.id, teacher.id, "Unanswered Q", QuestionType.MULTIPLE_CHOICE, 0.7, "D", pt2.id, c_prereq.id)

    exam = Exam(
        subject_id=subject.id,
        title="Scoring Test Exam",
        duration_minutes=60,
        exam_type=ExamType.REAL_SIMULATION,
        status=ExamStatus.PUBLISHED,
        created_by=teacher.id,
        total_questions=4,
        total_points=10.0,
    )
    db_session.add(exam)
    db_session.flush()
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q_mc.id, order_index=0, points=2.5))
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q_tf.id, order_index=1, points=2.5))
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q_sa_num.id, order_index=2, points=2.5))
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q_unans.id, order_index=3, points=2.5))

    attempt = ExamAttempt(
        exam_id=exam.id,
        student_id=s_prof.id,
        status=ExamAttemptStatus.IN_PROGRESS,
        total_points=10.0,
    )
    db_session.add(attempt)
    db_session.flush()

    # Answers:
    # 1. MC: "c" (lowercase match)
    db_session.add(ExamResponse(attempt_id=attempt.id, question_id=q_mc.id, student_answer="c", order_answered=1))
    # 2. TF: "False" (synonym match for "Sai")
    db_session.add(ExamResponse(attempt_id=attempt.id, question_id=q_tf.id, student_answer="false", order_answered=2))
    # 3. SA: "3.14150" (float equivalence match)
    db_session.add(ExamResponse(attempt_id=attempt.id, question_id=q_sa_num.id, student_answer="3.14150", order_answered=3))
    # 4. Unanswered
    db_session.commit()

    scoring_service = ExamScoringService(db_session)
    graded_attempt = scoring_service.score_attempt(attempt.id)

    assert graded_attempt.status == ExamAttemptStatus.GRADED
    assert graded_attempt.score == 7.5  # 3 out of 4 correct (2.5 * 3)
    assert graded_attempt.total_points == 10.0
    assert graded_attempt.accuracy == 0.75

    # Check unanswered question response was created with score 0.0
    unans_resp = db_session.scalar(
        select(ExamResponse).where(ExamResponse.attempt_id == attempt.id, ExamResponse.question_id == q_unans.id)
    )
    assert unans_resp is not None
    assert unans_resp.is_correct is False
    assert unans_resp.score_awarded == 0.0


# --------------------------------------------------------------------------
# 6. Comprehensive Exam Analytics (All 10 Metrics)
# --------------------------------------------------------------------------

def test_exam_analytics_all_metrics(
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_analytics@example.com")
    student_user = exam_user_factory(Role.STUDENT, "s_analytics@example.com")
    s_prof = student_profile(student_user)

    subject, chapter, topic, pt1, pt2, c_target, c_prereq = _setup_curriculum(db_session, "ANA")

    q1 = _create_question(db_session, subject.id, teacher.id, "ANA Q1", QuestionType.MULTIPLE_CHOICE, 0.2, "A", pt1.id, c_target.id)
    q2 = _create_question(db_session, subject.id, teacher.id, "ANA Q2", QuestionType.MULTIPLE_CHOICE, 0.5, "B", pt2.id, c_prereq.id)
    q3 = _create_question(db_session, subject.id, teacher.id, "ANA Q3", QuestionType.TRUE_FALSE, 0.8, "Đúng", pt1.id, c_target.id)

    exam = Exam(
        subject_id=subject.id,
        title="Đề thi phân tích toàn diện",
        duration_minutes=45,
        exam_type=ExamType.REAL_SIMULATION,
        status=ExamStatus.PUBLISHED,
        created_by=teacher.id,
        total_questions=3,
        total_points=10.0,
    )
    db_session.add(exam)
    db_session.flush()
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q1.id, order_index=0, points=3.0))
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q2.id, order_index=1, points=3.0))
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q3.id, order_index=2, points=4.0))

    attempt = ExamAttempt(
        exam_id=exam.id,
        student_id=s_prof.id,
        status=ExamAttemptStatus.GRADED,
        duration_seconds=1800,
        score=7.0,
        total_points=10.0,
        accuracy=round(2 / 3, 4),
    )
    db_session.add(attempt)
    db_session.flush()

    now = datetime.now(timezone.utc)
    # Q1: Correct (answered first)
    db_session.add(ExamResponse(attempt_id=attempt.id, question_id=q1.id, student_answer="A", is_correct=True, score_awarded=3.0, response_time_seconds=30.0, answered_at=now - timedelta(minutes=20), order_answered=1))
    # Q3: Correct (answered second, skipping Q2 -> testing order behavior)
    db_session.add(ExamResponse(attempt_id=attempt.id, question_id=q3.id, student_answer="Đúng", is_correct=True, score_awarded=4.0, response_time_seconds=60.0, answered_at=now - timedelta(minutes=10), order_answered=2))
    # Q2: Incorrect on prerequisite concept (answered last)
    db_session.add(ExamResponse(attempt_id=attempt.id, question_id=q2.id, student_answer="Sai", is_correct=False, score_awarded=0.0, response_time_seconds=120.0, answered_at=now - timedelta(minutes=2), order_answered=3))
    db_session.commit()

    analytics_service = ExamAnalyticsService(db_session)
    analytics = analytics_service.generate_analytics(attempt.id)

    # 1. Scores
    assert analytics.score == 7.0
    assert analytics.score_10 == 7.0
    assert analytics.total_points == 10.0
    assert analytics.accuracy == round(2 / 3, 4)

    # 2. Counts
    assert analytics.total_questions == 3
    assert analytics.correct_count == 2
    assert analytics.incorrect_count == 1
    assert analytics.unanswered_count == 0

    # 3. Chapter Performance
    assert len(analytics.chapter_performance) == 1
    assert analytics.chapter_performance[0].chapter_name == chapter.name

    # 4. Topic Performance
    assert len(analytics.topic_performance) == 1
    assert analytics.topic_performance[0].topic_name == topic.name

    # 5. ProblemType Performance
    assert len(analytics.problem_type_performance) == 2

    # 6. Concept Evidence (Prerequisite diagnostics)
    assert len(analytics.concept_evidence) == 2
    # Prereq concept c_prereq had 0% accuracy -> should trigger PREREQUISITE_GAP
    prereq_ev = next(ce for ce in analytics.concept_evidence if ce.concept_id == c_prereq.id)
    assert prereq_ev.is_prerequisite is True
    assert prereq_ev.diagnostic_signal == "PREREQUISITE_GAP"

    # 7. Difficulty Performance
    assert len(analytics.difficulty_performance) > 0

    # 8. Time per Question
    assert analytics.time_per_question.average_seconds_per_question == 70.0  # (30 + 60 + 120) / 3
    assert analytics.time_per_question.fastest_question_id == q1.id
    assert analytics.time_per_question.slowest_question_id == q2.id

    # 9. Accuracy Over Time
    assert analytics.accuracy_over_time.first_half_accuracy >= 0.0

    # 10. Question Order Behavior
    assert analytics.question_order_behavior.is_sequential is False  # Q1 then Q3 then Q2
    assert analytics.question_order_behavior.skip_count > 0
    assert "nhảy cóc" in analytics.question_order_behavior.behavior_summary


# --------------------------------------------------------------------------
# 7. Mastery Engine Integration Policy (Isolated unless Explicit)
# --------------------------------------------------------------------------

def test_mastery_engine_policy_isolation(
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_mast_pol@example.com")
    student_user = exam_user_factory(Role.STUDENT, "s_mast_pol@example.com")
    s_prof = student_profile(student_user)

    subject, chapter, topic, pt1, _, c_target, _ = _setup_curriculum(db_session, "MST")
    q1 = _create_question(db_session, subject.id, teacher.id, "MST Q1", QuestionType.MULTIPLE_CHOICE, 0.3, "A", pt1.id, c_target.id)

    exam = Exam(
        subject_id=subject.id,
        title="Mastery Policy Test Exam",
        duration_minutes=30,
        exam_type=ExamType.REAL_SIMULATION,
        status=ExamStatus.PUBLISHED,
        created_by=teacher.id,
        total_questions=1,
    )
    db_session.add(exam)
    db_session.flush()
    db_session.add(ExamQuestion(exam_id=exam.id, question_id=q1.id, order_index=0, points=10.0))
    db_session.commit()

    sim_service = ExamSimulationService(db_session)

    # 1. Take exam with update_mastery=False (DEFAULT)
    start_info = sim_service.start_exam(student_user.id, exam.id)
    attempt_id = start_info.attempt_id
    sim_service.record_response(
        student_user.id,
        attempt_id,
        ExamResponseSubmitRequest(question_id=q1.id, student_answer="A"),
    )
    res_default = sim_service.submit_exam(student_user.id, attempt_id, update_mastery=False)
    db_session.commit()

    assert res_default.official_mastery_updated is False

    # Check that NO mastery records were created for this student
    c_m = db_session.scalar(select(StudentConceptMastery).where(StudentConceptMastery.student_id == s_prof.id))
    pt_m = db_session.scalar(select(StudentProblemTypeMastery).where(StudentProblemTypeMastery.student_id == s_prof.id))
    assert c_m is None
    assert pt_m is None

    # 2. Now take exam with explicit policy: update_mastery=True
    start_info_2 = sim_service.start_exam(student_user.id, exam.id)
    attempt_id_2 = start_info_2.attempt_id
    sim_service.record_response(
        student_user.id,
        attempt_id_2,
        ExamResponseSubmitRequest(question_id=q1.id, student_answer="A"),
    )
    res_explicit = sim_service.submit_exam(student_user.id, attempt_id_2, update_mastery=True)
    db_session.commit()

    assert res_explicit.official_mastery_updated is True

    # Check that official Mastery Engine updated the records
    c_m_updated = db_session.scalar(select(StudentConceptMastery).where(StudentConceptMastery.student_id == s_prof.id))
    pt_m_updated = db_session.scalar(select(StudentProblemTypeMastery).where(StudentProblemTypeMastery.student_id == s_prof.id))
    assert c_m_updated is not None
    assert pt_m_updated is not None
    assert c_m_updated.attempt_count == 1
    assert pt_m_updated.attempt_count == 1

    # 3. Duplicate submit guard: submitting again does not double-apply mastery
    res_duplicate = sim_service.submit_exam(student_user.id, attempt_id_2, update_mastery=True)
    db_session.commit()
    assert res_duplicate.official_mastery_updated is False
    db_session.refresh(c_m_updated)
    db_session.refresh(pt_m_updated)
    assert c_m_updated.attempt_count == 1
    assert pt_m_updated.attempt_count == 1
