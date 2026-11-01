from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v2.application import create_v2_app
from app.assignments.models import (
    Assignment,
    AssignmentStatus,
    AssignmentStudentQuestion,
    AssignmentType,
    StudentAssignment,
    StudentAssignmentStatus,
)
from app.auth.models import AuthSession
from app.auth.security import TokenService, utc_now
from app.database.session import get_db
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.core.config import Settings
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.math_solutions.models import (
    EvaluationDecision,
    SolutionAttempt,
    SolutionRubric,
    SolutionStep,
    StepEvaluation,
    StepRevision,
)
from app.questions.models import Question, QuestionStatus, QuestionType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_name="EduMS",
        app_env="test",
        debug=False,
        database_name="test_teacher_grading",
        database_user="test",
        database_password="",
        jwt_secret_key="01234567890123456789012345678901",
        frontend_url="http://localhost:3000",
        ai_provider="mock",
    )


@pytest.fixture
def grading_fixture(db_session: Session):
    # Teacher 1
    t1_user = User(
        id=uuid4(),
        email=f"teacher1_{uuid4().hex[:6]}@edums.vn",
        password_hash="hash",
        full_name="Thầy Giáo Viên 1",
        role=Role.TEACHER,
    )
    db_session.add(t1_user)

    # Teacher 2 (Outsider)
    t2_user = User(
        id=uuid4(),
        email=f"teacher2_{uuid4().hex[:6]}@edums.vn",
        password_hash="hash",
        full_name="Cô Giáo Viên 2",
        role=Role.TEACHER,
    )
    db_session.add(t2_user)

    # Student
    s_user = User(
        id=uuid4(),
        email=f"student_{uuid4().hex[:6]}@edums.vn",
        password_hash="hash",
        full_name="Nguyễn Văn Học Sinh",
        role=Role.STUDENT,
    )
    db_session.add(s_user)
    db_session.flush()

    t1_profile = TeacherProfile(id=uuid4(), user_id=t1_user.id, specialization="Toán 12")
    db_session.add(t1_profile)
    t2_profile = TeacherProfile(id=uuid4(), user_id=t2_user.id, specialization="Vật lý")
    db_session.add(t2_profile)
    s_profile = StudentProfile(id=uuid4(), user_id=s_user.id, grade_level=12)
    db_session.add(s_profile)
    db_session.flush()

    # Classroom
    classroom = Classroom(
        id=uuid4(),
        name="Lớp 12A1 Chuyên Toán",
        academic_year="2026-2027",
        grade_level=12,
        created_by=t1_user.id,
    )
    db_session.add(classroom)
    db_session.flush()

    tc = TeacherClassroom(teacher_id=t1_profile.id, classroom_id=classroom.id, role="PRIMARY")
    db_session.add(tc)
    se = StudentEnrollment(classroom_id=classroom.id, student_id=s_profile.id, status=EnrollmentStatus.ACTIVE)
    db_session.add(se)
    db_session.flush()

    # Subject
    subject = Subject(id=uuid4(), code=f"MATH_{uuid4().hex[:4].upper()}", name="Toán 12", grade_level=12, order_index=1)
    db_session.add(subject)
    db_session.flush()

    # Assignment
    assignment = Assignment(
        id=uuid4(),
        classroom_id=classroom.id,
        created_by=t1_user.id,
        subject_id=subject.id,
        title="Bài kiểm tra Khảo sát Đạo hàm",
        assignment_type=AssignmentType.SAME_SET,
        status=AssignmentStatus.PUBLISHED,
        question_count=1,
    )
    db_session.add(assignment)
    db_session.flush()

    # Question
    question = Question(
        id=uuid4(),
        subject_id=subject.id,
        content="Khảo sát sự biến thiên của hàm số y = x^3 - 3x",
        content_hash="a" * 64,
        question_type="OPEN_RESPONSE",
        status="APPROVED",
        difficulty=0.5,
        source_type="SAMPLE_TEST",
        exam_weight=1.0,
        created_by=t1_user.id,
    )
    db_session.add(question)
    db_session.flush()

    # Rubric
    rubric = SolutionRubric(
        id=uuid4(),
        question_id=question.id,
        rubric_version=1,
        title="Rubric khảo sát đạo hàm",
        status="APPROVED",
        criteria=[
            {"code": "DERIVATIVE", "weight": 0.4, "label": "Đạo hàm"},
            {"code": "ROOTS", "weight": 0.3, "label": "Nghiệm đạo hàm"},
            {"code": "CONCLUSION", "weight": 0.3, "label": "Kết luận"},
        ],
        approved_by=t1_user.id,
    )
    db_session.add(rubric)
    db_session.flush()

    # Student Assignment & Assigned Question
    sa = StudentAssignment(
        id=uuid4(),
        assignment_id=assignment.id,
        student_id=s_profile.id,
        status=StudentAssignmentStatus.SUBMITTED,
    )
    db_session.add(sa)
    db_session.flush()

    asq = AssignmentStudentQuestion(
        id=uuid4(),
        student_assignment_id=sa.id,
        question_id=question.id,
        order_index=1,
    )
    db_session.add(asq)
    db_session.flush()

    # Attempt
    attempt = SolutionAttempt(
        id=uuid4(),
        student_id=s_profile.id,
        source_kind="CANONICAL",
        context_type="CLASSROOM_ASSIGNMENT",
        assignment_id=assignment.id,
        student_assignment_id=sa.id,
        assignment_student_question_id=asq.id,
        question_id=question.id,
        mode="INDEPENDENT_SOLUTION",
        status="SUBMITTED",
        total_score=0.7,
        is_correct=False,
        rubric_id=rubric.id,
        started_at=datetime.now(timezone.utc),
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(attempt)
    db_session.flush()

    # Steps
    step1 = SolutionStep(
        id=uuid4(),
        attempt_id=attempt.id,
        step_index=1,
        step_type="DERIVATIVE_CALCULATION",
        status="ACTIVE",
    )
    db_session.add(step1)
    step2 = SolutionStep(
        id=uuid4(),
        attempt_id=attempt.id,
        step_index=2,
        step_type="CONCLUSION",
        status="ACTIVE",
    )
    db_session.add(step2)
    db_session.flush()

    rev1 = StepRevision(
        id=uuid4(),
        step_id=step1.id,
        step_revision_number=1,
        step_index_at_revision=1,
        content_latex=r"y' = 3x^2 - 3",
        change_reason="STUDENT_EDIT",
    )
    db_session.add(rev1)
    rev2 = StepRevision(
        id=uuid4(),
        step_id=step2.id,
        step_revision_number=1,
        step_index_at_revision=2,
        content_latex=r"Hàm số đồng biến trên (-1, 1)",
        change_reason="STUDENT_EDIT",
    )
    db_session.add(rev2)
    db_session.flush()

    eval1 = StepEvaluation(
        id=uuid4(),
        step_revision_id=rev1.id,
        evaluator_type="AI_HEURISTIC",
        math_validity="VALID",
        score=1.0,
        confidence=0.95,
    )
    db_session.add(eval1)

    eval2 = StepEvaluation(
        id=uuid4(),
        step_revision_id=rev2.id,
        evaluator_type="AI_HEURISTIC",
        math_validity="NEEDS_REVIEW",
        score=0.0,
        confidence=0.5,
        error_description="Cần kiểm tra lại dấu đạo hàm trên khoảng này.",
    )
    db_session.add(eval2)
    db_session.flush()

    db_session.commit()

    return {
        "teacher1": t1_user,
        "teacher2": t2_user,
        "student": s_user,
        "classroom": classroom,
        "assignment": assignment,
        "attempt": attempt,
    }


def make_test_token(user: User, db_session: Session, test_settings: Settings) -> str:
    now = utc_now()
    s = AuthSession(user_id=user.id, expires_at=now + timedelta(days=1))
    db_session.add(s)
    db_session.flush()
    tok, _ = TokenService(test_settings).issue_access_token(user.id, s.id, s.expires_at, now)
    return tok


def test_grading_queue_listing(db_session: Session, test_settings: Settings, grading_fixture):
    app = create_v2_app(test_settings)
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    token = make_test_token(grading_fixture["teacher1"], db_session, test_settings)
    headers = {"Authorization": f"Bearer {token}"}

    # List queue
    resp = client.get("/teacher/grading/queue", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["pending_count"] == 1
    assert data["items"][0]["attempt_id"] == str(grading_fixture["attempt"].id)
    assert data["items"][0]["needs_teacher_review"] is True
    assert data["items"][0]["unverified_steps_count"] == 1


def test_get_attempt_detail(db_session: Session, test_settings: Settings, grading_fixture):
    app = create_v2_app(test_settings)
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    token = make_test_token(grading_fixture["teacher1"], db_session, test_settings)
    headers = {"Authorization": f"Bearer {token}"}

    attempt_id = str(grading_fixture["attempt"].id)
    resp = client.get(f"/teacher/grading/attempts/{attempt_id}", headers=headers)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["attempt_id"] == attempt_id
    assert len(detail["steps"]) == 2
    assert detail["steps"][0]["evaluation"]["math_validity"] == "VALID"
    assert detail["steps"][1]["evaluation"]["math_validity"] == "NEEDS_REVIEW"


def test_batch_approve(db_session: Session, test_settings: Settings, grading_fixture):
    app = create_v2_app(test_settings)
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    token = make_test_token(grading_fixture["teacher1"], db_session, test_settings)
    headers = {"Authorization": f"Bearer {token}"}

    attempt_id = str(grading_fixture["attempt"].id)
    resp = client.post(
        "/teacher/grading/batch-approve",
        headers=headers,
        json={"attempt_ids": [attempt_id], "note": "Duyệt toàn bộ bước hợp lệ"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["approved_count"] == 1
    assert body["failed_count"] == 0

    # Verify decision exists
    decision = db_session.query(EvaluationDecision).filter(EvaluationDecision.attempt_id == UUID(attempt_id)).first()
    assert decision is not None
    assert decision.decision_source == "TEACHER_REVIEW"
    assert decision.decided_by == grading_fixture["teacher1"].id


def test_teacher_override_and_retry_sync(db_session: Session, test_settings: Settings, grading_fixture):
    app = create_v2_app(test_settings)
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    token = make_test_token(grading_fixture["teacher1"], db_session, test_settings)
    headers = {"Authorization": f"Bearer {token}"}

    attempt_id = str(grading_fixture["attempt"].id)

    # 1. Override score to 0.85
    resp = client.post(
        f"/teacher/grading/{attempt_id}/override",
        headers=headers,
        json={
            "new_score": 0.85,
            "new_is_correct": True,
            "reason": "Học sinh giải thích bằng miệng đúng dù ghi nhầm dấu.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_score"] == 0.85
    assert data["new_is_correct"] is True
    assert data["sync_status"] == "SYNCED"

    # 2. Retry sync
    retry_resp = client.post(
        f"/teacher/grading/{attempt_id}/retry-sync",
        headers=headers,
    )
    assert retry_resp.status_code == 200
    retry_data = retry_resp.json()
    assert retry_data["sync_status"] == "SYNCED"


def test_outsider_teacher_forbidden(db_session: Session, test_settings: Settings, grading_fixture):
    app = create_v2_app(test_settings)
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    # Teacher 2 (outsider)
    token = make_test_token(grading_fixture["teacher2"], db_session, test_settings)
    headers = {"Authorization": f"Bearer {token}"}

    attempt_id = str(grading_fixture["attempt"].id)
    resp = client.get(f"/teacher/grading/attempts/{attempt_id}", headers=headers)
    assert resp.status_code == 403
