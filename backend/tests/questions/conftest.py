from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.concepts.models import Concept
from app.core.config import Settings
from app.subjects.models import Subject
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

QUESTION_TEST_PASSWORD = "Synthetic-Question-Test-Password-2026!"


@pytest.fixture
def question_user_factory(db_session: Session) -> Callable[[Role, str], User]:
    def create(role: Role, email: str) -> User:
        return UserService(db_session).create_user(UserCreate(
            email=email,
            password=QUESTION_TEST_PASSWORD,
            full_name=f"{role.value.title()} User",
            role=role,
        ))

    return create


@pytest.fixture
def question_bearer(
    db_session: Session, settings: Settings
) -> Callable[[User], dict[str, str]]:
    def headers(user: User) -> dict[str, str]:
        pair = AuthService(db_session, settings).login(
            LoginRequest(email=user.email, password=QUESTION_TEST_PASSWORD)
        )
        return {"Authorization": f"Bearer {pair.access_token}"}

    return headers


@pytest.fixture
def math_content(db_session: Session) -> tuple[Subject, Concept, Concept]:
    subject = Subject(code="MATH12-Q", name="Mathematics 12", grade_level=12)
    db_session.add(subject)
    db_session.flush()
    derivative = Concept(
        subject_id=subject.id, code="DERIVATIVE-Q", name="Derivative",
        description="Derivative concept", grade_level=12, order_index=1,
    )
    function = Concept(
        subject_id=subject.id, code="FUNCTION-Q", name="Function",
        description="Function concept", grade_level=12, order_index=0,
    )
    db_session.add_all([derivative, function])
    db_session.commit()
    return subject, derivative, function
