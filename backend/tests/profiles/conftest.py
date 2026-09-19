from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.core.config import Settings
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

PROFILE_TEST_PASSWORD = "Synthetic-Profile-Password-2026!"


@pytest.fixture
def profile_user_factory(db_session: Session) -> Callable[[Role, str], User]:
    def create(role: Role, email: str) -> User:
        return UserService(db_session).create_user(
            UserCreate(email=email, password=PROFILE_TEST_PASSWORD, full_name="Profile Test User", role=role)
        )

    return create


@pytest.fixture
def profile_bearer(db_session: Session, settings: Settings) -> Callable[[User], dict[str, str]]:
    def headers(user: User) -> dict[str, str]:
        pair = AuthService(db_session, settings).login(
            LoginRequest(email=user.email, password=PROFILE_TEST_PASSWORD)
        )
        return {"Authorization": f"Bearer {pair.access_token}"}

    return headers
