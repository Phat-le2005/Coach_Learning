from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.math_solutions.schemas import SolutionStepDraft
from app.math_solutions.service import MathSolutionService

from app.assignments.models import (
    Assignment,
    AssignmentMaterialItem,
    AssignmentMaterialItemOption,
    AssignmentQuestion,
    AssignmentStatus,
    AssignmentStudentQuestion,
    AssignmentType,
    StudentAssignment,
    StudentAssignmentMaterialItem,
    StudentAssignmentStatus,
)
from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment
from app.concepts.models import Concept
from app.core.config import Settings
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, Topic
from app.math_solutions.models import (
    SolutionAttempt,
    SolutionStep,
)
from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionStatus,
    PracticeSessionType,
)
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionGroup,
    QuestionGroupItem,
    QuestionGroupScoringPolicy,
    QuestionGroupType,
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teacher_materials.models import (
    MaterialEvaluationMode,
    MaterialItemExtractionStatus,
    TeacherMaterial,
    TeacherMaterialItem,
    TeacherMaterialStatus,
)
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

PASSWORD = "Delivery-Test-Password-2026!"


@dataclass
class DeliveryDomain:
    teacher: User
    student_a: User
    student_b: User
    student_profile_a: StudentProfile
    student_profile_b: StudentProfile
    classroom: Classroom
    subject: Subject
    canonical_question: Question
    canonical_question_options: list[QuestionOption]
    practice_session: PracticeSession
    teacher_material: TeacherMaterial
    teacher_material_item: TeacherMaterialItem
    assignment: Assignment
    student_assignment_a: StudentAssignment
    student_assignment_b: StudentAssignment
    material_snapshot: AssignmentMaterialItem


@pytest.fixture
def delivery_domain(db_session: Session) -> DeliveryDomain:
    users = UserService(db_session)

    def create_user(role: Role, local_part: str) -> User:
        return users.create_user(
            UserCreate(
                email=f"{local_part}@example.com",
                password=PASSWORD,
                full_name=f"{role.value.title()} Delivery User",
                role=role,
            )
        )

    teacher = create_user(Role.TEACHER, "del-teacher")
    student_a = create_user(Role.STUDENT, "del-student-a")
    student_b = create_user(Role.STUDENT, "del-student-b")

    profile_a = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student_a.id)
    )
    profile_b = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student_b.id)
    )
    assert profile_a is not None
    assert profile_b is not None

    subject = Subject(code="MATH-DEL-12", name="Math 12 Delivery", grade_level=12)
    db_session.add(subject)
    db_session.flush()

    classroom = Classroom(
        name="12A1 Math",
        academic_year="2026-2027",
        created_by=teacher.id,
        grade_level=12,
    )
    db_session.add(classroom)
    db_session.flush()

    # Enroll student A actively; student B not enrolled initially
    enrollment_a = StudentEnrollment(
        classroom_id=classroom.id,
        student_id=profile_a.id,
        status=EnrollmentStatus.ACTIVE,
    )
    db_session.add(enrollment_a)

    # Curriculum nodes for practice eligibility
    chapter = Chapter(
        subject_id=subject.id,
        code="CHP-DEL-1",
        name="Chương 1 Đơn Điệu",
        description="Đơn điệu hàm số",
        order_index=0,
    )
    concept = Concept(
        subject_id=subject.id,
        code="CON-DEL-1",
        name="Tính đơn điệu",
        description="Khái niệm đơn điệu",
        grade_level=12,
        order_index=0,
    )
    outcome = LearningOutcome(
        subject_id=subject.id,
        code="LO-DEL-1",
        description="Khảo sát tính đơn điệu hàm số",
        grade_level=12,
        order_index=0,
    )
    db_session.add_all([chapter, concept, outcome])
    db_session.flush()

    topic = Topic(
        chapter_id=chapter.id,
        code="TOP-DEL-1",
        name="Sự đồng biến nghịch biến",
        description="Chủ đề đơn điệu",
        order_index=0,
    )
    db_session.add(topic)
    db_session.flush()

    pt = ProblemType(
        topic_id=topic.id,
        code="PT-DEL-1",
        name="Xét dấu đạo hàm",
        description="Dạng toán xét dấu y'",
        order_index=0,
    )
    db_session.add(pt)
    db_session.flush()

    # Approved canonical question with options and classifications
    canonical_q = Question(
        subject_id=subject.id,
        content="Cho hàm số y = f(x). Khảo sát tính đơn điệu trên R.",
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=0.5,
        correct_answer="A - SECRET ANSWER KEY",
        explanation="INTERNAL EXPLANATION - MUST NOT BE LEAKED",
        source_type="TEST",
        source_reference="delivery-test-suite",
        exam_weight=1.0,
        status=QuestionStatus.APPROVED,
        created_by=teacher.id,
        concept_links=[QuestionConcept(concept_id=concept.id, weight=1.0)],
        learning_outcome_links=[QuestionLearningOutcome(learning_outcome_id=outcome.id)],
        problem_type_links=[QuestionProblemType(problem_type_id=pt.id, weight=1.0)],
    )
    db_session.add(canonical_q)
    db_session.flush()

    opt_a = QuestionOption(
        question_id=canonical_q.id,
        label="A",
        content="Đồng biến trên R",
        order_index=1,
    )
    opt_b = QuestionOption(
        question_id=canonical_q.id,
        label="B",
        content="Nghịch biến trên R",
        order_index=2,
    )
    db_session.add_all([opt_a, opt_b])
    db_session.flush()

    # Active practice session for student A
    practice = PracticeSession(
        student_id=profile_a.id,
        subject_id=subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    db_session.add(practice)
    db_session.flush()

    # Teacher Material PDF + Item
    tm = TeacherMaterial(
        classroom_id=classroom.id,
        subject_id=subject.id,
        uploaded_by=teacher.id,
        title="Đề thi thử PDF Chương 1",
        original_file_name="de_thi_thu_c1.pdf",
        mime_type="application/pdf",
        storage_key="materials/secret_pdf_key_not_for_students.pdf",
        sha256="a" * 64,
        file_size_bytes=1048576,
        page_count=5,
        status=TeacherMaterialStatus.READY,
    )
    db_session.add(tm)
    db_session.flush()

    tmi = TeacherMaterialItem(
        teacher_material_id=tm.id,
        order_index=0,
        page_start=1,
        page_end=2,
        content="Câu 1 PDF: Tìm khoảng nghịch biến của g(x).",
        content_hash="b" * 64,
        question_type=QuestionType.OPEN_RESPONSE,
        correct_answer="SECRET PDF KEY (x in (0, 2))",
        explanation="SECRET PDF EXPLANATION",
        difficulty=0.6,
        extraction_status=MaterialItemExtractionStatus.READY,
        evaluation_mode=MaterialEvaluationMode.OPEN_RESPONSE,
        raw_metadata={"content_reviewed": True},
    )
    db_session.add(tmi)
    db_session.flush()

    # Published Assignment
    now = datetime.now(timezone.utc)
    assignment = Assignment(
        classroom_id=classroom.id,
        subject_id=subject.id,
        created_by=teacher.id,
        question_count=2,
        title="Bài tập về nhà tuần 1",
        assignment_type=AssignmentType.SAME_SET,
        status=AssignmentStatus.PUBLISHED,
        start_at=now - timedelta(hours=1),
        due_at=now + timedelta(days=2),
    )
    db_session.add(assignment)
    db_session.flush()

    # Assignment questions and material snapshots (frozen)
    aq = AssignmentQuestion(
        assignment_id=assignment.id,
        question_id=canonical_q.id,
        order_index=0,
    )
    db_session.add(aq)

    ami = AssignmentMaterialItem(
        assignment_id=assignment.id,
        teacher_material_item_id=tmi.id,
        teacher_material_id=tm.id,
        source_content_hash=tmi.content_hash,
        content="SNAPSHOT: Câu 1 PDF: Tìm khoảng nghịch biến của g(x).",
        question_type=QuestionType.OPEN_RESPONSE,
        correct_answer="SECRET SNAPSHOT ANSWER",
        explanation="SECRET SNAPSHOT EXPLANATION",
        difficulty=0.6,
        evaluation_mode=MaterialEvaluationMode.OPEN_RESPONSE,
        snapshotted_at=now - timedelta(hours=1),
        order_index=0,
    )
    db_session.add(ami)
    db_session.flush()

    ami_opt = AssignmentMaterialItemOption(
        assignment_material_item_id=ami.id,
        label="A",
        content="Khoảng (0, 2)",
        order_index=1,
    )
    db_session.add(ami_opt)

    # StudentAssignment for student A (initially NOT prepared)
    sa_a = StudentAssignment(
        assignment_id=assignment.id,
        student_id=profile_a.id,
        status=StudentAssignmentStatus.NOT_STARTED,
        assigned_at=now - timedelta(hours=1),
    )
    # StudentAssignment for student B
    sa_b = StudentAssignment(
        assignment_id=assignment.id,
        student_id=profile_b.id,
        status=StudentAssignmentStatus.NOT_STARTED,
        assigned_at=now - timedelta(hours=1),
    )
    db_session.add_all([sa_a, sa_b])
    db_session.commit()

    return DeliveryDomain(
        teacher=teacher,
        student_a=student_a,
        student_b=student_b,
        student_profile_a=profile_a,
        student_profile_b=profile_b,
        classroom=classroom,
        subject=subject,
        canonical_question=canonical_q,
        canonical_question_options=[opt_a, opt_b],
        practice_session=practice,
        teacher_material=tm,
        teacher_material_item=tmi,
        assignment=assignment,
        student_assignment_a=sa_a,
        student_assignment_b=sa_b,
        material_snapshot=ami,
    )


@pytest.fixture
def auth_headers(db_session: Session, settings: Settings):
    def build(user: User) -> dict[str, str]:
        pair = AuthService(db_session, settings).login(
            LoginRequest(email=user.email, password=PASSWORD)
        )
        return {"Authorization": f"Bearer {pair.access_token}"}

    return build


# =========================================================================
# 1. Practice Session Delivery Tests
# =========================================================================

def test_practice_next_problem_delivers_canonical_question(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers
) -> None:
    headers = auth_headers(delivery_domain.student_a)
    url = f"/api/v2/math-solutions/practice-sessions/{delivery_domain.practice_session.id}/next-problem"

    res = db_client.get(url, headers=headers)
    assert res.status_code == 200
    assert res.headers.get("Cache-Control") == "no-store"
    assert res.headers.get("Pragma") == "no-cache"

    body = res.json()
    assert body["source_kind"] == "CANONICAL"
    assert body["context_type"] == "SELF_PRACTICE"
    assert body["question_id"] == str(delivery_domain.canonical_question.id)
    assert body["practice_session_id"] == str(delivery_domain.practice_session.id)
    assert body["content"] == delivery_domain.canonical_question.content
    assert body["is_read_only"] is False
    assert len(body["options"]) == 2
    assert body["options"][0]["label"] == "A"
    assert body["options"][1]["label"] == "B"

    # Redaction checks
    assert "correct_answer" not in body
    assert "explanation" not in body
    for opt in body["options"]:
        assert "is_correct" not in opt


def test_practice_next_problem_excludes_attempted_and_returns_404_when_exhausted(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers
) -> None:
    headers = auth_headers(delivery_domain.student_a)
    url = f"/api/v2/math-solutions/practice-sessions/{delivery_domain.practice_session.id}/next-problem"

    # 1. First call delivers the question
    res1 = db_client.get(url, headers=headers)
    assert res1.status_code == 200

    # 2. Student creates a solution attempt for this question in this session
    create_res = db_client.post(
        "/api/v2/math-solutions/attempts",
        json={
            "source_kind": "CANONICAL",
            "context_type": "SELF_PRACTICE",
            "mode": "INDEPENDENT_SOLUTION",
            "create_idempotency_key": "practice-attempt-1",
            "question_id": str(delivery_domain.canonical_question.id),
            "practice_session_id": str(delivery_domain.practice_session.id),
        },
        headers=headers,
    )
    assert create_res.status_code == 201

    # 3. Next call should exclude the already attempted question and return 404
    res2 = db_client.get(url, headers=headers)
    assert res2.status_code == 404
    assert res2.json()["error"]["code"] == "NO_QUESTIONS_AVAILABLE"


def test_practice_next_problem_auth_and_idor(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers
) -> None:
    session_id = delivery_domain.practice_session.id
    url = f"/api/v2/math-solutions/practice-sessions/{session_id}/next-problem"

    # Anonymous
    assert db_client.get(url).status_code == 401

    # Teacher forbidden
    teacher_headers = auth_headers(delivery_domain.teacher)
    assert db_client.get(url, headers=teacher_headers).status_code == 403

    # Outsider student gets 404
    outsider_headers = auth_headers(delivery_domain.student_b)
    res_b = db_client.get(url, headers=outsider_headers)
    assert res_b.status_code == 404
    assert res_b.json()["error"]["code"] == "PRACTICE_SESSION_NOT_FOUND"


# =========================================================================
# 2. Assignment Preparation & Delivery Tests
# =========================================================================

def test_assignment_problems_pure_read_and_requires_prepare(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers, db_session: Session
) -> None:
    headers = auth_headers(delivery_domain.student_a)
    sa_id = delivery_domain.student_assignment_a.id
    problems_url = f"/api/v2/math-solutions/student-assignments/{sa_id}/problems"

    # 1. Calling GET before prepare returns 409 ASSIGNMENT_NOT_PREPARED
    res = db_client.get(problems_url, headers=headers)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "ASSIGNMENT_NOT_PREPARED"

    # 2. Verify zero writes occurred
    count_qs = db_session.scalar(
        select(func.count(AssignmentStudentQuestion.id)).where(
            AssignmentStudentQuestion.student_assignment_id == sa_id
        )
    )
    count_mis = db_session.scalar(
        select(func.count(StudentAssignmentMaterialItem.id)).where(
            StudentAssignmentMaterialItem.student_assignment_id == sa_id
        )
    )
    assert count_qs == 0
    assert count_mis == 0


def test_prepare_assignment_is_idempotent_and_populates_both_sources(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers
) -> None:
    headers = auth_headers(delivery_domain.student_a)
    sa_id = delivery_domain.student_assignment_a.id
    prepare_url = f"/api/v2/math-solutions/student-assignments/{sa_id}/prepare"
    problems_url = f"/api/v2/math-solutions/student-assignments/{sa_id}/problems"

    # 1. POST prepare
    prep_res = db_client.post(prepare_url, headers=headers)
    assert prep_res.status_code == 200
    prep_body = prep_res.json()
    assert prep_body["status"] == "IN_PROGRESS"
    assert prep_body["item_count"] == 2
    assert len(prep_body["problems"]) == 2

    # Verify first problem: canonical question
    p1 = prep_body["problems"][0]
    assert p1["source_kind"] == "CANONICAL"
    assert p1["context_type"] == "CLASSROOM_ASSIGNMENT"
    assert p1["order_index"] == 0
    assert p1["question_id"] == str(delivery_domain.canonical_question.id)
    assert p1["assignment_student_question_id"] is not None
    assert p1["student_assignment_material_item_id"] is None
    assert p1["source_metadata"] is None

    # Verify second problem: teacher material snapshot
    p2 = prep_body["problems"][1]
    assert p2["source_kind"] == "TEACHER_MATERIAL"
    assert p2["context_type"] == "CLASSROOM_ASSIGNMENT"
    assert p2["order_index"] == 1
    assert p2["question_id"] is None
    assert p2["assignment_student_question_id"] is None
    assert p2["student_assignment_material_item_id"] is not None
    assert p2["source_metadata"]["title"] == "Đề thi thử PDF Chương 1"
    assert p2["source_metadata"]["page_start"] == 1
    assert p2["source_metadata"]["page_end"] == 2
    assert "storage_key" not in p2["source_metadata"]

    # 2. Second POST prepare call is strictly idempotent (no duplicates)
    prep_res2 = db_client.post(prepare_url, headers=headers)
    assert prep_res2.status_code == 200
    assert prep_res2.json()["item_count"] == 2

    # 3. GET problems now succeeds and matches prepared items
    get_res = db_client.get(problems_url, headers=headers)
    assert get_res.status_code == 200
    get_body = get_res.json()
    assert len(get_body) == 2
    assert get_body[0]["id"] == p1["id"]
    assert get_body[1]["id"] == p2["id"]


def test_pdf_snapshot_immutability(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers, db_session: Session
) -> None:
    headers = auth_headers(delivery_domain.student_a)
    sa_id = delivery_domain.student_assignment_a.id

    # 1. Prepare assignment
    prep_res = db_client.post(
        f"/api/v2/math-solutions/student-assignments/{sa_id}/prepare",
        headers=headers,
    )
    assert prep_res.status_code == 200

    # 2. Teacher modifies original TeacherMaterialItem
    tmi = db_session.get(TeacherMaterialItem, delivery_domain.teacher_material_item.id)
    assert tmi is not None
    tmi.content = "MODIFIED TEACHER MATERIAL ITEM - SHOULD NOT AFFECT STUDENTS"
    db_session.commit()

    # 3. Student reads assignment problems
    res = db_client.get(
        f"/api/v2/math-solutions/student-assignments/{sa_id}/problems",
        headers=headers,
    )
    assert res.status_code == 200
    items = res.json()
    pdf_item = items[1]
    assert pdf_item["source_kind"] == "TEACHER_MATERIAL"
    # Content must remain the frozen snapshot, not the modified teacher material
    assert pdf_item["content"] == "SNAPSHOT: Câu 1 PDF: Tìm khoảng nghịch biến của g(x)."


def test_assignment_access_control_and_isolation(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers, db_session: Session
) -> None:
    sa_a_id = delivery_domain.student_assignment_a.id
    sa_b_id = delivery_domain.student_assignment_b.id

    # Student B is not enrolled in the classroom
    headers_b = auth_headers(delivery_domain.student_b)
    prep_b = db_client.post(
        f"/api/v2/math-solutions/student-assignments/{sa_b_id}/prepare",
        headers=headers_b,
    )
    assert prep_b.status_code == 403
    assert prep_b.json()["error"]["code"] == "NOT_ENROLLED_IN_CLASSROOM"

    # Student B cannot access Student A's assignment (404)
    res_b_on_a = db_client.get(
        f"/api/v2/math-solutions/student-assignments/{sa_a_id}/problems",
        headers=headers_b,
    )
    assert res_b_on_a.status_code == 404
    assert res_b_on_a.json()["error"]["code"] == "STUDENT_ASSIGNMENT_NOT_FOUND"


# =========================================================================
# 3. End-to-End Math Workspace Loop Tests
# =========================================================================

def test_workspace_loop_canonical_question(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers
) -> None:
    headers = auth_headers(delivery_domain.student_a)

    # 1. Fetch next problem from practice session
    prob_res = db_client.get(
        f"/api/v2/math-solutions/practice-sessions/{delivery_domain.practice_session.id}/next-problem",
        headers=headers,
    )
    assert prob_res.status_code == 200
    problem = prob_res.json()

    # 2. Create SolutionAttempt
    create_res = db_client.post(
        "/api/v2/math-solutions/attempts",
        json={
            "source_kind": problem["source_kind"],
            "context_type": problem["context_type"],
            "mode": "INDEPENDENT_SOLUTION",
            "create_idempotency_key": "e2e-loop-canonical-1",
            "question_id": problem["question_id"],
            "practice_session_id": problem["practice_session_id"],
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    attempt = create_res.json()
    attempt_id = attempt["id"]

    # 3. Add solution step
    add_step_res = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
        json={
            "expected_attempt_revision": 1,
            "client_action_id": str(uuid4()),
            "step_type": "DERIVATIVE_CALCULATION",
            "content_latex": "f'(x) = 3x^2 + 2x",
            "explanation_text": "Tính đạo hàm bậc nhất của hàm số f(x)",
        },
        headers=headers,
    )
    assert add_step_res.status_code == 201

    # 4. Student refreshes workspace: read problem and attempt
    reload_prob_res = db_client.get(
        f"/api/v2/math-solutions/attempts/{attempt_id}/problem",
        headers=headers,
    )
    assert reload_prob_res.status_code == 200
    reloaded_problem = reload_prob_res.json()
    assert reloaded_problem["id"] == problem["id"]
    assert reloaded_problem["content"] == problem["content"]
    assert reloaded_problem["is_read_only"] is False

    reload_attempt_res = db_client.get(
        f"/api/v2/math-solutions/attempts/{attempt_id}",
        headers=headers,
    )
    assert reload_attempt_res.status_code == 200
    reloaded_attempt = reload_attempt_res.json()
    assert len(reloaded_attempt["steps"]) == 1
    assert reloaded_attempt["attempt_revision_number"] == 2

    # 5. Submit attempt
    submit_res = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/submit",
        json={
            "expected_attempt_revision": 2,
            "client_action_id": str(uuid4()),
        },
        headers=headers,
    )
    assert submit_res.status_code == 200
    assert submit_res.json()["status"] == "SUBMITTED"

    # 6. Reading problem after submit shows is_read_only = True
    prob_after_submit = db_client.get(
        f"/api/v2/math-solutions/attempts/{attempt_id}/problem",
        headers=headers,
    )
    assert prob_after_submit.status_code == 200
    assert prob_after_submit.json()["is_read_only"] is True

    # 7. Modifications to submitted attempt are locked (409)
    locked_res = db_client.post(
        f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
        json={
            "expected_attempt_revision": 3,
            "client_action_id": str(uuid4()),
            "step_type": "CONCLUSION",
            "content_latex": "Done",
        },
        headers=headers,
    )
    assert locked_res.status_code == 409
    assert locked_res.json()["error"]["code"] == "SOLUTION_LOCKED"


def test_workspace_loop_teacher_material_pdf(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers
) -> None:
    headers = auth_headers(delivery_domain.student_a)
    sa_id = delivery_domain.student_assignment_a.id

    # 1. Prepare assignment
    prep_res = db_client.post(
        f"/api/v2/math-solutions/student-assignments/{sa_id}/prepare",
        headers=headers,
    )
    assert prep_res.status_code == 200
    pdf_problem = prep_res.json()["problems"][1]

    # 2. Create SolutionAttempt for the PDF item
    create_res = db_client.post(
        "/api/v2/math-solutions/attempts",
        json={
            "source_kind": pdf_problem["source_kind"],
            "context_type": pdf_problem["context_type"],
            "mode": "INDEPENDENT_SOLUTION",
            "create_idempotency_key": "e2e-loop-pdf-1",
            "student_assignment_id": pdf_problem["student_assignment_id"],
            "student_assignment_material_item_id": pdf_problem["student_assignment_material_item_id"],
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    attempt_id = create_res.json()["id"]

    # 3. Read attempt problem
    prob_res = db_client.get(
        f"/api/v2/math-solutions/attempts/{attempt_id}/problem",
        headers=headers,
    )
    assert prob_res.status_code == 200
    read_prob = prob_res.json()
    assert read_prob["source_kind"] == "TEACHER_MATERIAL"
    assert read_prob["content"] == "SNAPSHOT: Câu 1 PDF: Tìm khoảng nghịch biến của g(x)."
    assert read_prob["source_metadata"]["title"] == "Đề thi thử PDF Chương 1"


# =========================================================================
# 4. Paginated Attempts List Tests
# =========================================================================

def test_list_attempts_pagination_and_filtering(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers
) -> None:
    headers_a = auth_headers(delivery_domain.student_a)
    headers_b = auth_headers(delivery_domain.student_b)

    # Student A creates 3 attempts
    for i in range(1, 4):
        create_res = db_client.post(
            "/api/v2/math-solutions/attempts",
            json={
                "source_kind": "CANONICAL",
                "context_type": "SELF_PRACTICE",
                "mode": "INDEPENDENT_SOLUTION",
                "create_idempotency_key": f"list-test-attempt-{i}",
                "question_id": str(delivery_domain.canonical_question.id),
                "practice_session_id": str(delivery_domain.practice_session.id),
            },
            headers=headers_a,
        )
        assert create_res.status_code == 201

    # Student A lists attempts with page=1, size=2
    list_res = db_client.get(
        "/api/v2/math-solutions/attempts?page=1&size=2",
        headers=headers_a,
    )
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["size"] == 2
    assert data["total_pages"] == 2
    assert len(data["items"]) == 2

    # Filter by practice_session_id
    filter_res = db_client.get(
        f"/api/v2/math-solutions/attempts?practice_session_id={delivery_domain.practice_session.id}",
        headers=headers_a,
    )
    assert filter_res.status_code == 200
    assert filter_res.json()["total"] == 3

    # Student B lists attempts: sees 0 attempts
    b_res = db_client.get("/api/v2/math-solutions/attempts", headers=headers_b)
    assert b_res.status_code == 200
    assert b_res.json()["total"] == 0


# =========================================================================
# 5. Question Group & Adaptive Assignment & Redaction Hardening Tests
# =========================================================================

def test_practice_next_problem_question_group_rejected_with_422(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers, db_session: Session
) -> None:
    headers = auth_headers(delivery_domain.student_a)

    # Create a new session with NO standalone questions
    subject_new = Subject(code="MATH-GRP-12", name="Math Group Test", grade_level=12)
    db_session.add(subject_new)
    db_session.flush()

    group_session = PracticeSession(
        student_id=delivery_domain.student_profile_a.id,
        subject_id=subject_new.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    db_session.add(group_session)
    db_session.flush()

    # Create approved QuestionGroup with 4 items
    qg = QuestionGroup(
        subject_id=subject_new.id,
        content="Cho hàm số bậc ba f(x). Xét tính đúng sai của các khẳng định sau:",
        group_type=QuestionGroupType.TRUE_FALSE_FOUR,
        scoring_policy=QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
        difficulty=0.7,
        source_type="TEST",
        exam_weight=1.0,
        status=QuestionStatus.APPROVED,
        created_by=delivery_domain.teacher.id,
    )
    db_session.add(qg)
    db_session.flush()

    # Add 4 child questions
    for idx, label in enumerate("abcd"):
        child_q = Question(
            subject_id=subject_new.id,
            content=f"Khẳng định ({label}) đúng hay sai?",
            question_type=QuestionType.TRUE_FALSE,
            difficulty=0.7,
            correct_answer="TRUE",
            source_type="TEST",
            exam_weight=0.25,
            status=QuestionStatus.APPROVED,
            created_by=delivery_domain.teacher.id,
            concept_links=[QuestionConcept(concept_id=delivery_domain.canonical_question.concept_links[0].concept_id, weight=1.0)],
            learning_outcome_links=[QuestionLearningOutcome(learning_outcome_id=delivery_domain.canonical_question.learning_outcome_links[0].learning_outcome_id)],
            problem_type_links=[QuestionProblemType(problem_type_id=delivery_domain.canonical_question.problem_type_links[0].problem_type_id, weight=1.0)],
        )
        db_session.add(child_q)
        db_session.flush()

        item = QuestionGroupItem(
            group_id=qg.id,
            question_id=child_q.id,
            label=label,
            order_index=idx,
        )
        db_session.add(item)

    db_session.commit()

    # Request next-problem for this group session -> 422 QUESTION_GROUP_NOT_SUPPORTED
    res = db_client.get(
        f"/api/v2/math-solutions/practice-sessions/{group_session.id}/next-problem",
        headers=headers,
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "QUESTION_GROUP_NOT_SUPPORTED"


def test_prepare_adaptive_assignment_idempotent_no_reroll(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers, db_session: Session
) -> None:
    headers = auth_headers(delivery_domain.student_a)

    # Create an adaptive assignment
    now = datetime.now(timezone.utc)
    adaptive_assignment = Assignment(
        classroom_id=delivery_domain.classroom.id,
        subject_id=delivery_domain.subject.id,
        created_by=delivery_domain.teacher.id,
        question_count=1,
        title="Bài tập thích ứng",
        assignment_type=AssignmentType.ADAPTIVE_SET,
        status=AssignmentStatus.PUBLISHED,
        start_at=now - timedelta(hours=1),
        due_at=now + timedelta(days=2),
    )
    db_session.add(adaptive_assignment)
    db_session.flush()

    sa_adaptive = StudentAssignment(
        assignment_id=adaptive_assignment.id,
        student_id=delivery_domain.student_profile_a.id,
        status=StudentAssignmentStatus.NOT_STARTED,
        assigned_at=now - timedelta(hours=1),
    )
    db_session.add(sa_adaptive)
    db_session.commit()

    url = f"/api/v2/math-solutions/student-assignments/{sa_adaptive.id}/prepare"

    # 1. First prepare call
    res1 = db_client.post(url, headers=headers)
    assert res1.status_code == 200
    problems1 = res1.json()["problems"]
    assert len(problems1) >= 1
    p1_id = problems1[0]["id"]

    # 2. Retry prepare call must return the exact same question, not re-roll
    res2 = db_client.post(url, headers=headers)
    assert res2.status_code == 200
    problems2 = res2.json()["problems"]
    assert len(problems2) == len(problems1)
    assert problems2[0]["id"] == p1_id


def test_sensitive_fields_not_exposed_across_all_delivery_endpoints(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers
) -> None:
    headers = auth_headers(delivery_domain.student_a)
    sa_id = delivery_domain.student_assignment_a.id

    # Prepare
    prep_res = db_client.post(
        f"/api/v2/math-solutions/student-assignments/{sa_id}/prepare",
        headers=headers,
    )
    assert prep_res.status_code == 200
    prep_text = prep_res.text
    assert "correct_answer" not in prep_text
    assert "SECRET" not in prep_text
    assert "storage_key" not in prep_text
    assert "secret_pdf_key" not in prep_text
    assert "rubric" not in prep_text

    # GET problems
    prob_res = db_client.get(
        f"/api/v2/math-solutions/student-assignments/{sa_id}/problems",
        headers=headers,
    )
    assert prob_res.status_code == 200
    prob_text = prob_res.text
    assert "correct_answer" not in prob_text
    assert "SECRET" not in prob_text
    assert "storage_key" not in prob_text
    assert "rubric" not in prob_text

    # Next problem
    next_res = db_client.get(
        f"/api/v2/math-solutions/practice-sessions/{delivery_domain.practice_session.id}/next-problem",
        headers=headers,
    )
    if next_res.status_code == 200:
        next_text = next_res.text
        assert "correct_answer" not in next_text
        assert "SECRET" not in next_text
        assert "storage_key" not in next_text


def test_cache_control_headers_on_delivery_error_and_success(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers
) -> None:
    headers = auth_headers(delivery_domain.student_a)

    # 200 Success
    res_200 = db_client.get(
        f"/api/v2/math-solutions/student-assignments/{delivery_domain.student_assignment_a.id}/problems",
        headers=headers,
    )
    assert res_200.headers.get("Cache-Control") == "no-store"
    assert res_200.headers.get("Pragma") == "no-cache"

    # 404 Not Found
    fake_id = uuid4()
    res_404 = db_client.get(
        f"/api/v2/math-solutions/student-assignments/{fake_id}/problems",
        headers=headers,
    )
    assert res_404.status_code == 404
    assert res_404.headers.get("Cache-Control") == "no-store"
    assert res_404.headers.get("Pragma") == "no-cache"

    # 403 Forbidden (student B on A's assignment)
    headers_b = auth_headers(delivery_domain.student_b)
    res_403 = db_client.post(
        f"/api/v2/math-solutions/student-assignments/{delivery_domain.student_assignment_b.id}/prepare",
        headers=headers_b,
    )
    assert res_403.status_code == 403
    assert res_403.headers.get("Cache-Control") == "no-store"
    assert res_403.headers.get("Pragma") == "no-cache"


# =========================================================================
# 5. FIX-01 Deadline Enforcement Tests (Before, At, After, Prepared)
# =========================================================================

def test_deadline_enforcement_lifecycle(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers, db_session: Session
) -> None:
    headers_a = auth_headers(delivery_domain.student_a)
    sa_id = delivery_domain.student_assignment_a.id
    prepare_url = f"/api/v2/math-solutions/student-assignments/{sa_id}/prepare"
    problems_url = f"/api/v2/math-solutions/student-assignments/{sa_id}/problems"

    # Case 1: Trước hạn (now < due_at) -> Prepare succeeds, is_read_only is False
    now = datetime.now(timezone.utc)
    delivery_domain.assignment.start_at = now - timedelta(hours=2)
    delivery_domain.assignment.due_at = now + timedelta(hours=2)
    db_session.commit()

    res1 = db_client.post(prepare_url, headers=headers_a)
    assert res1.status_code == 200
    assert res1.json()["item_count"] == 2
    assert res1.json()["problems"][0]["is_read_only"] is False

    # Case 2: Đúng hạn (exact deadline: now == due_at)
    # The condition `_utc(assignment.due_at) < now` evaluates False when now == due_at,
    # so submission, mutation and prepare are accepted at exact due_at.
    # Relative to the fixture window so this boundary test remains valid over time.
    exact_deadline = now + timedelta(hours=1)
    delivery_domain.assignment.due_at = exact_deadline
    db_session.commit()

    q_id = str(delivery_domain.canonical_question.id)
    asq = db_session.scalar(
        select(AssignmentStudentQuestion).where(
            AssignmentStudentQuestion.student_assignment_id == sa_id,
            AssignmentStudentQuestion.question_id == delivery_domain.canonical_question.id,
        )
    )
    assert asq is not None

    with patch("app.math_solutions.service._now", return_value=exact_deadline):
        create_res = db_client.post(
            "/api/v2/math-solutions/attempts",
            json={
                "source_kind": "CANONICAL",
                "context_type": "CLASSROOM_ASSIGNMENT",
                "mode": "INDEPENDENT_SOLUTION",
                "create_idempotency_key": "deadline-exact-attempt",
                "question_id": q_id,
                "student_assignment_id": str(sa_id),
                "assignment_student_question_id": str(asq.id),
            },
            headers=headers_a,
        )
        assert create_res.status_code == 201
        attempt_id = create_res.json()["id"]

        # Mutation at exact deadline
        step_res = db_client.post(
            f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
            json={
                "expected_attempt_revision": 1,
                "client_action_id": str(uuid4()),
                "step_type": "CUSTOM",
                "content_latex": "f'(x)=3x^2-3",
            },
            headers=headers_a,
        )
        assert step_res.status_code == 201

    # Case 3: Sau hạn (now > due_at) trên bài CHƯA prepare
    past_assignment = Assignment(
        classroom_id=delivery_domain.classroom.id,
        subject_id=delivery_domain.subject.id,
        title="Quá hạn nộp",
        assignment_type=AssignmentType.SAME_SET,
        status=AssignmentStatus.PUBLISHED,
        question_count=1,
        start_at=now - timedelta(days=2),
        due_at=now - timedelta(minutes=5),
        created_by=delivery_domain.teacher.id,
    )
    db_session.add(past_assignment)
    db_session.flush()

    sa_past = StudentAssignment(
        assignment_id=past_assignment.id,
        student_id=delivery_domain.student_profile_a.id,
        status=StudentAssignmentStatus.NOT_STARTED,
        assigned_at=now - timedelta(days=2),
    )
    db_session.add(sa_past)
    db_session.commit()

    # Calling prepare after deadline returns 409 ASSIGNMENT_OUTSIDE_WINDOW
    res_past = db_client.post(
        f"/api/v2/math-solutions/student-assignments/{sa_past.id}/prepare",
        headers=headers_a,
    )
    assert res_past.status_code == 409
    assert res_past.json()["error"]["code"] == "ASSIGNMENT_OUTSIDE_WINDOW"

    # Case 4: Bài ĐÃ prepare trước hạn, sau hạn học sinh vào lại
    after_deadline = exact_deadline + timedelta(seconds=1)

    with patch("app.math_solutions.service._now", return_value=after_deadline):
        # 4a: Calling prepare again after deadline is rejected with 409 ASSIGNMENT_OUTSIDE_WINDOW
        prep_after = db_client.post(prepare_url, headers=headers_a)
        assert prep_after.status_code == 409
        assert prep_after.json()["error"]["code"] == "ASSIGNMENT_OUTSIDE_WINDOW"

        # 4b: Calling GET /problems succeeds with 200 and is_read_only is True
        prob_after = db_client.get(problems_url, headers=headers_a)
        assert prob_after.status_code == 200
        for p in prob_after.json():
            assert p["is_read_only"] is True

        # 4c: Calling GET /attempts/{attempt_id}/problem returns is_read_only = True
        att_prob_after = db_client.get(
            f"/api/v2/math-solutions/attempts/{attempt_id}/problem",
            headers=headers_a,
        )
        assert att_prob_after.status_code == 200
        assert att_prob_after.json()["is_read_only"] is True

        # 4d: All mutations after deadline are rejected with 409 ASSIGNMENT_OUTSIDE_WINDOW
        step_after = db_client.post(
            f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
            json={
                "expected_attempt_revision": 2,
                "client_action_id": str(uuid4()),
                "step_type": "CUSTOM",
                "content_latex": "f'(x)>0",
            },
            headers=headers_a,
        )
        assert step_after.status_code == 409
        assert step_after.json()["error"]["code"] == "ASSIGNMENT_OUTSIDE_WINDOW"

        submit_after = db_client.post(
            f"/api/v2/math-solutions/attempts/{attempt_id}/submit",
            json={
                "expected_attempt_revision": 2,
                "client_action_id": str(uuid4()),
            },
            headers=headers_a,
        )
        assert submit_after.status_code == 409
        assert submit_after.json()["error"]["code"] == "ASSIGNMENT_OUTSIDE_WINDOW"


# =========================================================================
# 6. FIX-06 Assignment Not Open Yet (start_at in future)
# =========================================================================

def test_assignment_not_open_yet(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers, db_session: Session
) -> None:
    headers_a = auth_headers(delivery_domain.student_a)
    future_start = datetime.now(timezone.utc) + timedelta(days=2)
    delivery_domain.assignment.start_at = future_start
    delivery_domain.assignment.due_at = future_start + timedelta(days=5)
    db_session.commit()

    sa_id = delivery_domain.student_assignment_a.id

    # POST prepare fails with ASSIGNMENT_NOT_OPEN
    prep_res = db_client.post(
        f"/api/v2/math-solutions/student-assignments/{sa_id}/prepare",
        headers=headers_a,
    )
    assert prep_res.status_code == 409
    assert prep_res.json()["error"]["code"] == "ASSIGNMENT_NOT_OPEN"


# =========================================================================
# 7. FIX-06 Canonical Question Revoked or Subject Mismatched
# =========================================================================

def test_canonical_question_revoked_or_subject_mismatch(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers, db_session: Session
) -> None:
    headers_a = auth_headers(delivery_domain.student_a)
    sa_id = delivery_domain.student_assignment_a.id

    # 1. Prepare first
    prep_res = db_client.post(
        f"/api/v2/math-solutions/student-assignments/{sa_id}/prepare",
        headers=headers_a,
    )
    assert prep_res.status_code == 200

    # 2. Revoke canonical question APPROVED status
    delivery_domain.canonical_question.status = QuestionStatus.DRAFT
    db_session.commit()

    # GET problems must fail with CANONICAL_QUESTION_INVALID
    prob_res = db_client.get(
        f"/api/v2/math-solutions/student-assignments/{sa_id}/problems",
        headers=headers_a,
    )
    assert prob_res.status_code == 409
    assert prob_res.json()["error"]["code"] == "CANONICAL_QUESTION_INVALID"

    # 3. Restore status but mismatch subject
    delivery_domain.canonical_question.status = QuestionStatus.APPROVED
    other_subj = Subject(code="OTHER-MATH-12", name="Other Subject", grade_level=12)
    db_session.add(other_subj)
    db_session.flush()
    delivery_domain.canonical_question.subject_id = other_subj.id
    db_session.commit()

    prob_res2 = db_client.get(
        f"/api/v2/math-solutions/student-assignments/{sa_id}/problems",
        headers=headers_a,
    )
    assert prob_res2.status_code == 422
    assert prob_res2.json()["error"]["code"] == "SUBJECT_MISMATCH"


# =========================================================================
# 8. FIX-02 PDF Snapshot Integrity Negative Cases
# =========================================================================

def test_pdf_snapshot_integrity_negative_cases(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers, db_session: Session
) -> None:
    headers_a = auth_headers(delivery_domain.student_a)
    sa_id = delivery_domain.student_assignment_a.id

    # Prepare first
    prep_res = db_client.post(
        f"/api/v2/math-solutions/student-assignments/{sa_id}/prepare",
        headers=headers_a,
    )
    assert prep_res.status_code == 200

    smi = db_session.scalar(
        select(StudentAssignmentMaterialItem).where(
            StudentAssignmentMaterialItem.student_assignment_id == sa_id
        )
    )
    assert smi is not None

    # Negative 1: Snapshot belongs to a different assignment
    other_assign = Assignment(
        classroom_id=delivery_domain.classroom.id,
        subject_id=delivery_domain.subject.id,
        title="Other Assignment",
        assignment_type=AssignmentType.SAME_SET,
        status=AssignmentStatus.PUBLISHED,
        question_count=1,
        created_by=delivery_domain.teacher.id,
    )
    db_session.add(other_assign)
    db_session.flush()

    orig_assign_id = delivery_domain.material_snapshot.assignment_id
    delivery_domain.material_snapshot.assignment_id = other_assign.id
    db_session.commit()

    res_mismatch = db_client.get(
        f"/api/v2/math-solutions/student-assignments/{sa_id}/problems",
        headers=headers_a,
    )
    assert res_mismatch.status_code == 409
    assert res_mismatch.json()["error"]["code"] == "MATERIAL_SNAPSHOT_MISMATCH"

    # Restore assignment_id
    delivery_domain.material_snapshot.assignment_id = orig_assign_id
    db_session.commit()

    # Negative 2: Mismatched item origin
    orig_tmi_id = smi.teacher_material_item_id
    fake_tmi = TeacherMaterialItem(
        teacher_material_id=delivery_domain.teacher_material.id,
        order_index=99,
        page_start=10,
        page_end=10,
        content="Fake origin",
        content_hash="c" * 64,
        extraction_status=MaterialItemExtractionStatus.READY,
        evaluation_mode=MaterialEvaluationMode.OPEN_RESPONSE,
    )
    db_session.add(fake_tmi)
    db_session.flush()
    smi.teacher_material_item_id = fake_tmi.id
    db_session.commit()

    res_item_mismatch = db_client.get(
        f"/api/v2/math-solutions/student-assignments/{sa_id}/problems",
        headers=headers_a,
    )
    assert res_item_mismatch.status_code == 409
    assert res_item_mismatch.json()["error"]["code"] == "MATERIAL_ITEM_SNAPSHOT_MISMATCH"

    # Restore tmi
    smi.teacher_material_item_id = orig_tmi_id
    db_session.commit()

    # Negative 3: Origin material from a different classroom
    other_class = Classroom(
        name="12A2 Other Class",
        academic_year="2026-2027",
        created_by=delivery_domain.teacher.id,
        grade_level=12,
    )
    db_session.add(other_class)
    db_session.flush()
    orig_class_id = delivery_domain.teacher_material.classroom_id
    delivery_domain.teacher_material.classroom_id = other_class.id
    db_session.commit()

    res_source_cross = db_client.get(
        f"/api/v2/math-solutions/student-assignments/{sa_id}/problems",
        headers=headers_a,
    )
    assert res_source_cross.status_code == 403
    assert res_source_cross.json()["error"]["code"] == "MATERIAL_SOURCE_NOT_ACCESSIBLE"

    # Restore classroom
    delivery_domain.teacher_material.classroom_id = orig_class_id
    db_session.commit()

    # Negative 4: Snapshot with empty content
    orig_content = delivery_domain.material_snapshot.content
    delivery_domain.material_snapshot.content = ""
    db_session.commit()

    res_empty = db_client.get(
        f"/api/v2/math-solutions/student-assignments/{sa_id}/problems",
        headers=headers_a,
    )
    assert res_empty.status_code == 409
    assert res_empty.json()["error"]["code"] == "MATERIAL_SNAPSHOT_INVALID"

    # Restore content
    delivery_domain.material_snapshot.content = orig_content
    db_session.commit()


# =========================================================================
# 9. FIX-04 Transaction Safety (Rollback leaves no partial writes)
# =========================================================================

def test_transaction_safety_rollback_leaves_no_partial_writes(
    db_client: TestClient, delivery_domain: DeliveryDomain, auth_headers, db_session: Session
) -> None:
    headers_a = auth_headers(delivery_domain.student_a)
    now = datetime.now(timezone.utc)

    # Create a new assignment with a corrupted snapshot (empty content)
    corrupted_assignment = Assignment(
        classroom_id=delivery_domain.classroom.id,
        subject_id=delivery_domain.subject.id,
        title="Corrupted Assignment",
        assignment_type=AssignmentType.SAME_SET,
        status=AssignmentStatus.PUBLISHED,
        question_count=1,
        start_at=now - timedelta(hours=1),
        due_at=now + timedelta(days=2),
        created_by=delivery_domain.teacher.id,
    )
    db_session.add(corrupted_assignment)
    db_session.flush()

    corrupt_ami = AssignmentMaterialItem(
        assignment_id=corrupted_assignment.id,
        teacher_material_id=delivery_domain.teacher_material.id,
        teacher_material_item_id=delivery_domain.teacher_material_item.id,
        order_index=0,
        content="",  # Empty / corrupted content!
        evaluation_mode=MaterialEvaluationMode.TEACHER_REVIEW,
    )
    db_session.add(corrupt_ami)
    db_session.flush()

    sa_corrupt = StudentAssignment(
        assignment_id=corrupted_assignment.id,
        student_id=delivery_domain.student_profile_a.id,
        status=StudentAssignmentStatus.NOT_STARTED,
        assigned_at=now - timedelta(hours=1),
    )
    db_session.add(sa_corrupt)
    db_session.commit()

    # Calling prepare must fail with MATERIAL_SNAPSHOT_INVALID
    prep_res = db_client.post(
        f"/api/v2/math-solutions/student-assignments/{sa_corrupt.id}/prepare",
        headers=headers_a,
    )
    assert prep_res.status_code == 409
    assert prep_res.json()["error"]["code"] == "MATERIAL_SNAPSHOT_INVALID"

    # Verify atomic rollback: sa.status is STILL NOT_STARTED, zero rows in DB
    db_session.expire_all()
    reloaded_sa = db_session.get(StudentAssignment, sa_corrupt.id)
    assert reloaded_sa.status == StudentAssignmentStatus.NOT_STARTED
    assert reloaded_sa.started_at is None

    smi_count = db_session.scalar(
        select(func.count(StudentAssignmentMaterialItem.id)).where(
            StudentAssignmentMaterialItem.student_assignment_id == sa_corrupt.id
        )
    )
    assert smi_count == 0

    # Fix the corruption and retry prepare
    corrupt_ami.content = "Fixed valid mathematical problem content"
    db_session.commit()

    retry_res = db_client.post(
        f"/api/v2/math-solutions/student-assignments/{sa_corrupt.id}/prepare",
        headers=headers_a,
    )
    assert retry_res.status_code == 200
    assert retry_res.json()["status"] == "IN_PROGRESS"
    assert retry_res.json()["item_count"] == 1


# =========================================================================
# 10. FIX-03 PostgreSQL Concurrency Integration Tests
# =========================================================================

def test_postgres_concurrency_prepare_two_transactions(postgres_engine: Engine) -> None:
    """Verifies that two concurrent transactions calling prepare for the same StudentAssignment
    materialize exactly one set of items without duplicates or deadlocks using PostgreSQL row locking."""
    # Setup domain on PostgreSQL
    with Session(postgres_engine, expire_on_commit=False) as db:
        teacher = User(email=f"pg-teach-{uuid4().hex}@test.com", full_name="PG Teacher", role=Role.TEACHER, password_hash="test")
        student = User(email=f"pg-stud-{uuid4().hex}@test.com", full_name="PG Student", role=Role.STUDENT, password_hash="test")
        db.add_all([teacher, student])
        db.flush()

        sp = StudentProfile(user_id=student.id)
        db.add(sp)
        db.flush()

        subj = Subject(code=f"PG-M-{uuid4().hex[:6].upper()}", name="PG Math", grade_level=12)
        db.add(subj)
        db.flush()

        classroom = Classroom(name="PG 12A1", academic_year="2026-2027", created_by=teacher.id, grade_level=12)
        db.add(classroom)
        db.flush()

        db.add(StudentEnrollment(classroom_id=classroom.id, student_id=sp.id, status=EnrollmentStatus.ACTIVE))

        now = datetime.now(timezone.utc)
        assignment = Assignment(
            classroom_id=classroom.id,
            subject_id=subj.id,
            title="PG Concurrency Assignment",
            assignment_type=AssignmentType.SAME_SET,
            status=AssignmentStatus.PUBLISHED,
            question_count=2,
            start_at=now - timedelta(hours=1),
            due_at=now + timedelta(days=2),
            created_by=teacher.id,
        )
        db.add(assignment)
        db.flush()

        # Add 2 canonical questions to assignment
        q1 = Question(subject_id=subj.id, content="PG Question 1", question_type=QuestionType.OPEN_RESPONSE, difficulty=0.5, status=QuestionStatus.APPROVED, created_by=teacher.id, source_type="TEST", exam_weight=0.5, explanation="PG Question 1")
        q2 = Question(subject_id=subj.id, content="PG Question 2", question_type=QuestionType.OPEN_RESPONSE, difficulty=0.5, status=QuestionStatus.APPROVED, created_by=teacher.id, source_type="TEST", exam_weight=0.5, explanation="PG Question 2")
        db.add_all([q1, q2])
        db.flush()

        db.add_all([
            AssignmentQuestion(assignment_id=assignment.id, question_id=q1.id, order_index=0),
            AssignmentQuestion(assignment_id=assignment.id, question_id=q2.id, order_index=1),
        ])
        db.flush()

        sa = StudentAssignment(
            assignment_id=assignment.id,
            student_id=sp.id,
            status=StudentAssignmentStatus.NOT_STARTED,
            assigned_at=now - timedelta(hours=1),
        )
        db.add(sa)
        db.commit()

        student_user_id = student.id
        student_assignment_id = sa.id

    barrier = Barrier(2)

    def prepare_worker():
        with Session(postgres_engine, expire_on_commit=False) as db:
            barrier.wait(timeout=10)
            svc = MathSolutionService(db)
            return svc.prepare_student_assignment(student_user_id, student_assignment_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(prepare_worker)
        f2 = executor.submit(prepare_worker)
        r1 = f1.result(timeout=15)
        r2 = f2.result(timeout=15)

    assert r1.status == "IN_PROGRESS"
    assert r2.status == "IN_PROGRESS"
    assert r1.item_count == 2
    assert r2.item_count == 2

    # Verify exactly 2 rows exist in DB (no duplicates!)
    with Session(postgres_engine) as db:
        count = db.scalar(
            select(func.count(AssignmentStudentQuestion.id)).where(
                AssignmentStudentQuestion.student_assignment_id == student_assignment_id
            )
        )
        assert count == 2
        reloaded = db.get(StudentAssignment, student_assignment_id)
        assert reloaded.status == StudentAssignmentStatus.IN_PROGRESS

