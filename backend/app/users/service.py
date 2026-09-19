import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.core.exceptions import ApplicationError
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile
from app.parents.models import ParentProfile

logger = logging.getLogger(__name__)


def duplicate_email_error() -> ApplicationError:
    return ApplicationError(409, "EMAIL_ALREADY_REGISTERED", "Email is already registered.")


class UserService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email.lower()))

    def create_user(self, data: UserCreate) -> User:
        """Trusted provisioning operation; public registration policy lives in AuthService."""
        if self.find_by_email(str(data.email)) is not None:
            raise duplicate_email_error()
        user = User(
            email=str(data.email),
            password_hash=hash_password(data.password.get_secret_value()),
            full_name=data.full_name,
            role=data.role,
        )
        self.session.add(user)
        try:
            self.session.flush()
            profile_model = {
                Role.STUDENT: StudentProfile,
                Role.TEACHER: TeacherProfile,
                Role.PARENT: ParentProfile,
            }.get(user.role)
            if profile_model is not None:
                self.session.add(profile_model(user_id=user.id))
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            # A unique constraint also protects against concurrent registrations.
            if self.find_by_email(str(data.email)) is not None:
                raise duplicate_email_error() from None
            raise
        self.session.refresh(user)
        logger.info("User created (id=%s, role=%s)", user.id, user.role.value)
        return user
