from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.curriculum.models import Chapter, LearningOutcome, ProblemType, Topic
from app.concepts.models import Concept
from app.subjects.models import Subject
from app.users.models import Role, User
from tests.questions.test_api import create_question, multiple_choice_payload
from tests.questions.test_import import import_record, preview_json

UserFactory = Callable[[Role, str], User]
BearerFactory = Callable[[User], dict[str, str]]


def classification(
    session: Session, subject: Subject
) -> tuple[ProblemType, LearningOutcome]:
    chapter = Chapter(
        subject_id=subject.id, code="Q_CHAPTER", name="Question Chapter", order_index=1
    )
    session.add(chapter)
    session.flush()
    topic = Topic(chapter_id=chapter.id, code="Q_TOPIC", name="Question Topic", order_index=1)
    session.add(topic)
    session.flush()
    problem = ProblemType(
        topic_id=topic.id,
        code="Q_PROBLEM_TYPE",
        name="Question Problem Type",
        order_index=1,
        is_active=True,
    )
    outcome = LearningOutcome(
        subject_id=subject.id,
        code="Q_OUTCOME",
        description="Question learning outcome",
        grade_level=12,
        order_index=1,
    )
    session.add_all([problem, outcome])
    session.commit()
    return problem, outcome


def test_question_maps_and_filters_problem_type_concept_and_learning_outcome(
    db_client: TestClient,
    db_session: Session,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "classification@example.com")
    subject, derivative, function = math_content
    problem, outcome = classification(db_session, subject)
    payload = multiple_choice_payload(subject, derivative, function)
    payload.update({
        "source_year": 2025,
        "cognitive_level": "APPLY",
        "problem_types": [{
            "problem_type_id": str(problem.id),
            "weight": 1.0,
            "is_primary": True,
        }],
        "learning_outcomes": [{
            "learning_outcome_id": str(outcome.id),
            "weight": 1.0,
        }],
    })
    headers = question_bearer(teacher)
    created = create_question(db_client, headers, payload)
    assert created["source_year"] == 2025 and created["cognitive_level"] == "APPLY"
    assert created["problem_types"][0]["problem_type_id"] == str(problem.id)
    assert created["learning_outcomes"][0]["learning_outcome_id"] == str(outcome.id)

    response = db_client.get("/questions", params={
        "problem_type": str(problem.id),
        "learning_outcome": str(outcome.id),
        "concept": str(derivative.id),
        "cognitive_level": "APPLY",
    }, headers=headers)
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [created["id"]]


def test_question_import_validates_problem_type_and_learning_outcome_codes(
    db_client: TestClient,
    db_session: Session,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "classification-import@example.com")
    subject, derivative, _ = math_content
    problem, outcome = classification(db_session, subject)
    valid = import_record(subject, derivative, content="Classified import")
    valid.update({
        "problem_types": [{"code": problem.code, "weight": 1.0, "is_primary": True}],
        "learning_outcomes": [{"code": outcome.code, "weight": 1.0}],
        "cognitive_level": "ANALYZE",
        "source_year": 2024,
    })
    invalid_problem = {**valid, "content": "Bad problem", "problem_types": [{
        "code": "MISSING_PROBLEM", "weight": 1.0, "is_primary": True
    }]}
    invalid_outcome = {**valid, "content": "Bad outcome", "learning_outcomes": [{
        "code": "MISSING_OUTCOME", "weight": 1.0
    }]}
    response = preview_json(
        db_client,
        question_bearer(teacher),
        [valid, invalid_problem, invalid_outcome],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["report"]["valid"] == 1 and body["report"]["invalid"] == 2
    assert "MISSING_PROBLEM" in body["rows"][1]["errors"][0]
    assert "MISSING_OUTCOME" in body["rows"][2]["errors"][0]

    confirmed = db_client.post(
        f"/questions/import/{body['batch_id']}/confirm",
        headers=question_bearer(teacher),
    )
    imported = confirmed.json()["rows"][0]["data"]
    assert imported["problem_types"][0]["code"] == problem.code
    assert imported["learning_outcomes"][0]["code"] == outcome.code
