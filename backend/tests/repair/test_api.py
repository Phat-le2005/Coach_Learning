from collections.abc import Callable
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.curriculum.models import ProblemType
from app.practice.models import PracticeSessionStatus
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.users.models import Role, User
from tests.practice.conftest import PracticeContent

BearerFactory = Callable[[User], dict[str, str]]


def test_repair_session_api_full_flow(
    db_client: TestClient,
    db_session: Session,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    headers = practice_bearer(student)

    # 1. Create a graded pool of APPROVED questions with low difficulties
    creator_id = practice_content.mcq.created_by
    subject_id = practice_content.subject.id
    pt_id = practice_content.problem_type.id
    c_id = practice_content.concept.id

    for i, diff in enumerate([0.10, 0.20, 0.30, 0.40]):
        q = Question(
            subject_id=subject_id,
            content=f"API Test question {i + 1}?",
            content_hash=f"{uuid4().hex}{uuid4().hex}",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=diff,
            correct_answer="A",
            explanation="Detailed explanation",
            source_type="BANK",
            exam_weight=1.0,
            status=QuestionStatus.APPROVED,
            created_by=creator_id,
        )
        db_session.add(q)
        db_session.flush()

        opt_a = QuestionOption(question_id=q.id, label="A", content="Correct", order_index=0)
        opt_b = QuestionOption(question_id=q.id, label="B", content="Incorrect", order_index=1)
        db_session.add_all([opt_a, opt_b])

        qpt = QuestionProblemType(question_id=q.id, problem_type_id=pt_id, is_primary=True, weight=1.0)
        qc = QuestionConcept(question_id=q.id, concept_id=c_id, weight=1.0)
        db_session.add_all([qpt, qc])

    db_session.commit()

    # 2. POST /repair/sessions - Start session
    payload = {
        "trigger": "LOW_PROBLEM_TYPE_MASTERY",
        "target_type": "PROBLEM_TYPE",
        "target_id": str(pt_id),
    }
    create_res = db_client.post("/repair/sessions", json=payload, headers=headers)
    assert create_res.status_code == 200, create_res.text
    session_data = create_res.json()
    session_id = session_data["id"]
    assert len(session_data["steps"]) == 5
    assert session_data["steps"][0]["role"] == "BRIEF_REVIEW"
    assert session_data["steps"][1]["role"] == "EASY_VERIFICATION"
    assert session_data["steps"][2]["role"] == "GUIDED_PRACTICE"
    assert session_data["steps"][3]["role"] == "MEDIUM_PRACTICE"
    assert session_data["steps"][4]["role"] == "FINAL_RECHECK"

    # 3. GET /repair/sessions/{session_id} - Fetch session
    get_res = db_client.get(f"/repair/sessions/{session_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == session_id

    # 4. Answer steps 2, 3, 4, 5
    for step_num in range(2, 6):
        ans_res = db_client.post(
            f"/repair/sessions/{session_id}/steps/{step_num}/answer",
            json={"student_answer": "A", "response_time_seconds": 15.0},
            headers=headers,
        )
        assert ans_res.status_code == 200, ans_res.text
        ans_data = ans_res.json()
        assert ans_data["is_correct"] is True
        assert ans_data["score"] == 1.0

    # 5. POST /repair/sessions/{session_id}/complete
    complete_res = db_client.post(
        f"/repair/sessions/{session_id}/complete",
        headers=headers,
    )
    assert complete_res.status_code == 200, complete_res.text
    eval_data = complete_res.json()
    assert eval_data["is_successful"] is True
    assert eval_data["average_score"] == 1.0
    assert eval_data["final_recheck_correct"] is True
    assert eval_data["resolution_status"] == "RESOLVED"
    assert eval_data["status"] == PracticeSessionStatus.COMPLETED.value


def test_repair_session_rbac_forbidden_for_teacher(
    db_client: TestClient,
    practice_content: PracticeContent,
    practice_user_factory: Callable[[Role, str], User],
    practice_bearer: BearerFactory,
) -> None:
    teacher = practice_user_factory(Role.TEACHER, "teacher-repair-test@example.com")
    headers = practice_bearer(teacher)

    payload = {
        "trigger": "LOW_PROBLEM_TYPE_MASTERY",
        "target_type": "PROBLEM_TYPE",
        "target_id": str(practice_content.problem_type.id),
    }
    # Teachers cannot start student repair sessions
    res = db_client.post("/repair/sessions", json=payload, headers=headers)
    assert res.status_code == 403
