from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from app.classes.access import TeacherStudentAccessService
from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, ProblemTypeConcept, Topic
from app.questions.models import Question, QuestionProblemType, QuestionStatus, QuestionType
from app.questions.eligibility import standalone_question_only
from app.mastery.aggregation import MasteryAggregationService, MasterySnapshot
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.mastery.schemas import (
    ChapterMasteryRead,
    ConceptMasteryRead,
    ProblemTypeMasteryRead,
    StudentMasteryRead,
    SubjectMasteryRead,
    TopicMasteryRead,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject


class MasteryQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.aggregation = MasteryAggregationService(session)

    def overview_for_student_user(self, user_id: UUID) -> StudentMasteryRead:
        student = self._student_for_user(user_id)
        return self._overview(student.id)

    def problem_type_for_student_user(
        self, user_id: UUID, problem_type_id: UUID
    ) -> ProblemTypeMasteryRead:
        student = self._student_for_user(user_id)
        return self._problem_type_read(student.id, problem_type_id)

    def concept_for_student_user(
        self, user_id: UUID, concept_id: UUID
    ) -> ConceptMasteryRead:
        student = self._student_for_user(user_id)
        return self._concept_read(student.id, concept_id)

    def overview_for_teacher(
        self, teacher_user_id: UUID, student_id: UUID
    ) -> StudentMasteryRead:
        self._authorize_teacher_student(teacher_user_id, student_id)
        return self._overview(student_id)

    def overview_for_student_id(self, student_id: UUID) -> StudentMasteryRead:
        if self.session.get(StudentProfile, student_id) is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile was not found.")
        return self._overview(student_id)

    def _overview(self, student_id: UUID) -> StudentMasteryRead:
        subjects = list(
            self.session.scalars(
                select(Subject).order_by(Subject.order_index, Subject.code, Subject.id)
            )
        )
        chapters = list(
            self.session.scalars(
                select(Chapter).order_by(
                    Chapter.subject_id, Chapter.order_index, Chapter.code, Chapter.id
                )
            )
        )
        topics = list(
            self.session.scalars(
                select(Topic).order_by(
                    Topic.chapter_id, Topic.order_index, Topic.code, Topic.id
                )
            )
        )
        problem_types = list(
            self.session.scalars(
                select(ProblemType)
                .where(ProblemType.is_active.is_(True))
                .order_by(
                    ProblemType.topic_id,
                    ProblemType.order_index,
                    ProblemType.code,
                    ProblemType.id,
                )
            )
        )
        concepts = list(
            self.session.scalars(
                select(Concept).order_by(
                    Concept.subject_id, Concept.order_index, Concept.code, Concept.id
                )
            )
        )
        supply = self._supply_metadata([p.id for p in problem_types])
        problem_mastery = {
            item.problem_type_id: item
            for item in self.session.scalars(
                select(StudentProblemTypeMastery).where(
                    StudentProblemTypeMastery.student_id == student_id
                )
            )
        }
        concept_mastery = {
            item.concept_id: item
            for item in self.session.scalars(
                select(StudentConceptMastery).where(
                    StudentConceptMastery.student_id == student_id
                )
            )
        }

        chapters_by_subject: dict[UUID, list[Chapter]] = defaultdict(list)
        topics_by_chapter: dict[UUID, list[Topic]] = defaultdict(list)
        problems_by_topic: dict[UUID, list[ProblemType]] = defaultdict(list)
        concepts_by_subject: dict[UUID, list[Concept]] = defaultdict(list)
        for chapter in chapters:
            chapters_by_subject[chapter.subject_id].append(chapter)
        for topic in topics:
            topics_by_chapter[topic.chapter_id].append(topic)
        for problem_type in problem_types:
            problems_by_topic[problem_type.topic_id].append(problem_type)
        for concept in concepts:
            concepts_by_subject[concept.subject_id].append(concept)

        subject_reads: list[SubjectMasteryRead] = []
        for subject in subjects:
            chapter_reads: list[ChapterMasteryRead] = []
            subject_problem_rows: list[StudentProblemTypeMastery | None] = []
            for chapter in chapters_by_subject[subject.id]:
                topic_reads: list[TopicMasteryRead] = []
                chapter_problem_rows: list[StudentProblemTypeMastery | None] = []
                for topic in topics_by_chapter[chapter.id]:
                    problem_reads: list[ProblemTypeMasteryRead] = []
                    topic_rows: list[StudentProblemTypeMastery | None] = []
                    for problem_type in problems_by_topic[topic.id]:
                        row = problem_mastery.get(problem_type.id)
                        topic_rows.append(row)
                        problem_reads.append(
                            self._problem_type_from_parts(
                                problem_type, self.aggregation.snapshot(row)
                            ).model_copy(update=supply[problem_type.id])
                        )
                    chapter_problem_rows.extend(topic_rows)
                    subject_problem_rows.extend(topic_rows)
                    topic_reads.append(
                        TopicMasteryRead(
                            topic_id=topic.id,
                            chapter_id=topic.chapter_id,
                            code=topic.code,
                            name=topic.name,
                            problem_types=problem_reads,
                            **self._metric(self.aggregation.aggregate(topic_rows)),
                        )
                    )
                chapter_reads.append(
                    ChapterMasteryRead(
                        chapter_id=chapter.id,
                        subject_id=chapter.subject_id,
                        code=chapter.code,
                        name=chapter.name,
                        topics=topic_reads,
                        **self._metric(self.aggregation.aggregate(chapter_problem_rows)),
                    )
                )

            concept_reads = [
                self._concept_from_parts(
                    concept, self.aggregation.snapshot(concept_mastery.get(concept.id))
                )
                for concept in concepts_by_subject[subject.id]
            ]
            subject_reads.append(
                SubjectMasteryRead(
                    subject_id=subject.id,
                    code=subject.code,
                    name=subject.name,
                    chapters=chapter_reads,
                    concepts=concept_reads,
                    **self._metric(self.aggregation.aggregate(subject_problem_rows)),
                )
            )
        return StudentMasteryRead(student_id=student_id, subjects=subject_reads)

    def _problem_type_read(
        self, student_id: UUID, problem_type_id: UUID
    ) -> ProblemTypeMasteryRead:
        problem_type = self.session.get(ProblemType, problem_type_id)
        if problem_type is None:
            raise ApplicationError(
                404, "PROBLEM_TYPE_NOT_FOUND", "Problem type was not found."
            )
        snapshot = self.aggregation.get_problem_type_mastery(student_id, problem_type_id)
        return self._problem_type_from_parts(problem_type, snapshot).model_copy(
            update=self._supply_metadata([problem_type_id])[problem_type_id])

    def _supply_metadata(self, problem_ids: list[UUID]) -> dict:
        metadata = {identifier: {"concept_ids": [], "available_question_count": 0} for identifier in problem_ids}
        for problem_id, concept_id in self.session.execute(select(
            ProblemTypeConcept.problem_type_id, ProblemTypeConcept.concept_id
        ).where(ProblemTypeConcept.problem_type_id.in_(problem_ids))):
            metadata[problem_id]["concept_ids"].append(concept_id)
        for problem_id, count in self.session.execute(select(
            QuestionProblemType.problem_type_id, func.count(func.distinct(Question.id))
        ).join(Question, Question.id == QuestionProblemType.question_id).where(
            QuestionProblemType.problem_type_id.in_(problem_ids), Question.status == QuestionStatus.APPROVED,
            standalone_question_only(), Question.concept_links.any(), Question.learning_outcome_links.any(),
            or_(Question.question_type == QuestionType.OPEN_RESPONSE, Question.correct_answer.is_not(None)),
        ).group_by(QuestionProblemType.problem_type_id)):
            metadata[problem_id]["available_question_count"] = count
        return metadata

    def _concept_read(self, student_id: UUID, concept_id: UUID) -> ConceptMasteryRead:
        concept = self.session.get(Concept, concept_id)
        if concept is None:
            raise ApplicationError(404, "CONCEPT_NOT_FOUND", "Concept was not found.")
        snapshot = self.aggregation.get_concept_mastery(student_id, concept_id)
        return self._concept_from_parts(concept, snapshot)

    def _authorize_teacher_student(self, teacher_user_id: UUID, student_id: UUID) -> None:
        TeacherStudentAccessService(self.session).require_active_relationship(
            teacher_user_id,
            student_id,
            denied_code="STUDENT_MASTERY_ACCESS_DENIED",
        )

    def _student_for_user(self, user_id: UUID) -> StudentProfile:
        student = self.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        if student is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Student profile was not found.")
        return student

    @staticmethod
    def _problem_type_from_parts(
        problem_type: ProblemType, snapshot: MasterySnapshot
    ) -> ProblemTypeMasteryRead:
        return ProblemTypeMasteryRead(
            problem_type_id=problem_type.id,
            topic_id=problem_type.topic_id,
            code=problem_type.code,
            name=problem_type.name,
            **MasteryQueryService._metric(snapshot, include_aggregate=False),
        )

    @staticmethod
    def _concept_from_parts(
        concept: Concept, snapshot: MasterySnapshot
    ) -> ConceptMasteryRead:
        return ConceptMasteryRead(
            concept_id=concept.id,
            subject_id=concept.subject_id,
            code=concept.code,
            name=concept.name,
            **MasteryQueryService._metric(snapshot, include_aggregate=False),
        )

    @staticmethod
    def _metric(
        snapshot: MasterySnapshot, *, include_aggregate: bool = True
    ) -> dict[str, Any]:
        values: dict[str, Any] = {
            "mastery_score": snapshot.mastery_score,
            "confidence": snapshot.confidence,
            "attempt_count": snapshot.attempt_count,
            "correct_count": snapshot.correct_count,
            "last_practiced_at": snapshot.last_practiced_at,
            "last_updated_at": snapshot.last_updated_at,
            "state": snapshot.state,
        }
        if include_aggregate:
            values.update(
                problem_type_count=snapshot.problem_type_count,
                started_problem_type_count=snapshot.started_problem_type_count,
            )
        return values
