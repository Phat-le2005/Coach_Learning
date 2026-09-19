from dataclasses import dataclass
from math import ceil
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.questions.models import (
    Question,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)


@dataclass(frozen=True, slots=True)
class DiagnosticBlueprint:
    problem_type_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class _BlueprintCandidate:
    problem_type_id: UUID
    topic_id: UUID
    chapter_id: UUID
    chapter_order: int
    topic_order: int
    problem_type_order: int
    problem_type_code: str
    exam_relevance: float


class DiagnosticBlueprintService:
    """Choose a deterministic, hierarchy-balanced set of assessable ProblemTypes."""

    AUTO_EVALUATED_TYPES = (
        QuestionType.MULTIPLE_CHOICE,
        QuestionType.TRUE_FALSE,
        QuestionType.SHORT_ANSWER,
    )

    def __init__(self, session: Session) -> None:
        self.session = session

    def build(
        self,
        subject_id: UUID,
        *,
        max_questions: int,
        minimum_problem_type_coverage: float,
    ) -> DiagnosticBlueprint:
        rows = self.session.execute(
            select(
                ProblemType.id,
                Topic.id,
                Chapter.id,
                Chapter.order_index,
                Topic.order_index,
                ProblemType.order_index,
                ProblemType.code,
                func.max(Question.exam_weight),
            )
            .join(Topic, Topic.id == ProblemType.topic_id)
            .join(Chapter, Chapter.id == Topic.chapter_id)
            .join(
                QuestionProblemType,
                QuestionProblemType.problem_type_id == ProblemType.id,
            )
            .join(Question, Question.id == QuestionProblemType.question_id)
            .where(
                Chapter.subject_id == subject_id,
                ProblemType.is_active.is_(True),
                Question.status == QuestionStatus.APPROVED,
                Question.question_type.in_(self.AUTO_EVALUATED_TYPES),
                Question.problem_type_links.any(),
                Question.concept_links.any(),
                Question.learning_outcome_links.any(),
            )
            .group_by(
                ProblemType.id,
                Topic.id,
                Chapter.id,
                Chapter.order_index,
                Topic.order_index,
                ProblemType.order_index,
                ProblemType.code,
            )
        )
        candidates = [
            _BlueprintCandidate(
                problem_type_id=problem_type_id,
                topic_id=topic_id,
                chapter_id=chapter_id,
                chapter_order=chapter_order,
                topic_order=topic_order,
                problem_type_order=problem_type_order,
                problem_type_code=problem_type_code,
                exam_relevance=float(exam_relevance),
            )
            for (
                problem_type_id,
                topic_id,
                chapter_id,
                chapter_order,
                topic_order,
                problem_type_order,
                problem_type_code,
                exam_relevance,
            ) in rows
        ]
        if not candidates:
            raise ApplicationError(
                422,
                "DIAGNOSTIC_BLUEPRINT_EMPTY",
                "The subject has no approved auto-evaluable classified questions.",
            )

        chapter_count = len({item.chapter_id for item in candidates})
        desired_count = min(
            len(candidates),
            max_questions,
            max(chapter_count, ceil(len(candidates) * minimum_problem_type_coverage)),
        )
        selected: list[_BlueprintCandidate] = []
        selected_ids: set[UUID] = set()

        by_chapter: dict[UUID, list[_BlueprintCandidate]] = {}
        for item in candidates:
            by_chapter.setdefault(item.chapter_id, []).append(item)
        for chapter_items in sorted(
            by_chapter.values(), key=lambda items: (items[0].chapter_order, str(items[0].chapter_id))
        ):
            self._append_best(chapter_items, selected, selected_ids, desired_count)

        by_topic: dict[UUID, list[_BlueprintCandidate]] = {}
        for item in candidates:
            by_topic.setdefault(item.topic_id, []).append(item)
        for topic_items in sorted(
            by_topic.values(),
            key=lambda items: (
                items[0].chapter_order,
                items[0].topic_order,
                str(items[0].topic_id),
            ),
        ):
            self._append_best(topic_items, selected, selected_ids, desired_count)

        for item in sorted(candidates, key=self._importance_key):
            if len(selected) >= desired_count:
                break
            if item.problem_type_id not in selected_ids:
                selected.append(item)
                selected_ids.add(item.problem_type_id)

        return DiagnosticBlueprint(
            problem_type_ids=tuple(item.problem_type_id for item in selected)
        )

    @classmethod
    def _append_best(
        cls,
        candidates: list[_BlueprintCandidate],
        selected: list[_BlueprintCandidate],
        selected_ids: set[UUID],
        desired_count: int,
    ) -> None:
        if len(selected) >= desired_count:
            return
        for item in sorted(candidates, key=cls._importance_key):
            if item.problem_type_id not in selected_ids:
                selected.append(item)
                selected_ids.add(item.problem_type_id)
                return

    @staticmethod
    def _importance_key(item: _BlueprintCandidate) -> tuple[float, int, int, int, str, str]:
        return (
            -item.exam_relevance,
            item.chapter_order,
            item.topic_order,
            item.problem_type_order,
            item.problem_type_code,
            str(item.problem_type_id),
        )
