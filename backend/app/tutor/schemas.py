from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.tutor.models import LearningMemoryType, TutorSessionStatus


class TutorSessionCreate(BaseModel):
    """Payload to initiate a new tutoring session."""

    subject_id: UUID | None = Field(
        default=None, description="Optional subject id for the session"
    )
    problem_type_id: UUID | None = Field(
        default=None, description="Optional problem type id in focus"
    )
    concept_id: UUID | None = Field(
        default=None, description="Optional concept id in focus"
    )
    question_id: UUID | None = Field(
        default=None, description="Optional question id being attempted"
    )


class TutorSessionRead(BaseModel):
    """Representation of an active or concluded tutoring session."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    subject_id: UUID | None
    problem_type_id: UUID | None
    concept_id: UUID | None
    question_id: UUID | None
    started_at: datetime
    ended_at: datetime | None
    turn_count: int
    status: TutorSessionStatus
    created_at: datetime
    updated_at: datetime


class TutorSessionEndRequest(BaseModel):
    """Payload when concluding a tutoring session."""

    summary_text: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional manual summary or client reflection for the session",
    )
    resolved_questions_count: int = Field(
        default=0,
        ge=0,
        description="Number of questions or obstacles successfully resolved",
    )


class TutorSessionSummaryRead(BaseModel):
    """Representation of the synthesized session summary."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    student_id: UUID
    summary_text: str
    key_takeaways: list[str]
    resolved_questions_count: int
    created_at: datetime


class StudentLearningMemoryRead(BaseModel):
    """Persistent structured learning memory of a student."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    type: LearningMemoryType
    value: str
    confidence: float
    problem_type_id: UUID | None
    concept_id: UUID | None
    source_session_id: UUID | None
    created_at: datetime
    last_confirmed_at: datetime
    is_active: bool


class StudentLearningMemoryFilter(BaseModel):
    """Filter parameters for querying learning memories."""

    type: LearningMemoryType | None = None
    is_active: bool = True


# AI Extraction Contracts
class ProposedMemoryItem(BaseModel):
    """Single learning memory proposal emitted by AI Memory Extractor."""

    type: LearningMemoryType
    value: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Concise description of learning preference, persistent difficulty, misconception, or academic goal",
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence score from 0.0 to 1.0",
    )
    problem_type_id: UUID | None = Field(
        default=None,
        description="Optional referenced problem_type_id if strictly academic",
    )
    concept_id: UUID | None = Field(
        default=None,
        description="Optional referenced concept_id if strictly academic",
    )
    reasoning: str | None = Field(
        default=None,
        max_length=500,
        description="Pedagogical rationale for why this should be remembered",
    )


class MemoryExtractionAIOutput(BaseModel):
    """Structured response schema enforced on AI Memory Extractor."""

    session_summary: str = Field(
        ...,
        description="2-3 sentence academic summary of topics learned and obstacles tackled",
    )
    key_takeaways: list[str] = Field(
        default_factory=list,
        description="Bulleted key academic takeaways from the session",
    )
    proposed_memories: list[ProposedMemoryItem] = Field(
        default_factory=list,
        description="Proposed persistent memories to be strictly validated by the backend",
    )
