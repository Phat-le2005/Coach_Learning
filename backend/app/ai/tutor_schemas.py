from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TutorRequest(BaseModel):
    """Input payload for student tutoring requests."""

    model_config = ConfigDict(extra="ignore")

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Student query, question, or expression of confusion",
    )
    question_id: UUID | None = Field(
        default=None,
        description="Optional ID of the specific question being attempted",
    )
    problem_type_id: UUID | None = Field(
        default=None,
        description="Optional ID of the current problem type being studied",
    )
    concept_id: UUID | None = Field(
        default=None,
        description="Optional ID of the primary concept in focus",
    )
    session_id: UUID | None = Field(
        default=None,
        description="Optional ID of the active practice or study session",
    )
    session_summary: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional short summary (2-3 sentences) of recent dialogue turns",
    )
    stream: bool = Field(
        default=False,
        description="Whether to stream the tutor's response in chunks",
    )


class TutorContextData(BaseModel):
    """Lean, targeted academic context constructed for the Socratic prompt.

    Strict boundary: does NOT include full digital twin or full chat history.
    """

    student_name: str
    grade_level: int
    subject_name: str
    topic_name: str
    problem_type_name: str
    concept_context: str
    mastery_context: str
    misconceptions_context: str
    question_context: str
    recent_attempts_context: str
    rag_context: str
    session_summary: str
    learning_memory_context: str = "(Chưa có ký ức học tập liên quan)"
    student_query: str

    def to_prompt_variables(self) -> dict[str, str]:
        return {
            "student_name": self.student_name,
            "grade_level": str(self.grade_level),
            "subject_name": self.subject_name,
            "topic_name": self.topic_name,
            "problem_type_name": self.problem_type_name,
            "concept_context": self.concept_context,
            "mastery_context": self.mastery_context,
            "misconceptions_context": self.misconceptions_context,
            "question_context": self.question_context,
            "recent_attempts_context": self.recent_attempts_context,
            "rag_context": self.rag_context,
            "session_summary": self.session_summary,
            "learning_memory_context": self.learning_memory_context,
            "student_query": self.student_query,
        }


class TutorResponse(BaseModel):
    """Standard non-streaming response from the AI tutor."""

    reply: str = Field(..., description="Socratic pedagogical reply from tutor")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Non-sensitive academic metadata (e.g. subject, problem type, rag chunks count)",
    )
