from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_gateway
from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.core.config import Settings
from app.hints.models import HintLevel, QuestionHint
from app.practice.schemas import PracticeSessionCreate
from app.practice.service import PracticeService
from app.users.models import User
from tests.practice.conftest import PracticeContent


def test_hint_api_returns_predefined_hint_and_enforces_owner(
    db_app: FastAPI,
    db_client: TestClient,
    db_session: Session,
    settings: Settings,
    practice_students: tuple[User, User],
    practice_bearer,
    practice_content: PracticeContent,
) -> None:
    owner, outsider = practice_students
    practice = PracticeService(db_session).create_session(
        owner,
        PracticeSessionCreate(
            subject_id=practice_content.subject.id,
            session_type="PRACTICE",
            problem_type_ids=[practice_content.problem_type.id],
            concept_ids=[practice_content.concept.id],
        ),
    )
    question = PracticeService(db_session).get_next_question(owner, practice.id)
    db_session.add(
        QuestionHint(
            question_id=question.id,
            hint_level=HintLevel.LEVEL_1,
            content="Recall the relevant mapped rule.",
        )
    )
    db_session.commit()
    provider = MockAIProvider()
    db_app.dependency_overrides[get_ai_gateway] = lambda: AIGateway(
        provider=provider, settings=settings
    )

    denied = db_client.post(
        f"/practice/questions/{question.id}/hint",
        json={
            "practice_session_id": str(practice.id),
            "current_hint_level": "LEVEL_1",
        },
        headers=practice_bearer(outsider),
    )
    assert denied.status_code == 403

    response = db_client.post(
        f"/practice/questions/{question.id}/hint",
        json={
            "practice_session_id": str(practice.id),
            "current_hint_level": "LEVEL_1",
        },
        headers=practice_bearer(owner),
    )

    assert response.status_code == 200, response.text
    assert response.json()["hint_level"] == "LEVEL_1"
    assert response.json()["hint_count"] == 1
    assert response.json()["hint_source"] == "PREDEFINED"
    assert provider.call_count == 0
