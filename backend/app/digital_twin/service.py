from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classes.access import TeacherStudentAccessService
from app.core.exceptions import ApplicationError
from app.digital_twin.repository import StudentDigitalTwinRepository
from app.digital_twin.schemas import (
    ConceptKnowledgeRead,
    CurriculumSubjectProgressRead,
    DigitalTwinContextType,
    ExamAnalysisAIContextRead,
    KnowledgeStateRead,
    ParentSummaryAIContextRead,
    PlannerAIContextRead,
    PrerequisiteConceptRead,
    ProblemTypeConceptLinkRead,
    ReviewDueRead,
    StudentAIContext,
    StudentDigitalTwinSnapshot,
    SubjectProgressSummaryRead,
    TeacherCopilotAIContextRead,
    TutorAIContextRead,
)
from app.mastery.schemas import ConceptMasteryRead, ProblemTypeMasteryRead
from app.mastery.service import MasteryQueryService
from app.mastery.state import DerivedMasteryState
from app.practice.models import PracticeSessionType
from app.students.models import StudentProfile


class StudentDigitalTwinService:
    """Compose a transient student snapshot from normalized relational sources."""

    RECENT_ATTEMPT_LIMIT = 20

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = StudentDigitalTwinRepository(session)

    def get_snapshot(self, student_id: UUID) -> StudentDigitalTwinSnapshot:
        basic_profile = self.repository.get_basic_profile(student_id)
        mastery = MasteryQueryService(self.session).overview_for_student_id(student_id)

        curriculum_progress = [
            CurriculumSubjectProgressRead.model_validate(
                subject.model_dump(exclude={"concepts"})
            )
            for subject in mastery.subjects
        ]
        concept_masteries = [
            concept for subject in mastery.subjects for concept in subject.concepts
        ]
        problem_type_masteries = [
            problem_type
            for subject in mastery.subjects
            for chapter in subject.chapters
            for topic in chapter.topics
            for problem_type in topic.problem_types
        ]
        knowledge_state = self._knowledge_state(
            concept_masteries, problem_type_masteries
        )
        strong_problem_types = [
            item for item in problem_type_masteries if self._is_strong(item.state)
        ]
        weak_problem_types = [
            item
            for item in problem_type_masteries
            if item.state == DerivedMasteryState.WEAK
        ]
        review_due = ReviewDueRead(
            concepts=[
                item
                for item in knowledge_state.concepts
                if item.state == DerivedMasteryState.REVIEW_DUE
            ],
            problem_types=[
                item
                for item in problem_type_masteries
                if item.state == DerivedMasteryState.REVIEW_DUE
            ],
        )
        return StudentDigitalTwinSnapshot(
            basic_profile=basic_profile,
            curriculum_progress=curriculum_progress,
            knowledge_state=knowledge_state,
            strong_problem_types=strong_problem_types,
            weak_problem_types=weak_problem_types,
            recent_attempts=self.repository.get_recent_attempts(
                student_id, limit=self.RECENT_ATTEMPT_LIMIT
            ),
            review_due=review_due,
            study_behavior=self.repository.get_study_behavior(student_id),
            known_misconceptions=self.repository.get_known_misconceptions(student_id),
        )

    def get_ai_context(
        self,
        student_id: UUID,
        context_type: DigitalTwinContextType | str,
    ) -> StudentAIContext:
        try:
            kind = DigitalTwinContextType(context_type)
        except ValueError:
            raise ApplicationError(
                422, "INVALID_CONTEXT_TYPE", "Digital Twin AI context type is invalid."
            ) from None
        snapshot = self.get_snapshot(student_id)
        summaries = self._subject_summaries(snapshot)

        if kind == DigitalTwinContextType.TUTOR:
            return TutorAIContextRead(
                context_type=kind,
                student_id=student_id,
                weak_problem_types=snapshot.weak_problem_types,
                weak_concepts=snapshot.knowledge_state.weak_concepts,
                problem_type_concept_links=self._links_for_problem_types(
                    snapshot, snapshot.weak_problem_types
                ),
                review_due=snapshot.review_due,
                recent_attempts=snapshot.recent_attempts[:5],
                known_misconceptions=snapshot.known_misconceptions,
            )
        if kind == DigitalTwinContextType.PLANNER:
            return PlannerAIContextRead(
                context_type=kind,
                student_id=student_id,
                grade_level=snapshot.basic_profile.grade_level,
                subject_progress=summaries,
                weak_problem_types=snapshot.weak_problem_types,
                weak_concepts=[
                    self._concept_metric(item)
                    for item in snapshot.knowledge_state.weak_concepts
                ],
                review_due=snapshot.review_due,
                study_behavior=snapshot.study_behavior,
            )
        if kind == DigitalTwinContextType.TEACHER_COPILOT:
            return TeacherCopilotAIContextRead(
                context_type=kind,
                basic_profile=snapshot.basic_profile,
                subject_progress=summaries,
                strong_problem_types=snapshot.strong_problem_types,
                weak_problem_types=snapshot.weak_problem_types,
                strong_concepts=[
                    self._concept_metric(item)
                    for item in snapshot.knowledge_state.strong_concepts
                ],
                weak_concepts=snapshot.knowledge_state.weak_concepts,
                problem_type_concept_links=snapshot.knowledge_state.problem_type_concept_links,
                recent_attempts=snapshot.recent_attempts[:10],
                review_due=snapshot.review_due,
                study_behavior=snapshot.study_behavior,
                known_misconceptions=snapshot.known_misconceptions,
            )
        if kind == DigitalTwinContextType.PARENT_SUMMARY:
            return ParentSummaryAIContextRead(
                context_type=kind,
                student_name=snapshot.basic_profile.full_name,
                grade_level=snapshot.basic_profile.grade_level,
                school_name=snapshot.basic_profile.school_name,
                subject_progress=summaries,
                strengths=self._signal_names(
                    snapshot.strong_problem_types,
                    snapshot.knowledge_state.strong_concepts,
                ),
                areas_for_support=self._signal_names(
                    snapshot.weak_problem_types,
                    snapshot.knowledge_state.weak_concepts,
                ),
                study_behavior=snapshot.study_behavior,
            )
        return ExamAnalysisAIContextRead(
            context_type=kind,
            student_id=student_id,
            subject_progress=summaries,
            recent_exam_attempts=self.repository.get_recent_attempts(
                student_id,
                limit=self.RECENT_ATTEMPT_LIMIT,
                session_type=PracticeSessionType.EXAM,
            ),
            weak_problem_types=snapshot.weak_problem_types,
        )

    def get_snapshot_for_user(self, user_id: UUID) -> StudentDigitalTwinSnapshot:
        student_id = self.session.scalar(
            select(StudentProfile.id).where(StudentProfile.user_id == user_id)
        )
        if student_id is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Student profile was not found.")
        return self.get_snapshot(student_id)

    def get_snapshot_for_teacher(
        self, teacher_user_id: UUID, student_id: UUID
    ) -> StudentDigitalTwinSnapshot:
        TeacherStudentAccessService(self.session).require_active_relationship(
            teacher_user_id, student_id
        )
        return self.get_snapshot(student_id)

    def _knowledge_state(
        self,
        concepts: list[ConceptMasteryRead],
        problem_types: list[ProblemTypeMasteryRead],
    ) -> KnowledgeStateRead:
        concept_by_id = {item.concept_id: item for item in concepts}
        prerequisites_by_target: dict[UUID, list[UUID]] = defaultdict(list)
        for edge in self.repository.get_prerequisite_edges(set(concept_by_id)):
            prerequisites_by_target[edge.target_concept_id].append(
                edge.prerequisite_concept_id
            )

        knowledge: list[ConceptKnowledgeRead] = []
        for concept in concepts:
            prerequisites = [
                PrerequisiteConceptRead(
                    concept_id=prerequisite.concept_id,
                    code=prerequisite.code,
                    name=prerequisite.name,
                    mastery_score=prerequisite.mastery_score,
                    confidence=prerequisite.confidence,
                    state=prerequisite.state,
                )
                for prerequisite_id in prerequisites_by_target[concept.concept_id]
                if (prerequisite := concept_by_id.get(prerequisite_id)) is not None
            ]
            knowledge.append(
                ConceptKnowledgeRead(
                    **concept.model_dump(), prerequisites=prerequisites
                )
            )
        return KnowledgeStateRead(
            concepts=knowledge,
            problem_type_concept_links=self.repository.get_problem_type_concept_links(
                {item.problem_type_id for item in problem_types}
            ),
            strong_concepts=[item for item in knowledge if self._is_strong(item.state)],
            weak_concepts=[
                item for item in knowledge if item.state == DerivedMasteryState.WEAK
            ],
        )

    @staticmethod
    def _subject_summaries(
        snapshot: StudentDigitalTwinSnapshot,
    ) -> list[SubjectProgressSummaryRead]:
        return [
            SubjectProgressSummaryRead(
                subject_id=subject.subject_id,
                code=subject.code,
                name=subject.name,
                mastery_score=subject.mastery_score,
                confidence=subject.confidence,
                state=subject.state,
            )
            for subject in snapshot.curriculum_progress
        ]

    @staticmethod
    def _concept_metric(item: ConceptKnowledgeRead) -> ConceptMasteryRead:
        return ConceptMasteryRead.model_validate(
            item.model_dump(exclude={"prerequisites"})
        )

    @staticmethod
    def _signal_names(
        problem_types: list[ProblemTypeMasteryRead],
        concepts: list[ConceptKnowledgeRead],
    ) -> list[str]:
        return [
            *(f"ProblemType: {item.name}" for item in problem_types),
            *(f"Concept: {item.name}" for item in concepts),
        ]

    @staticmethod
    def _links_for_problem_types(
        snapshot: StudentDigitalTwinSnapshot,
        problem_types: list[ProblemTypeMasteryRead],
    ) -> list[ProblemTypeConceptLinkRead]:
        problem_type_ids = {item.problem_type_id for item in problem_types}
        return [
            item
            for item in snapshot.knowledge_state.problem_type_concept_links
            if item.problem_type_id in problem_type_ids
        ]

    @staticmethod
    def _is_strong(state: DerivedMasteryState) -> bool:
        return state in {
            DerivedMasteryState.MASTERED,
            DerivedMasteryState.REVIEW_DUE,
        }
