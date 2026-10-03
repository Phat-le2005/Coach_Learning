from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.practice.models import EvaluationStatus, PracticeSessionStatus
from app.questions.models import QuestionType
from app.knowledge_gap.models import RootCauseVerificationTargetType
from app.repair.models import (
    AdaptiveRepairDecisionReason,
    AdaptiveRepairItemRole,
    AdaptiveRepairOutcome,
    AdaptiveRepairPhase,
    AdaptiveRepairStatus,
)



class RepairTriggerType(StrEnum):
    """Event or condition that triggered the Repair Session."""

    LOW_PROBLEM_TYPE_MASTERY = "LOW_PROBLEM_TYPE_MASTERY"
    LOW_CONCEPT_MASTERY = "LOW_CONCEPT_MASTERY"
    PERSISTENT_MISCONCEPTION = "PERSISTENT_MISCONCEPTION"
    KNOWLEDGE_GAP_DETECTED = "KNOWLEDGE_GAP_DETECTED"
    REPEATED_WRONG_ATTEMPTS = "REPEATED_WRONG_ATTEMPTS"


class RepairTargetType(StrEnum):
    """Type of entity being targeted for repair."""

    PROBLEM_TYPE = "PROBLEM_TYPE"
    PREREQUISITE_CONCEPT = "PREREQUISITE_CONCEPT"


class RepairStepRole(StrEnum):
    """Pedagogical role of each step in the repair sequence."""

    BRIEF_REVIEW = "BRIEF_REVIEW"
    EASY_VERIFICATION = "EASY_VERIFICATION"
    GUIDED_PRACTICE = "GUIDED_PRACTICE"
    MEDIUM_PRACTICE = "MEDIUM_PRACTICE"
    FINAL_RECHECK = "FINAL_RECHECK"


class RepairSessionCreate(BaseModel):
    """Payload to start a new repair session."""

    model_config = ConfigDict(extra="forbid")

    trigger: RepairTriggerType = Field(
        ..., description="Condition that triggered the repair."
    )
    target_type: RepairTargetType = Field(
        ..., description="Whether targeting a ProblemType or prerequisite Concept."
    )
    target_id: UUID = Field(
        ..., description="UUID of the targeted ProblemType or Concept."
    )
    misconception_definition_id: UUID | None = Field(
        default=None,
        description="Optional ID of a persistent misconception to resolve upon repair success.",
    )


class RepairStepQuestionOptionRead(BaseModel):
    """Option for multiple choice question in repair step."""

    id: UUID
    label: str
    content: str
    order_index: int


class RepairStepRead(BaseModel):
    """Representation of an individual step in the repair sequence."""

    step_number: int = Field(..., ge=1, le=5)
    role: RepairStepRole
    instruction: str
    # If step is BRIEF_REVIEW, review_content is provided and question is None
    review_content: str | None = None
    # For question steps
    question_id: UUID | None = None
    question_content: str | None = None
    question_type: QuestionType | None = None
    difficulty: float | None = None
    options: list[RepairStepQuestionOptionRead] = Field(default_factory=list)
    # Available hints for GUIDED_PRACTICE
    hints_available: bool = False
    # Attempt status if already answered
    is_attempted: bool = False
    is_correct: bool | None = None
    score: float | None = None


class RepairSessionRead(BaseModel):
    """Full detail of a Repair Session and its sequential steps."""

    id: UUID
    student_id: UUID
    subject_id: UUID
    trigger: RepairTriggerType
    target_type: RepairTargetType
    target_id: UUID
    target_name: str
    target_code: str
    status: PracticeSessionStatus
    started_at: datetime
    completed_at: datetime | None = None
    steps: list[RepairStepRead]
    is_completed: bool = False


class RepairAnswerSubmit(BaseModel):
    """Payload when a student answers a question step."""

    model_config = ConfigDict(extra="forbid")

    student_answer: str = Field(..., min_length=1)
    response_time_seconds: float | None = Field(default=None, gt=0)
    hint_count: int = Field(default=0, ge=0)


class RepairAnswerResult(BaseModel):
    """Result of submitting an answer in a repair step."""

    step_number: int
    question_id: UUID
    is_correct: bool | None
    score: float | None
    evaluation_status: EvaluationStatus
    explanation: str | None = None


class RepairEvaluationResult(BaseModel):
    """Final deterministic evaluation of a completed repair session."""

    session_id: UUID
    is_successful: bool
    status: PracticeSessionStatus
    average_score: float = Field(..., ge=0.0, le=1.0)
    final_recheck_correct: bool
    evidence_count: int
    resolution_status: str
    misconception_resolved: bool = False
    summary_message: str

# ---------------------------------------------------------------------------
# Adaptive verified-root-cause repair
# ---------------------------------------------------------------------------


class AdaptiveRepairTargetRead(BaseModel):
    target_type: RootCauseVerificationTargetType
    concept_id: UUID | None = None
    problem_type_id: UUID | None = None
    misconception_definition_id: UUID | None = None
    name: str | None = None
    code: str | None = None


class AdaptiveRepairQuestionOptionRead(BaseModel):
    id: UUID
    label: str
    content: str
    order_index: int


class AdaptiveRepairCurrentItemRead(BaseModel):
    id: UUID
    order_index: int
    role: AdaptiveRepairItemRole
    question_id: UUID
    question_content: str
    question_type: QuestionType
    question_difficulty: float
    desired_difficulty: float
    options: list[AdaptiveRepairQuestionOptionRead] = Field(default_factory=list)
    hints_allowed: bool


class AdaptiveRepairHistoryItemRead(BaseModel):
    id: UUID
    order_index: int
    role: AdaptiveRepairItemRole
    question_id: UUID
    question_difficulty: float
    desired_difficulty: float
    is_correct: bool
    score: float
    hint_count: int
    difficulty_before: float
    difficulty_after: float
    phase_before: AdaptiveRepairPhase
    phase_after: AdaptiveRepairPhase
    reason_code: AdaptiveRepairDecisionReason
    explanation: str | None = None


class AdaptiveRepairProgressRead(BaseModel):
    attempted_count: int
    correct_count: int
    consecutive_correct: int
    consecutive_wrong: int
    max_questions: int


class AdaptiveRepairSessionRead(BaseModel):
    id: UUID
    practice_session_id: UUID
    diagnosis_id: UUID
    verification_id: UUID
    verification_target_id: UUID
    repair_cycle_index: int = 1
    previous_adaptive_repair_session_id: UUID | None = None
    target: AdaptiveRepairTargetRead
    status: AdaptiveRepairStatus
    phase: AdaptiveRepairPhase
    outcome: AdaptiveRepairOutcome
    initial_difficulty: float
    current_difficulty: float
    target_exit_difficulty: float
    progress: AdaptiveRepairProgressRead
    current_item: AdaptiveRepairCurrentItemRead | None = None
    history: list[AdaptiveRepairHistoryItemRead] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime | None = None


class AdaptiveRepairAnswerSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: UUID
    student_answer: str = Field(..., min_length=1)
    response_time_seconds: float | None = Field(default=None, gt=0)
    hint_count: int = Field(default=0, ge=0)


class AdaptiveRepairAttemptRead(BaseModel):
    id: UUID
    item_id: UUID
    question_id: UUID
    is_correct: bool
    score: float
    evaluation_status: EvaluationStatus


class AdaptiveRepairAnswerResult(BaseModel):
    attempt: AdaptiveRepairAttemptRead
    previous_phase: AdaptiveRepairPhase
    next_phase: AdaptiveRepairPhase
    difficulty_before: float
    difficulty_after: float
    reason_code: AdaptiveRepairDecisionReason
    session: AdaptiveRepairSessionRead
