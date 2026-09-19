import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.students.models import StudentProfile
from app.students.schemas import StudentProfilePatch

logger = logging.getLogger(__name__)


class StudentProfileService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_user(self, user_id: UUID) -> StudentProfile:
        profile = self.session.scalar(select(StudentProfile).where(StudentProfile.user_id == user_id))
        if profile is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Student profile was not found.")
        return profile

    def update_for_user(self, user_id: UUID, data: StudentProfilePatch) -> StudentProfile:
        profile = self.get_for_user(user_id)
        updates = data.model_dump(exclude_unset=True)
        if updates:
            for field, value in updates.items():
                setattr(profile, field, value)
            self.session.commit()
            self.session.refresh(profile)
            logger.info("Student profile updated (profile_id=%s)", profile.id)
        return profile
