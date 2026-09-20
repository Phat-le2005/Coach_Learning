from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.learning.models import (
    ConceptSignalLevel,
    QuickCheckQuestionRole,
    QuickCheckVerdict,
)
from app.practice.models import PracticeSessionStatus
from app.questions.models import QuestionType


class QuickCheckStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: UUID
    classroom_id: UUID | None = None


class QuickCheckQuestionOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    content: str
    order_index: int


class QuickCheckQuestionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_id: UUID
    order_index: int
    content: str
    question_type: QuestionType
    difficulty: float
    target_problem_type_id: UUID | None = None
    target_concept_id: UUID | None = None
    target_role: QuickCheckQuestionRole
    options: list[QuickCheckQuestionOptionRead] = Field(default_factory=list)


class QuickCheckStartRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    teaching_plan_id: UUID
    classroom_id: UUID
    subject_id: UUID
    status: PracticeSessionStatus
    question_count: int
    target_problem_type_ids: list[UUID]
    questions: list[QuickCheckQuestionItemRead] = Field(default_factory=list)


class QuickCheckProblemTypeResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    problem_type_id: UUID
    problem_type_code: str | None = None
    problem_type_name: str | None = None
    is_core: bool = False
    total_questions: int
    correct_questions: int
    score: float
    status: QuickCheckVerdict


class QuickCheckConceptSignal(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    concept_id: UUID
    concept_code: str | None = None
    concept_name: str | None = None
    is_prerequisite: bool = False
    total_questions: int
    correct_questions: int
    score: float
    signal: ConceptSignalLevel


class QuickCheckResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    teaching_plan_id: UUID
    classroom_id: UUID
    subject_id: UUID
    status: PracticeSessionStatus
    verdict: QuickCheckVerdict
    score: float
    total_questions: int
    attempted_questions: int
    correct_questions: int
    problem_type_results: list[QuickCheckProblemTypeResult] = Field(default_factory=list)
    concept_signals: list[QuickCheckConceptSignal] = Field(default_factory=list)
