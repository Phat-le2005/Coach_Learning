from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ParentProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class ParentProfilePatch(BaseModel):
    """No editable ParentProfile fields yet; accept an empty JSON object only."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
