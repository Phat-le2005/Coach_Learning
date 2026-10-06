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


def create_curriculum(
    session: Session, prefix: str = "SLS"
) -> tuple[Subject, Chapter, Topic, ProblemType, Concept]:
    subject = Subject(code=f"{prefix}-SUB", name=f"{prefix} Môn Học", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(
        subject_id=subject.id,
        code=f"{prefix}-CHP",
        name=f"{prefix} Chương 1",
        order_index=0,
    )
    session.add(chapter)
    session.flush()

    topic = Topic(
        chapter_id=chapter.id,
        code=f"{prefix}-TOP",
        name=f"{prefix} Chủ đề 1",
        order_index=0,
    )
    session.add(topic)
    session.flush()

    pt = ProblemType(
        topic_id=topic.id,
        code=f"{prefix}-PT",
        name=f"{prefix} Dạng Bài 1",
        order_index=0,
        is_active=True,
    )
    concept = Concept(
        subject_id=subject.id,
        code=f"{prefix}-CON",
        name=f"{prefix} Khái Niệm 1",
        order_index=0,
    )
    session.add_all([pt, concept])
    session.flush()
    return subject, chapter, topic, pt, concept
