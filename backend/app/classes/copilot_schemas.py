from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TeacherCopilotRequest(BaseModel):
    """Payload sent by teacher asking pedagogical questions to the Copilot."""

    query: str = Field(
        ...,
        min_length=2,
        max_length=1000,
        description="Teacher query (e.g., 'Lớp đang yếu dạng bài nào?', 'Học sinh nào đang yếu do kiến thức tiền đề?', 'Tiết sau nên củng cố phần nào?').",
        examples=["Lớp đang yếu dạng bài nào?"],
    )
    subject_id: UUID | None = Field(
        default=None,
        description="Optional filter by subject ID.",
    )
    include_synthetic: bool = Field(
        default=False,
        description="Whether to include synthetic test students in the analysis.",
    )


class TeacherCopilotStudentAttentionAI(BaseModel):
    """Structured student attention item parsed from AI response."""

    student_name: str = Field(..., description="Student full name as provided in context.")
    reason: str = Field(..., description="Factual pedagogical reason from analytics data.")
    suggested_focus: str = Field(..., description="Specific recommended focus area or remedial task.")


class TeacherCopilotAIOutput(BaseModel):
    """Strict structured JSON output contract expected from the AI provider."""

    observations: list[str] = Field(
        default_factory=list,
        description="Factual observations strictly drawn from classroom analytics, without speculation.",
    )
    priorities: list[str] = Field(
        default_factory=list,
        description="Ranked pedagogical priorities for the teacher to address.",
    )
    recommended_actions: list[str] = Field(
        default_factory=list,
        description="Actionable instructional recommendations for upcoming lessons (no auto-assignment).",
    )
    students_requiring_attention: list[TeacherCopilotStudentAttentionAI] = Field(
        default_factory=list,
        description="Specific students requiring targeted intervention or 1-on-1 support.",
    )


class TeacherCopilotStudentAttention(BaseModel):
    """Student attention item returned in API response with optional UUID."""

    student_id: UUID | None = Field(
        default=None,
        description="Resolved UUID of the student profile if matched by name.",
    )
    student_name: str = Field(..., description="Student full name.")
    reason: str = Field(..., description="Pedagogical reason based on mastery and alert data.")
    suggested_focus: str = Field(..., description="Recommended remedial or instructional focus.")


class TeacherCopilotContextSummary(BaseModel):
    """Metadata summary of the context data fed into the Copilot."""

    student_count: int = Field(..., description="Number of active enrolled students analyzed.")
    active_teaching_plan: str | None = Field(
        default=None,
        description="Name or topic of the active teaching plan for this classroom, if any.",
    )
    weak_problem_types_count: int = Field(
        default=0,
        description="Number of problem types with average mastery < 0.50.",
    )
    prerequisite_gaps_count: int = Field(
        default=0,
        description="Number of prerequisite concepts identified with low mastery.",
    )
    common_misconceptions_count: int = Field(
        default=0,
        description="Number of active misconceptions identified in the classroom.",
    )
    total_alerts_count: int = Field(
        default=0,
        description="Total number of intervention alerts active across the classroom.",
    )
    critical_alerts_count: int = Field(
        default=0,
        description="Number of CRITICAL intervention alerts.",
    )


class TeacherCopilotRead(BaseModel):
    """Complete Teacher Copilot response returned to the frontend."""

    classroom_id: UUID = Field(..., description="Classroom ID.")
    classroom_name: str = Field(..., description="Classroom name.")
    teacher_name: str = Field(..., description="Teacher name.")
    query: str = Field(..., description="The query answered by Copilot.")
    observations: list[str] = Field(
        ...,
        description="Factual observations drawn directly from supplied classroom analytics.",
    )
    priorities: list[str] = Field(
        ...,
        description="Pedagogical priorities ordered by instructional urgency.",
    )
    recommended_actions: list[str] = Field(
        ...,
        description="Instructional recommendations for the teacher.",
    )
    students_requiring_attention: list[TeacherCopilotStudentAttention] = Field(
        default_factory=list,
        description="Targeted students requiring attention with data-backed reasons.",
    )
    context_summary: TeacherCopilotContextSummary = Field(
        ...,
        description="Summary of classroom data supplied to the Copilot.",
    )
    is_fallback: bool = Field(
        default=False,
        description="True if response was produced by deterministic fallback logic.",
    )
    generated_at: datetime = Field(
        ...,
        description="Timestamp when this Copilot response was generated.",
    )


class TeacherCopilotContextInput(BaseModel):
    """Internal model aggregating all gathered database context before prompt rendering."""

    classroom_id: UUID
    classroom_name: str
    grade_level: int
    teacher_name: str
    query: str
    subject_name: str
    teaching_plan_summary: str
    curriculum_context: str
    class_analytics_summary: str
    problem_type_summaries: str
    prerequisite_signals_summary: str
    misconceptions_summary: str
    intervention_alerts_summary: str
    students_attention_summary: str
    student_name_to_id: dict[str, UUID] = Field(default_factory=dict)
    context_summary: TeacherCopilotContextSummary
    weak_problem_types_list: list[str] = Field(default_factory=list)
    prerequisite_gaps_list: list[dict[str, Any]] = Field(default_factory=list)
    misconceptions_list: list[dict[str, Any]] = Field(default_factory=list)
    alerts_list: list[dict[str, Any]] = Field(default_factory=list)
