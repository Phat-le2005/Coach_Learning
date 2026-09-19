from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.diagnostics.models import (
    DiagnosticCompletionReason,
    DiagnosticSelectionReason,
)
from app.mastery.state import DerivedMasteryState
from app.practice.models import PracticeSessionStatus
from app.practice.schemas import PracticeAnswerCreate, PracticeQuestionRead, QuestionAttemptRead


class DiagnosticStartCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    subject_id: UUID
    max_questions: int = Field(default=12, ge=1, le=100, strict=True)
    minimum_problem_type_coverage: float = Field(
        default=0.6, gt=0.0, le=1.0, allow_inf_nan=False
    )
    confidence_threshold: float = Field(
        default=0.2, ge=0.0, le=1.0, allow_inf_nan=False
    )


class DiagnosticStartRead(BaseModel):
    id: UUID
    subject_id: UUID
    status: PracticeSessionStatus
    max_questions: int
    minimum_problem_type_coverage: float
    confidence_threshold: float
    blueprint_problem_type_ids: list[UUID]
    started_at: datetime


class DiagnosticQuestionRead(BaseModel):
    status: PracticeSessionStatus
    question: PracticeQuestionRead | None
    target_problem_type_id: UUID | None
    target_concept_id: UUID | None
    desired_difficulty: float | None
    selection_reason: DiagnosticSelectionReason | None


class DiagnosticAnswerCreate(PracticeAnswerCreate):
    pass


class DiagnosticAnswerRead(BaseModel):
    attempt: QuestionAttemptRead
    status: PracticeSessionStatus
    coverage: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    completion_reason: DiagnosticCompletionReason | None


class DiagnosticMasteryMetric(BaseModel):
    mastery_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    attempt_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    state: DerivedMasteryState


class DiagnosticSubjectSummary(DiagnosticMasteryMetric):
    subject_id: UUID
    code: str
    name: str


class DiagnosticChapterSummary(DiagnosticMasteryMetric):
    chapter_id: UUID
    code: str
    name: str


class DiagnosticTopicSummary(DiagnosticMasteryMetric):
    topic_id: UUID
    chapter_id: UUID
    code: str
    name: str


class DiagnosticProblemTypeMastery(DiagnosticMasteryMetric):
    problem_type_id: UUID
    topic_id: UUID
    code: str
    name: str


class DiagnosticConceptMastery(DiagnosticMasteryMetric):
    concept_id: UUID
    code: str
    name: str


class DiagnosticResultRead(BaseModel):
    diagnostic_id: UUID
    student_id: UUID
    completion_reason: DiagnosticCompletionReason
    question_count: int
    coverage: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    subject_summary: DiagnosticSubjectSummary
    chapter_summary: list[DiagnosticChapterSummary]
    topic_summary: list[DiagnosticTopicSummary]
    problem_type_mastery: list[DiagnosticProblemTypeMastery]
    concept_mastery: list[DiagnosticConceptMastery]
    strong_problem_types: list[UUID]
    weak_problem_types: list[UUID]
    strong_concepts: list[UUID]
    weak_concepts: list[UUID]
    recommended_starting_problem_types: list[UUID]
