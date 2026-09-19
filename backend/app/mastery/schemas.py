from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.mastery.state import DerivedMasteryState


class MasteryMetricRead(BaseModel):
    mastery_score: float
    confidence: float
    attempt_count: int
    correct_count: int
    last_practiced_at: datetime | None
    last_updated_at: datetime | None
    state: DerivedMasteryState


class ProblemTypeMasteryRead(MasteryMetricRead):
    problem_type_id: UUID
    topic_id: UUID
    code: str
    name: str


class ConceptMasteryRead(MasteryMetricRead):
    concept_id: UUID
    subject_id: UUID
    code: str
    name: str


class AggregateMasteryRead(MasteryMetricRead):
    problem_type_count: int
    started_problem_type_count: int


class TopicMasteryRead(AggregateMasteryRead):
    topic_id: UUID
    chapter_id: UUID
    code: str
    name: str
    problem_types: list[ProblemTypeMasteryRead]


class ChapterMasteryRead(AggregateMasteryRead):
    chapter_id: UUID
    subject_id: UUID
    code: str
    name: str
    topics: list[TopicMasteryRead]


class SubjectMasteryRead(AggregateMasteryRead):
    subject_id: UUID
    code: str
    name: str
    chapters: list[ChapterMasteryRead]
    concepts: list[ConceptMasteryRead]


class StudentMasteryRead(BaseModel):
    student_id: UUID
    subjects: list[SubjectMasteryRead]

