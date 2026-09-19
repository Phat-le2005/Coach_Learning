import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.teachers.models import TeacherProfile
from app.teachers.schemas import TeacherProfilePatch

logger = logging.getLogger(__name__)


class TeacherProfileService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_user(self, user_id: UUID) -> TeacherProfile:
        profile = self.session.scalar(select(TeacherProfile).where(TeacherProfile.user_id == user_id))
        if profile is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Teacher profile was not found.")
        return profile

    def update_for_user(self, user_id: UUID, data: TeacherProfilePatch) -> TeacherProfile:
        profile = self.get_for_user(user_id)
        if "specialization" in data.model_fields_set:
            profile.specialization = data.specialization
            self.session.commit()
            self.session.refresh(profile)
            logger.info("Teacher profile updated (profile_id=%s)", profile.id)
        return profile
