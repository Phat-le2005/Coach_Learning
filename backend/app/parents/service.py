from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.parents.models import ParentProfile
from app.parents.schemas import ParentProfilePatch


class ParentProfileService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_user(self, user_id: UUID) -> ParentProfile:
        profile = self.session.scalar(select(ParentProfile).where(ParentProfile.user_id == user_id))
        if profile is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Parent profile was not found.")
        return profile

    def update_for_user(self, user_id: UUID, data: ParentProfilePatch) -> ParentProfile:
        # The schema contains no editable fields; this PATCH is explicitly a no-op.
        return self.get_for_user(user_id)
