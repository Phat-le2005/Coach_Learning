from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.core.config import Settings
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.fixture
def curriculum_admin_headers(db_session: Session, settings: Settings) -> dict[str, str]:
    password = "Curriculum-Foundation-Test-Password-2026!"
    admin = UserService(db_session).create_user(UserCreate(
        email="curriculum-admin@example.com",
        password=password,
        full_name="Curriculum Admin",
        role=Role.ADMIN,
    ))
    tokens = AuthService(db_session, settings).login(
        LoginRequest(email=admin.email, password=password)
    )
    return {"Authorization": f"Bearer {tokens.access_token}"}
