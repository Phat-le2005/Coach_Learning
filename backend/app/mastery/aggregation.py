from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.mastery.state import DerivedMasteryState, derive_mastery_state
from app.subjects.models import Subject


@dataclass(frozen=True, slots=True)
class MasterySnapshot:
    mastery_score: float
    confidence: float
    attempt_count: int
    correct_count: int
    last_practiced_at: datetime | None
    last_updated_at: datetime | None
    state: DerivedMasteryState
    problem_type_count: int = 0
    started_problem_type_count: int = 0


class MasteryAggregationService:
    """Read persisted leaf mastery and derive hierarchy aggregates in memory."""

    def __init__(self, session: Session, *, as_of: datetime | None = None) -> None:
        self.session = session
        self.as_of = as_of or datetime.now(timezone.utc)

    def get_problem_type_mastery(
        self, student_id: UUID, problem_type_id: UUID
    ) -> MasterySnapshot:
        if self.session.get(ProblemType, problem_type_id) is None:
            raise ApplicationError(
                404, "PROBLEM_TYPE_NOT_FOUND", "Problem type was not found."
            )
        row = self.session.get(StudentProblemTypeMastery, (student_id, problem_type_id))
        return self.snapshot(row)

    def get_concept_mastery(self, student_id: UUID, concept_id: UUID) -> MasterySnapshot:
        if self.session.get(Concept, concept_id) is None:
            raise ApplicationError(404, "CONCEPT_NOT_FOUND", "Concept was not found.")
        row = self.session.get(StudentConceptMastery, (student_id, concept_id))
        return self.snapshot(row)

    def get_topic_mastery(self, student_id: UUID, topic_id: UUID) -> MasterySnapshot:
        if self.session.get(Topic, topic_id) is None:
            raise ApplicationError(404, "TOPIC_NOT_FOUND", "Topic was not found.")
        rows = self.session.execute(
            select(ProblemType, StudentProblemTypeMastery)
            .outerjoin(
                StudentProblemTypeMastery,
                (StudentProblemTypeMastery.problem_type_id == ProblemType.id)
                & (StudentProblemTypeMastery.student_id == student_id),
            )
            .where(ProblemType.topic_id == topic_id, ProblemType.is_active.is_(True))
            .order_by(ProblemType.order_index, ProblemType.code, ProblemType.id)
        ).all()
        return self.aggregate([mastery for _, mastery in rows])

    def get_chapter_mastery(self, student_id: UUID, chapter_id: UUID) -> MasterySnapshot:
        if self.session.get(Chapter, chapter_id) is None:
            raise ApplicationError(404, "CHAPTER_NOT_FOUND", "Chapter was not found.")
        rows = self.session.execute(
            select(ProblemType, StudentProblemTypeMastery)
            .join(Topic, Topic.id == ProblemType.topic_id)
            .outerjoin(
                StudentProblemTypeMastery,
                (StudentProblemTypeMastery.problem_type_id == ProblemType.id)
                & (StudentProblemTypeMastery.student_id == student_id),
            )
            .where(Topic.chapter_id == chapter_id, ProblemType.is_active.is_(True))
        ).all()
        return self.aggregate([mastery for _, mastery in rows])

    def get_subject_mastery(self, student_id: UUID, subject_id: UUID) -> MasterySnapshot:
        if self.session.get(Subject, subject_id) is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject was not found.")
        rows = self.session.execute(
            select(ProblemType, StudentProblemTypeMastery)
            .join(Topic, Topic.id == ProblemType.topic_id)
            .join(Chapter, Chapter.id == Topic.chapter_id)
            .outerjoin(
                StudentProblemTypeMastery,
                (StudentProblemTypeMastery.problem_type_id == ProblemType.id)
                & (StudentProblemTypeMastery.student_id == student_id),
            )
            .where(Chapter.subject_id == subject_id, ProblemType.is_active.is_(True))
        ).all()
        return self.aggregate([mastery for _, mastery in rows])

    def snapshot(
        self, row: StudentConceptMastery | StudentProblemTypeMastery | None
    ) -> MasterySnapshot:
        if row is None:
            return MasterySnapshot(
                mastery_score=0.0,
                confidence=0.0,
                attempt_count=0,
                correct_count=0,
                last_practiced_at=None,
                last_updated_at=None,
                state=DerivedMasteryState.NOT_STARTED,
            )
        return MasterySnapshot(
            mastery_score=row.mastery_score,
            confidence=row.confidence,
            attempt_count=row.attempt_count,
            correct_count=row.correct_count,
            last_practiced_at=row.last_practiced_at,
            last_updated_at=row.last_updated_at,
            state=derive_mastery_state(
                mastery_score=row.mastery_score,
                confidence=row.confidence,
                attempt_count=row.attempt_count,
                last_practiced_at=row.last_practiced_at,
                as_of=self.as_of,
            ),
        )

    def aggregate(
        self, rows: list[StudentProblemTypeMastery | None]
    ) -> MasterySnapshot:
        total = len(rows)
        started = [row for row in rows if row is not None]
        if total == 0:
            return MasterySnapshot(
                mastery_score=0.0,
                confidence=0.0,
                attempt_count=0,
                correct_count=0,
                last_practiced_at=None,
                last_updated_at=None,
                state=DerivedMasteryState.NOT_STARTED,
                problem_type_count=0,
                started_problem_type_count=0,
            )

        # Active ProblemTypes currently have equal curriculum weight. Missing leaf rows
        # count as zero so one practiced type cannot inflate an entire topic/chapter.
        mastery_score = round(sum(row.mastery_score for row in started) / total, 6)
        confidence = round(sum(row.confidence for row in started) / total, 6)
        attempt_count = sum(row.attempt_count for row in started)
        correct_count = sum(row.correct_count for row in started)
        last_practiced_at = _latest_or_none(
            [row.last_practiced_at for row in started]
        )
        last_updated_at = _latest_or_none([row.last_updated_at for row in started])
        return MasterySnapshot(
            mastery_score=mastery_score,
            confidence=confidence,
            attempt_count=attempt_count,
            correct_count=correct_count,
            last_practiced_at=last_practiced_at,
            last_updated_at=last_updated_at,
            state=derive_mastery_state(
                mastery_score=mastery_score,
                confidence=confidence,
                attempt_count=attempt_count,
                last_practiced_at=last_practiced_at,
                as_of=self.as_of,
            ),
            problem_type_count=total,
            started_problem_type_count=len(started),
        )


def _latest_or_none(values: list[datetime]) -> datetime | None:
    if not values:
        return None
    return max(
        values,
        key=lambda value: value
        if value.tzinfo is not None
        else value.replace(tzinfo=timezone.utc),
    )

