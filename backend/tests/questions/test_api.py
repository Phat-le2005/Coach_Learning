from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.questions.models import Question, QuestionConcept, QuestionOption, QuestionStatus, QuestionType
from app.questions.service import QuestionService
from app.subjects.models import Subject
from app.users.models import Role, User

UserFactory = Callable[[Role, str], User]
BearerFactory = Callable[[User], dict[str, str]]


def multiple_choice_payload(subject: Subject, derivative: Concept, function: Concept) -> dict[str, object]:
    return {
        "subject_id": str(subject.id),
        "content": "The derivative of x squared is?",
        "question_type": "MULTIPLE_CHOICE",
        "difficulty": 0.4,
        "correct_answer": "B",
        "explanation": "Apply the power rule.",
        "source_type": "teacher",
        "source_reference": "Lesson 1",
        "exam_weight": 0.6,
        "options": [
            {"label": "a", "content": "x", "order_index": 0},
            {"label": "b", "content": "2x", "order_index": 1},
        ],
        "concepts": [
            {"concept_id": str(derivative.id), "weight": 0.7},
            {"concept_id": str(function.id), "weight": 0.3},
        ],
    }


def create_question(
    client: TestClient, headers: dict[str, str], payload: dict[str, object]
) -> dict[str, object]:
    response = client.post("/questions", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_teacher_creates_draft_with_options_and_weighted_concepts(
    db_client: TestClient,
    db_session: Session,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "teacher@example.com")
    subject, derivative, function = math_content
    created = create_question(
        db_client, question_bearer(teacher), multiple_choice_payload(subject, derivative, function)
    )
    assert created["status"] == "DRAFT"
    assert created["created_by"] == str(teacher.id)
    assert created["source_type"] == "TEACHER"
    assert [option["label"] for option in created["options"]] == ["A", "B"]
    assert {item["concept_id"]: item["weight"] for item in created["concepts"]} == {
        str(derivative.id): 0.7, str(function.id): 0.3,
    }
    question_id = UUID(str(created["id"]))
    assert db_session.scalar(select(func.count()).select_from(Question).where(Question.id == question_id)) == 1
    assert db_session.scalar(select(func.count()).select_from(QuestionOption).where(QuestionOption.question_id == question_id)) == 2
    assert db_session.scalar(select(func.count()).select_from(QuestionConcept).where(QuestionConcept.question_id == question_id)) == 2


@pytest.mark.parametrize("field,value", [
    ("difficulty", -0.01), ("difficulty", 1.01),
    ("exam_weight", -0.01), ("exam_weight", 1.01),
])
def test_create_rejects_out_of_range_scores(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
    field: str,
    value: float,
) -> None:
    teacher = question_user_factory(Role.TEACHER, f"{field}-{value}@example.com")
    payload = multiple_choice_payload(*math_content)
    payload[field] = value
    response = db_client.post("/questions", json=payload, headers=question_bearer(teacher))
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_validates_option_shape_and_concept_weights(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "shape@example.com")
    headers = question_bearer(teacher)
    subject, derivative, function = math_content
    too_heavy = multiple_choice_payload(subject, derivative, function)
    too_heavy["concepts"] = [
        {"concept_id": str(derivative.id), "weight": 0.8},
        {"concept_id": str(function.id), "weight": 0.4},
    ]
    assert db_client.post("/questions", json=too_heavy, headers=headers).status_code == 422
    no_options = multiple_choice_payload(subject, derivative, function)
    no_options["options"] = []
    assert db_client.post("/questions", json=no_options, headers=headers).status_code == 422
    true_false = multiple_choice_payload(subject, derivative, function)
    true_false["question_type"] = "TRUE_FALSE"
    assert db_client.post("/questions", json=true_false, headers=headers).status_code == 422


def test_create_rejects_missing_or_cross_subject_concepts(
    db_client: TestClient,
    db_session: Session,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "concept-check@example.com")
    headers = question_bearer(teacher)
    subject, derivative, function = math_content
    payload = multiple_choice_payload(subject, derivative, function)
    payload["concepts"] = [{"concept_id": str(uuid4()), "weight": 0.5}]
    missing = db_client.post("/questions", json=payload, headers=headers)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "CONCEPT_NOT_FOUND"
    other_subject = Subject(code="PHYSICS12-Q", name="Physics", grade_level=12)
    db_session.add(other_subject)
    db_session.flush()
    other = Concept(
        subject_id=other_subject.id, code="VECTOR-P", name="Vector P",
        description="Physics vector", grade_level=12, order_index=0,
    )
    db_session.add(other)
    db_session.commit()
    payload["concepts"] = [{"concept_id": str(other.id), "weight": 0.5}]
    mismatch = db_client.post("/questions", json=payload, headers=headers)
    assert mismatch.status_code == 422 and mismatch.json()["error"]["code"] == "CONCEPT_SUBJECT_MISMATCH"


def test_teacher_updates_own_draft_and_replaces_children(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "editor@example.com")
    headers = question_bearer(teacher)
    subject, derivative, function = math_content
    created = create_question(db_client, headers, multiple_choice_payload(subject, derivative, function))
    response = db_client.patch(
        f"/questions/{created['id']}",
        json={
            "content": "Updated question",
            "correct_answer": "C",
            "options": [
                {"label": "B", "content": "wrong", "order_index": 0},
                {"label": "C", "content": "correct", "order_index": 1},
            ],
            "concepts": [{"concept_id": str(derivative.id), "weight": 0.8}],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["content"] == "Updated question"
    assert [item["label"] for item in response.json()["options"]] == ["B", "C"]
    assert response.json()["concepts"] == [{"concept_id": str(derivative.id), "weight": 0.8}]


def test_review_and_approval_workflow_enforces_roles_and_state(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "workflow@example.com")
    admin = question_user_factory(Role.ADMIN, "admin@example.com")
    teacher_headers, admin_headers = question_bearer(teacher), question_bearer(admin)
    created = create_question(db_client, teacher_headers, multiple_choice_payload(*math_content))
    forbidden = db_client.post(f"/questions/{created['id']}/approve", headers=teacher_headers)
    assert forbidden.status_code == 403
    review = db_client.post(f"/questions/{created['id']}/submit-review", headers=teacher_headers)
    assert review.status_code == 200 and review.json()["status"] == "REVIEW"
    locked = db_client.patch(f"/questions/{created['id']}", json={"difficulty": 0.5}, headers=teacher_headers)
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "QUESTION_NOT_EDITABLE"
    approved = db_client.post(f"/questions/{created['id']}/approve", headers=admin_headers)
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED"
    duplicate = db_client.post(f"/questions/{created['id']}/approve", headers=admin_headers)
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "INVALID_QUESTION_TRANSITION"
    archived = db_client.patch(
        f"/questions/{created['id']}", json={"status": "ARCHIVED"}, headers=admin_headers
    )
    assert archived.status_code == 200 and archived.json()["status"] == "ARCHIVED"


@pytest.mark.parametrize("question_type,answer", [
    (QuestionType.MULTIPLE_CHOICE, None),
    (QuestionType.TRUE_FALSE, "MAYBE"),
    (QuestionType.SHORT_ANSWER, None),
])
def test_submit_review_rejects_incomplete_objective_question(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
    question_type: QuestionType,
    answer: str | None,
) -> None:
    teacher = question_user_factory(Role.TEACHER, f"ready-{question_type.value.lower()}@example.com")
    subject, derivative, function = math_content
    payload = multiple_choice_payload(subject, derivative, function)
    payload["question_type"] = question_type.value
    payload["correct_answer"] = answer
    if question_type != QuestionType.MULTIPLE_CHOICE:
        payload["options"] = []
    created = create_question(db_client, question_bearer(teacher), payload)
    response = db_client.post(
        f"/questions/{created['id']}/submit-review", headers=question_bearer(teacher)
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "QUESTION_NOT_READY"


def test_visibility_uses_creator_and_approved_status(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    owner = question_user_factory(Role.TEACHER, "owner@example.com")
    outsider = question_user_factory(Role.TEACHER, "outsider@example.com")
    admin = question_user_factory(Role.ADMIN, "visibility-admin@example.com")
    owner_headers = question_bearer(owner)
    created = create_question(db_client, owner_headers, multiple_choice_payload(*math_content))
    outsider_headers = question_bearer(outsider)
    assert db_client.get(f"/questions/{created['id']}", headers=outsider_headers).status_code == 403
    assert db_client.get("/questions", headers=outsider_headers).json() == []
    denied_patch = db_client.patch(
        f"/questions/{created['id']}", json={"difficulty": 0.8}, headers=outsider_headers
    )
    assert denied_patch.status_code == 403 and denied_patch.json()["error"]["code"] == "QUESTION_ACCESS_DENIED"
    assert len(db_client.get("/questions", headers=question_bearer(admin)).json()) == 1
    db_client.post(f"/questions/{created['id']}/submit-review", headers=owner_headers)
    db_client.post(f"/questions/{created['id']}/approve", headers=question_bearer(admin))
    assert db_client.get(f"/questions/{created['id']}", headers=outsider_headers).status_code == 200
    assert len(db_client.get("/questions", headers=outsider_headers).json()) == 1


def test_search_filters_all_supported_fields(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "filter@example.com")
    headers = question_bearer(teacher)
    subject, derivative, function = math_content
    expected = create_question(db_client, headers, multiple_choice_payload(subject, derivative, function))
    second_payload = {
        **multiple_choice_payload(subject, derivative, function),
        "content": "A function statement is true.",
        "question_type": "TRUE_FALSE", "difficulty": 0.9,
        "correct_answer": "TRUE", "options": [],
        "concepts": [{"concept_id": str(function.id), "weight": 0.5}],
    }
    create_question(db_client, headers, second_payload)
    params = {
        "subject": str(subject.id), "concept": str(derivative.id),
        "difficulty_min": 0.3, "difficulty_max": 0.5,
        "question_type": "MULTIPLE_CHOICE", "status": "DRAFT",
    }
    response = db_client.get("/questions", params=params, headers=headers)
    assert response.status_code == 200 and [item["id"] for item in response.json()] == [expected["id"]]
    invalid = db_client.get(
        "/questions", params={"difficulty_min": 0.8, "difficulty_max": 0.2}, headers=headers
    )
    assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "INVALID_DIFFICULTY_RANGE"


def test_learning_lookup_returns_only_approved_questions(
    db_session: Session,
    question_user_factory: UserFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "learning@example.com")
    admin = question_user_factory(Role.ADMIN, "learning-admin@example.com")
    subject, derivative, function = math_content
    from app.questions.schemas import QuestionCreate
    data = QuestionCreate.model_validate(multiple_choice_payload(subject, derivative, function))
    service = QuestionService(db_session)
    draft = service.create(teacher, data)
    with pytest.raises(ApplicationError) as error:
        service.get_approved_for_learning(draft.id)
    assert getattr(error.value, "code", None) == "APPROVED_QUESTION_NOT_FOUND"
    service.submit_review(teacher, draft.id)
    service.approve(admin, draft.id)
    assert service.get_approved_for_learning(draft.id).status == QuestionStatus.APPROVED


@pytest.mark.parametrize("role", [Role.STUDENT, Role.PARENT, Role.ADMIN])
def test_only_teacher_can_create(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
    role: Role,
) -> None:
    user = question_user_factory(role, f"create-{role.value.lower()}@example.com")
    response = db_client.post(
        "/questions", json=multiple_choice_payload(*math_content), headers=question_bearer(user)
    )
    assert response.status_code == 403


@pytest.mark.parametrize("role", [Role.STUDENT, Role.PARENT])
def test_students_and_parents_cannot_access_question_bank(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    role: Role,
) -> None:
    user = question_user_factory(role, f"read-{role.value.lower()}@example.com")
    headers = question_bearer(user)
    assert db_client.get("/questions", headers=headers).status_code == 403
    assert db_client.get(f"/questions/{uuid4()}", headers=headers).status_code == 403


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid"}])
def test_question_bank_requires_authentication(db_client: TestClient, headers: dict[str, str]) -> None:
    assert db_client.get("/questions", headers=headers).status_code == 401
    assert db_client.get(f"/questions/{uuid4()}", headers=headers).status_code == 401
