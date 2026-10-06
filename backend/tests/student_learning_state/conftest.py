from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.concepts.models import Concept
from app.core.config import Settings
from app.curriculum.models import Chapter, ProblemType, Topic
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

TEST_PASSWORD = "Synthetic-Student-State-Test-Password-2026!"


@pytest.fixture
def user_factory(db_session: Session) -> Callable[[Role, str], User]:
    def create(role: Role, email: str) -> User:
        return UserService(db_session).create_user(
            UserCreate(
                email=email,
                password=TEST_PASSWORD,
                full_name=f"{role.value.title()} {email.split('@')[0]}",
                role=role,
            )
        )

    return create


@pytest.fixture
def auth_bearer(
    db_session: Session, settings: Settings
) -> Callable[[User], dict[str, str]]:
    def headers(user: User) -> dict[str, str]:
        pair = AuthService(db_session, settings).login(
            LoginRequest(email=user.email, password=TEST_PASSWORD)
        )
        return {"Authorization": f"Bearer {pair.access_token}"}

    return headers


@pytest.fixture
def student_profile_getter(db_session: Session) -> Callable[[User], StudentProfile]:
    def get(user: User) -> StudentProfile:
        profile = db_session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user.id)
        )
        assert profile is not None
        return profile

    return get


from tests.student_learning_state.helpers import create_curriculum  # noqa: F401
