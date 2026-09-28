from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.practice.models import QuestionAttempt, QuestionGroupAttempt
from app.questions.models import QuestionStatus
from app.users.models import Role, User
from tests.practice.conftest import PracticeContent
from tests.practice.group_helpers import create_group, create_other_subject


BearerFactory = Callable[[User], dict[str, str]]


def _session(
    client: TestClient,
    headers: dict[str, str],
    content: PracticeContent,
) -> str:
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
    return response.json()["id"]


def _payload(group_id: object) -> dict[str, object]:
    return {
        "question_group_id": str(group_id),
        "answers": [
            {"label": "a", "student_answer": "TRUE"},
            {"label": "b", "student_answer": "FALSE"},
            {"label": "c", "student_answer": "TRUE"},
            {"label": "d", "student_answer": "FALSE"},
        ],
        "response_time_seconds": 90.0,
    }


def test_next_item_api_prefers_group_then_returns_standalone(
    db_client: TestClient,
    db_session: Session,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    owner, _ = practice_students
    author = practice_user_factory(Role.TEACHER, "group-api-author@example.com")
    grouped = create_group(db_session, practice_content, author)
    headers = practice_bearer(owner)
    session_id = _session(db_client, headers, practice_content)

    first = db_client.get(
        f"/practice/sessions/{session_id}/next-item", headers=headers
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["item_type"] == "QUESTION_GROUP"
    assert body["question"] is None
    assert body["question_group"]["id"] == str(grouped.group.id)
    assert body["question_group"]["content"] == grouped.group.content
    assert body["question_group"]["difficulty"] == grouped.group.difficulty
    assert [item["label"] for item in body["question_group"]["items"]] == list("abcd")
    assert [item["question_id"] for item in body["question_group"]["items"]] == [
        str(child.id) for child in grouped.children
    ]
    assert [item["content"] for item in body["question_group"]["items"]] == [
        child.content for child in grouped.children
    ]
    forbidden = {"correct_answer", "is_correct", "answer_evidence", "source_answer_key"}
    serialized = str(body).casefold()
    assert all(field not in serialized for field in forbidden)

    submitted = db_client.post(
        f"/practice/sessions/{session_id}/group-answer",
        json=_payload(grouped.group.id),
        headers=headers,
    )
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["score"] == 1.0
    second = db_client.get(
        f"/practice/sessions/{session_id}/next-item", headers=headers
    )
    assert second.status_code == 200, second.text
    assert second.json()["item_type"] == "QUESTION"


def test_group_api_enforces_owner_for_fetch_and_submit(
    db_client: TestClient,
    db_session: Session,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    owner, outsider = practice_students
    author = practice_user_factory(Role.TEACHER, "group-api-owner@example.com")
    grouped = create_group(db_session, practice_content, author)
    session_id = _session(db_client, practice_bearer(owner), practice_content)
    outsider_headers = practice_bearer(outsider)

    fetched = db_client.get(
        f"/practice/sessions/{session_id}/next-item", headers=outsider_headers
    )
    submitted = db_client.post(
        f"/practice/sessions/{session_id}/group-answer",
        json=_payload(grouped.group.id),
        headers=outsider_headers,
    )
    assert fetched.status_code == 403
    assert submitted.status_code == 403
    assert fetched.json()["error"]["code"] == "PRACTICE_SESSION_ACCESS_DENIED"
    assert submitted.json()["error"]["code"] == "PRACTICE_SESSION_ACCESS_DENIED"


def test_admin_question_bank_can_inspect_and_list_group_children(
    db_client: TestClient,
    db_session: Session,
    practice_bearer: BearerFactory,
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    author = practice_user_factory(Role.TEACHER, "group-api-staff@example.com")
    admin = practice_user_factory(Role.ADMIN, "group-api-admin@example.com")
    grouped = create_group(db_session, practice_content, author)
    child = grouped.children[0]
    headers = practice_bearer(admin)

    fetched = db_client.get(f"/questions/{child.id}", headers=headers)
    listed = db_client.get(
        "/questions", params={"status": "APPROVED"}, headers=headers
    )

    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["id"] == str(child.id)
    assert listed.status_code == 200, listed.text
    assert str(child.id) in {row["id"] for row in listed.json()}


def test_cross_subject_child_group_is_not_served_or_accepted(
    db_client: TestClient,
    db_session: Session,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    owner, _ = practice_students
    author = practice_user_factory(Role.TEACHER, "group-api-cross@example.com")
    grouped = create_group(db_session, practice_content, author)
    grouped.children[0].subject_id = create_other_subject(db_session).id
    db_session.commit()
    headers = practice_bearer(owner)
    session_id = _session(db_client, headers, practice_content)

    next_item = db_client.get(
        f"/practice/sessions/{session_id}/next-item", headers=headers
    )
    submitted = db_client.post(
        f"/practice/sessions/{session_id}/group-answer",
        json=_payload(grouped.group.id),
        headers=headers,
    )

    assert next_item.status_code == 200
    assert next_item.json()["item_type"] == "QUESTION"
    assert submitted.status_code == 422
    assert submitted.json()["error"]["code"] == "QUESTION_GROUP_NOT_ELIGIBLE"
    assert db_session.scalar(select(func.count()).select_from(QuestionGroupAttempt)) == 0
    assert db_session.scalar(select(func.count()).select_from(QuestionAttempt)) == 0


def test_group_answer_api_rejects_invalid_shape_before_writes(
    db_client: TestClient,
    db_session: Session,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    owner, _ = practice_students
    author = practice_user_factory(Role.TEACHER, "group-api-shape@example.com")
    grouped = create_group(db_session, practice_content, author)
    headers = practice_bearer(owner)
    session_id = _session(db_client, headers, practice_content)
    invalid = _payload(grouped.group.id)
    invalid["answers"] = [
        {"label": "a", "student_answer": "TRUE"},
        {"label": "a", "student_answer": "FALSE"},
        {"label": "c", "student_answer": "TRUE"},
        {"label": "d", "student_answer": "FALSE"},
    ]

    response = db_client.post(
        f"/practice/sessions/{session_id}/group-answer",
        json=invalid,
        headers=headers,
    )
    assert response.status_code == 422
    assert db_session.scalar(select(func.count()).select_from(QuestionGroupAttempt)) == 0
    assert db_session.scalar(select(func.count()).select_from(QuestionAttempt)) == 0


def test_next_item_returns_stable_empty_error(
    db_client: TestClient,
    db_session: Session,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_content: PracticeContent,
) -> None:
    owner, _ = practice_students
    for question in (
        practice_content.mcq,
        practice_content.true_false,
        practice_content.short_answer,
        practice_content.open_response,
    ):
        question.status = QuestionStatus.DRAFT
    db_session.commit()
    headers = practice_bearer(owner)
    session_id = _session(db_client, headers, practice_content)

    response = db_client.get(
        f"/practice/sessions/{session_id}/next-item", headers=headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NO_AVAILABLE_PRACTICE_ITEM"
