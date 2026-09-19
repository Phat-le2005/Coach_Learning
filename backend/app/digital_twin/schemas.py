from datetime import date, datetime
from enum import StrEnum
from typing import TypeAlias
from uuid import UUID

from pydantic import BaseModel

from app.mastery.schemas import (
    AggregateMasteryRead,
    ChapterMasteryRead,
    ConceptMasteryRead,
    ProblemTypeMasteryRead,
)
from app.mastery.state import DerivedMasteryState
from app.practice.models import EvaluationStatus, PracticeSessionType
from app.questions.models import QuestionType
from app.students.models import SyntheticProfile


class DigitalTwinContextType(StrEnum):
    TUTOR = "TUTOR"
    PLANNER = "PLANNER"
    TEACHER_COPILOT = "TEACHER_COPILOT"
    PARENT_SUMMARY = "PARENT_SUMMARY"
    EXAM_ANALYSIS = "EXAM_ANALYSIS"


class DigitalTwinBasicProfileRead(BaseModel):
    student_id: UUID
    user_id: UUID
    email: str
    full_name: str
    grade_level: int
    school_name: str | None
    date_of_birth: date | None
    is_synthetic: bool
    synthetic_profile: SyntheticProfile | None


class CurriculumSubjectProgressRead(AggregateMasteryRead):
    subject_id: UUID
    code: str
    name: str
    chapters: list[ChapterMasteryRead]


class PrerequisiteConceptRead(BaseModel):
    concept_id: UUID
    code: str
    name: str
    mastery_score: float
    confidence: float
    state: DerivedMasteryState


class ConceptKnowledgeRead(ConceptMasteryRead):
    prerequisites: list[PrerequisiteConceptRead]


class ProblemTypeConceptLinkRead(BaseModel):
    problem_type_id: UUID
    concept_id: UUID
    weight: float
    is_primary: bool


class KnowledgeStateRead(BaseModel):
    concepts: list[ConceptKnowledgeRead]
    problem_type_concept_links: list[ProblemTypeConceptLinkRead]
    strong_concepts: list[ConceptKnowledgeRead]
    weak_concepts: list[ConceptKnowledgeRead]


class RecentAttemptRead(BaseModel):
    attempt_id: UUID
    practice_session_id: UUID
    question_id: UUID
    subject_id: UUID
    session_type: PracticeSessionType
    question_type: QuestionType
    question_content: str
    student_answer: str
    is_correct: bool | None
    score: float | None
    evaluation_status: EvaluationStatus
    response_time_seconds: float | None
    hint_count: int
    attempted_at: datetime
    concept_ids: list[UUID]
    problem_type_ids: list[UUID]


class ReviewDueRead(BaseModel):
    concepts: list[ConceptKnowledgeRead]
    problem_types: list[ProblemTypeMasteryRead]


class StudyBehaviorRead(BaseModel):
    total_sessions: int
    completed_sessions: int
    total_attempts: int
    correct_attempts: int
    average_response_time_seconds: float | None
    total_hints: int
    last_activity_at: datetime | None


class StudentDigitalTwinSnapshot(BaseModel):
    basic_profile: DigitalTwinBasicProfileRead
    curriculum_progress: list[CurriculumSubjectProgressRead]
    knowledge_state: KnowledgeStateRead
    strong_problem_types: list[ProblemTypeMasteryRead]
    weak_problem_types: list[ProblemTypeMasteryRead]
    recent_attempts: list[RecentAttemptRead]
    review_due: ReviewDueRead
    study_behavior: StudyBehaviorRead


class SubjectProgressSummaryRead(BaseModel):
    subject_id: UUID
    code: str
    name: str
    mastery_score: float
    confidence: float
    state: DerivedMasteryState


class TutorAIContextRead(BaseModel):
    context_type: DigitalTwinContextType
    student_id: UUID
    weak_problem_types: list[ProblemTypeMasteryRead]
    weak_concepts: list[ConceptKnowledgeRead]
    problem_type_concept_links: list[ProblemTypeConceptLinkRead]
    review_due: ReviewDueRead
    recent_attempts: list[RecentAttemptRead]


class PlannerAIContextRead(BaseModel):
    context_type: DigitalTwinContextType
    student_id: UUID
    grade_level: int
    subject_progress: list[SubjectProgressSummaryRead]
    weak_problem_types: list[ProblemTypeMasteryRead]
    weak_concepts: list[ConceptMasteryRead]
    review_due: ReviewDueRead
    study_behavior: StudyBehaviorRead


class TeacherCopilotAIContextRead(BaseModel):
    context_type: DigitalTwinContextType
    basic_profile: DigitalTwinBasicProfileRead
    subject_progress: list[SubjectProgressSummaryRead]
    strong_problem_types: list[ProblemTypeMasteryRead]
    weak_problem_types: list[ProblemTypeMasteryRead]
    strong_concepts: list[ConceptMasteryRead]
    weak_concepts: list[ConceptKnowledgeRead]
    problem_type_concept_links: list[ProblemTypeConceptLinkRead]
    recent_attempts: list[RecentAttemptRead]
    review_due: ReviewDueRead
    study_behavior: StudyBehaviorRead


class ParentSummaryAIContextRead(BaseModel):
    context_type: DigitalTwinContextType
    student_name: str
    grade_level: int
    school_name: str | None
    subject_progress: list[SubjectProgressSummaryRead]
    strengths: list[str]
    areas_for_support: list[str]
    study_behavior: StudyBehaviorRead


class ExamAnalysisAIContextRead(BaseModel):
    context_type: DigitalTwinContextType
    student_id: UUID
    subject_progress: list[SubjectProgressSummaryRead]
    recent_exam_attempts: list[RecentAttemptRead]
    weak_problem_types: list[ProblemTypeMasteryRead]


StudentAIContext: TypeAlias = (
    TutorAIContextRead
    | PlannerAIContextRead
    | TeacherCopilotAIContextRead
    | ParentSummaryAIContextRead
    | ExamAnalysisAIContextRead
)
