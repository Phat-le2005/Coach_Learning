from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.practice.models import PracticeSession, QuestionAttempt
from app.questions.models import Question
from app.users.models import User
from tests.practice.conftest import PracticeContent

BearerFactory = Callable[[User], dict[str, str]]


def create_session(
    client: TestClient,
    headers: dict[str, str],
    content: PracticeContent,
) -> dict[str, object]:
    response = client.post(
        "/practice/sessions",
        json={
            "subject_id": str(content.subject.id),
            "session_type": "PRACTICE",
            "problem_type_ids": [str(content.problem_type.id)],
            "concept_ids": [str(content.concept.id)],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit_answer(
    client: TestClient,
    headers: dict[str, str],
    session_id: str,
    question: Question,
    answer: str,
) -> object:
    return client.post(
        f"/practice/sessions/{session_id}/answer",
        json={
            "question_id": str(question.id),
            "student_answer": answer,
            "response_time_seconds": 12.5,
            "hint_count": 1,
        },
        headers=headers,
    )


def test_student_creates_owned_scoped_session_without_client_student_id(
    db_client: TestClient,
    db_session: Session,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    headers = practice_bearer(student)
    created = create_session(db_client, headers, practice_content)

    assert created["status"] == "ACTIVE"
    assert created["problem_type_ids"] == [str(practice_content.problem_type.id)]
    assert created["concept_ids"] == [str(practice_content.concept.id)]
    stored = db_session.get(PracticeSession, UUID(str(created["id"])))
    assert stored is not None
    assert str(stored.student_id) == created["student_id"]

    forged = db_client.post(
        "/practice/sessions",
        json={
            "student_id": str(uuid4()),
            "subject_id": str(practice_content.subject.id),
            "session_type": "PRACTICE",
        },
        headers=headers,
    )
    assert forged.status_code == 422


def test_other_student_cannot_access_or_answer_session(
    db_client: TestClient,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_content: PracticeContent,
) -> None:
    owner, outsider = practice_students
    created = create_session(db_client, practice_bearer(owner), practice_content)
    outsider_headers = practice_bearer(outsider)

    response = db_client.get(
        f"/practice/sessions/{created['id']}", headers=outsider_headers
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PRACTICE_SESSION_ACCESS_DENIED"
    answer = submit_answer(
        db_client,
        outsider_headers,
        str(created["id"]),
        practice_content.mcq,
        "B",
    )
    assert answer.status_code == 403


def test_next_question_returns_only_approved_fully_classified_question(
    db_client: TestClient,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    headers = practice_bearer(student)
    created = create_session(db_client, headers, practice_content)
    response = db_client.get(
        f"/practice/sessions/{created['id']}/next-question", headers=headers
    )
    assert response.status_code == 200, response.text
    approved_ids = {
        str(practice_content.mcq.id),
        str(practice_content.true_false.id),
        str(practice_content.short_answer.id),
        str(practice_content.open_response.id),
    }
    assert response.json()["id"] in approved_ids
    assert "correct_answer" not in response.json()
    assert response.json()["id"] not in {
        str(practice_content.draft.id),
        str(practice_content.unclassified.id),
    }


@pytest.mark.parametrize(
    ("question_name", "answer", "is_correct", "score"),
    [
        ("mcq", " b ", True, 1.0),
        ("true_false", " true ", True, 1.0),
        ("short_answer", "  ĐÁP   ÁN CHUẨN  ", True, 1.0),
        ("short_answer", "đáp án khác", False, 0.0),
    ],
)
def test_objective_answers_are_evaluated_deterministically(
    db_client: TestClient,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_content: PracticeContent,
    question_name: str,
    answer: str,
    is_correct: bool,
    score: float,
) -> None:
    student, _ = practice_students
    headers = practice_bearer(student)
    created = create_session(db_client, headers, practice_content)
    question = getattr(practice_content, question_name)
    response = submit_answer(db_client, headers, str(created["id"]), question, answer)
    assert response.status_code == 201, response.text
    assert response.json()["evaluation_status"] == "AUTO_EVALUATED"
    assert response.json()["is_correct"] is is_correct
    assert response.json()["score"] == score
    assert response.json()["attempt_number"] == 1


def test_open_response_is_saved_pending_evaluation(
    db_client: TestClient,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    headers = practice_bearer(student)
    created = create_session(db_client, headers, practice_content)
    response = submit_answer(
        db_client,
        headers,
        str(created["id"]),
        practice_content.open_response,
        "The derivative stays positive on the interval.",
    )
    assert response.status_code == 201, response.text
    assert response.json()["evaluation_status"] == "NEEDS_EVALUATION"
    assert response.json()["is_correct"] is None
    assert response.json()["score"] is None


def test_duplicate_answer_is_rejected_without_second_row(
    db_client: TestClient,
    db_session: Session,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    headers = practice_bearer(student)
    created = create_session(db_client, headers, practice_content)
    first = submit_answer(
        db_client, headers, str(created["id"]), practice_content.mcq, "B"
    )
    assert first.status_code == 201
    duplicate = submit_answer(
        db_client, headers, str(created["id"]), practice_content.mcq, "A"
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "QUESTION_ALREADY_ANSWERED"
    count = db_session.scalar(
        select(func.count()).select_from(QuestionAttempt).where(
            QuestionAttempt.practice_session_id == UUID(str(created["id"]))
        )
    )
    assert count == 1


@pytest.mark.parametrize("question_name", ["draft", "unclassified"])
def test_invalid_or_ineligible_question_is_rejected(
    db_client: TestClient,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_content: PracticeContent,
    question_name: str,
) -> None:
    student, _ = practice_students
    headers = practice_bearer(student)
    created = create_session(db_client, headers, practice_content)
    response = submit_answer(
        db_client,
        headers,
        str(created["id"]),
        getattr(practice_content, question_name),
        "TRUE",
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "QUESTION_NOT_ELIGIBLE"


def test_unknown_question_is_rejected(
    db_client: TestClient,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    headers = practice_bearer(student)
    created = create_session(db_client, headers, practice_content)
    response = db_client.post(
        f"/practice/sessions/{created['id']}/answer",
        json={"question_id": str(uuid4()), "student_answer": "B"},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "QUESTION_NOT_ELIGIBLE"

