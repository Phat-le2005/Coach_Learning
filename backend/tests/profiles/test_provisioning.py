from collections.abc import Callable
from uuid import uuid4

import pytest
from sqlalchemy import event, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.parents.models import ParentProfile
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService
from tests.profiles.conftest import PROFILE_TEST_PASSWORD


@pytest.mark.parametrize("role", list(Role))
def test_user_provisioning_creates_only_matching_profile(
    db_session: Session, profile_user_factory: Callable[[Role, str], User], role: Role
) -> None:
    user = profile_user_factory(role, "provisioned@example.com")
    for expected, model in [(Role.STUDENT, StudentProfile), (Role.TEACHER, TeacherProfile), (Role.PARENT, ParentProfile)]:
        profiles = db_session.scalars(select(model)).all()
        assert len(profiles) == (1 if role == expected else 0)
        if profiles:
            assert profiles[0].user_id == user.id


@pytest.mark.parametrize("role,model", [(Role.STUDENT, StudentProfile), (Role.TEACHER, TeacherProfile), (Role.PARENT, ParentProfile)])
def test_user_can_have_only_one_profile_of_each_type(
    db_session: Session, profile_user_factory: Callable[[Role, str], User], role: Role,
    model: type[StudentProfile] | type[TeacherProfile] | type[ParentProfile],
) -> None:
    user = profile_user_factory(role, "unique@example.com")
    with pytest.raises(IntegrityError):
        db_session.execute(insert(model).values(id=uuid4(), user_id=user.id))
    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(model)) == 1


@pytest.mark.parametrize("grade", [0, 13, None])
def test_database_enforces_student_grade(
    db_session: Session, profile_user_factory: Callable[[Role, str], User], grade: int | None
) -> None:
    user = profile_user_factory(Role.STUDENT, "grade@example.com")
    profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    assert profile is not None
    with pytest.raises(IntegrityError):
        db_session.execute(update(StudentProfile).where(StudentProfile.user_id == user.id).values(grade_level=grade))
    db_session.rollback()
    assert profile.grade_level == 12


def test_profile_failure_rolls_back_user_creation(db_session: Session) -> None:
    @event.listens_for(db_session, "before_flush")
    def invalidate_new_profile(session: Session, flush_context: object, instances: object) -> None:
        for instance in session.new:
            if isinstance(instance, StudentProfile):
                instance.grade_level = 99

    with pytest.raises(IntegrityError):
        UserService(db_session).create_user(
            UserCreate(email="atomic@example.com", password=PROFILE_TEST_PASSWORD, full_name="Atomic User")
        )
    assert db_session.scalar(select(func.count()).select_from(User)) == 0
    assert db_session.scalar(select(func.count()).select_from(StudentProfile)) == 0
