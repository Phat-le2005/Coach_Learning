from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.assignments.models import AssignmentStatus, AssignmentType, StudentAssignmentStatus


class AssignmentProblemTypeConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    problem_type_id: UUID
    weight: float = 1.0


class AssignmentLearningObjectiveConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    learning_outcome_id: UUID
    weight: float = 1.0


class AssignmentConceptConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    concept_id: UUID
    weight: float = 1.0


class AssignmentCreate(BaseModel):
    classroom_id: UUID
    subject_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    assignment_type: AssignmentType
    question_count: int = Field(default=5, ge=1)
    difficulty_distribution: dict[str, float] | None = None
    target_problem_types: list[AssignmentProblemTypeConfig] = Field(default_factory=list)
    learning_outcomes: list[AssignmentLearningObjectiveConfig] = Field(default_factory=list)
    target_concepts: list[AssignmentConceptConfig] = Field(default_factory=list)
    question_ids: list[UUID] | None = None
    teaching_plan_id: UUID | None = None
    teacher_material_item_ids: list[UUID] | None = None
    start_at: datetime | None = None
    due_at: datetime | None = None


class AssignmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    due_at: datetime | None = None


class AssignmentLearningObjectiveRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    learning_outcome_id: UUID
    weight: float
    name: str | None = None
    description: str | None = None
    code: str | None = None


class AssignmentProblemTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    problem_type_id: UUID
    weight: float
    name: str | None = None
    code: str | None = None


class AssignmentConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    concept_id: UUID
    weight: float
    name: str | None = None
    code: str | None = None


class AssignmentQuestionOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    label: str
    content: str
    order_index: int


class AssignmentQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    assignment_id: UUID
    question_id: UUID
    order_index: int
    content: str | None = None
    question_type: str | None = None
    difficulty: float | None = None
    correct_answer: str | None = None
    explanation: str | None = None
    options: list[AssignmentQuestionOptionRead] = Field(default_factory=list)


class AssignmentMaterialItemRead(BaseModel):
    id: UUID
    assignment_id: UUID
    teacher_material_item_id: UUID
    order_index: int
    content: str
    question_type: str | None
    difficulty: float | None
    correct_answer: str | None
    explanation: str | None
    options: list[AssignmentQuestionOptionRead] = Field(default_factory=list)


class AssignmentSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    classroom_id: UUID
    subject_id: UUID
    teaching_plan_id: UUID | None = None
    title: str
    description: str | None = None
    assignment_type: AssignmentType
    status: AssignmentStatus
    question_count: int
    start_at: datetime
    due_at: datetime | None = None
    created_by: UUID
    created_at: datetime


class AssignmentRead(AssignmentSummaryRead):
    difficulty_distribution: dict[str, float] | None = None
    learning_objectives: list[AssignmentLearningObjectiveRead] = Field(default_factory=list)
    problem_types: list[AssignmentProblemTypeRead] = Field(default_factory=list)
    concepts: list[AssignmentConceptRead] = Field(default_factory=list)
    questions: list[AssignmentQuestionRead] = Field(default_factory=list)
    material_items: list[AssignmentMaterialItemRead] = Field(default_factory=list)
    total_assigned_students: int = 0
    submitted_count: int = 0


class StudentQuestionOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    label: str
    content: str
    order_index: int


class StudentQuestionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    source_kind: str = "CANONICAL_QUESTION"
    question_id: UUID | None = None
    teacher_material_item_id: UUID | None = None
    order_index: int
    content: str
    question_type: str
    difficulty: float | None
    options: list[StudentQuestionOptionRead] = Field(default_factory=list)
    student_answer: str | None = None
    is_correct: bool | None = None
    correct_answer: str | None = None
    explanation: str | None = None


class StudentAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    assignment_id: UUID
    classroom_id: UUID
    subject_id: UUID
    title: str
    description: str | None = None
    assignment_type: AssignmentType
    status: StudentAssignmentStatus
    question_count: int
    start_at: datetime
    due_at: datetime | None = None
    assigned_at: datetime
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    score: float | None = None
    questions: list[StudentQuestionItemRead] = Field(default_factory=list)


class AnswerSubmitItem(BaseModel):
    question_id: UUID | None = None
    teacher_material_item_id: UUID | None = None
    student_answer: str
    response_time_seconds: float | None = Field(default=None, gt=0)
    hint_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def exactly_one_source(self):
        if (self.question_id is None) == (self.teacher_material_item_id is None):
            raise ValueError("Exactly one question_id or teacher_material_item_id is required")
        return self


class AssignmentSubmissionRequest(BaseModel):
    answers: list[AnswerSubmitItem]


class QuestionResultItem(BaseModel):
    source_kind: str = "CANONICAL_QUESTION"
    question_id: UUID | None = None
    teacher_material_item_id: UUID | None = None
    student_answer: str
    correct_answer: str | None = None
    is_correct: bool | None
    score: float | None
    explanation: str | None = None


class AssignmentSubmissionResultRead(BaseModel):
    student_assignment_id: UUID
    assignment_id: UUID
    status: StudentAssignmentStatus
    score: float
    total_questions: int
    correct_count: int
    submitted_at: datetime
    results: list[QuestionResultItem] = Field(default_factory=list)


class StudentRosterStatusItem(BaseModel):
    student_id: UUID
    student_name: str
    status: StudentAssignmentStatus
    assigned_at: datetime
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    score: float | None = None


class TeacherAssignmentRosterRead(BaseModel):
    assignment_id: UUID
    title: str
    total_students: int
    not_started_count: int
    in_progress_count: int
    submitted_count: int
    graded_count: int
    average_score: float | None = None
    roster: list[StudentRosterStatusItem] = Field(default_factory=list)
