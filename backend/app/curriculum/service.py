import logging
from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import (
    Chapter,
    Curriculum,
    CurriculumVersion,
    LearningOutcome,
    ProblemType,
    ProblemTypeConcept,
    ProblemTypeLearningOutcome,
    Topic,
)
from app.curriculum.schemas import (
    ChapterCreate,
    ChapterTreeNode,
    CurriculumCreate,
    CurriculumVersionCreate,
    LearningOutcomeCreate,
    ProblemTypeConceptCreate,
    ProblemTypeDetail,
    ProblemTypeLearningOutcomeCreate,
    ProblemTypeRead,
    ProblemTypeTreeNode,
    SubjectTree,
    TopicCreate,
    TopicTreeNode,
    ProblemTypeCreate,
)
from app.subjects.models import Subject

logger = logging.getLogger(__name__)


class CurriculumService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_curriculum(self, data: CurriculumCreate) -> Curriculum:
        return self._create_unique(
            Curriculum(**data.model_dump()),
            select(Curriculum.id).where(Curriculum.code == data.code),
            "CURRICULUM_CODE_EXISTS",
            "Curriculum code already exists.",
        )

    def list_curricula(self) -> list[Curriculum]:
        return list(self.session.scalars(select(Curriculum).order_by(Curriculum.code)))

    def create_version(self, data: CurriculumVersionCreate) -> CurriculumVersion:
        self._require(Curriculum, data.curriculum_id, "CURRICULUM_NOT_FOUND")
        return self._create_unique(
            CurriculumVersion(**data.model_dump()),
            select(CurriculumVersion.id).where(
                CurriculumVersion.curriculum_id == data.curriculum_id,
                CurriculumVersion.code == data.code,
            ),
            "CURRICULUM_VERSION_CODE_EXISTS",
            "Curriculum version code already exists for this curriculum.",
        )

    def list_versions(self, curriculum_id: UUID | None = None) -> list[CurriculumVersion]:
        statement = select(CurriculumVersion)
        if curriculum_id is not None:
            statement = statement.where(CurriculumVersion.curriculum_id == curriculum_id)
        return list(
            self.session.scalars(
                statement.order_by(CurriculumVersion.curriculum_id, CurriculumVersion.code)
            )
        )

    def create_chapter(self, data: ChapterCreate) -> Chapter:
        self._require(Subject, data.subject_id, "SUBJECT_NOT_FOUND")
        return self._create_unique(
            Chapter(**data.model_dump()),
            select(Chapter.id).where(
                Chapter.subject_id == data.subject_id, Chapter.code == data.code
            ),
            "CHAPTER_CODE_EXISTS",
            "Chapter code already exists for this subject.",
        )

    def create_topic(self, data: TopicCreate) -> Topic:
        self._require(Chapter, data.chapter_id, "CHAPTER_NOT_FOUND")
        return self._create_unique(
            Topic(**data.model_dump()),
            select(Topic.id).where(Topic.chapter_id == data.chapter_id, Topic.code == data.code),
            "TOPIC_CODE_EXISTS",
            "Topic code already exists for this chapter.",
        )

    def create_problem_type(self, data: ProblemTypeCreate) -> ProblemType:
        self._require(Topic, data.topic_id, "TOPIC_NOT_FOUND")
        return self._create_unique(
            ProblemType(**data.model_dump()),
            select(ProblemType.id).where(
                ProblemType.topic_id == data.topic_id, ProblemType.code == data.code
            ),
            "PROBLEM_TYPE_CODE_EXISTS",
            "Problem type code already exists for this topic.",
        )

    def create_learning_outcome(self, data: LearningOutcomeCreate) -> LearningOutcome:
        self._require(Subject, data.subject_id, "SUBJECT_NOT_FOUND")
        return self._create_unique(
            LearningOutcome(**data.model_dump()),
            select(LearningOutcome.id).where(
                LearningOutcome.subject_id == data.subject_id,
                LearningOutcome.code == data.code,
            ),
            "LEARNING_OUTCOME_CODE_EXISTS",
            "Learning outcome code already exists for this subject.",
        )

    def map_problem_type_concept(
        self, data: ProblemTypeConceptCreate
    ) -> ProblemTypeConcept:
        problem_type = self._require(
            ProblemType, data.problem_type_id, "PROBLEM_TYPE_NOT_FOUND"
        )
        concept = self._require(Concept, data.concept_id, "CONCEPT_NOT_FOUND")
        if self._problem_type_subject(problem_type.id) != concept.subject_id:
            raise ApplicationError(
                422,
                "PROBLEM_TYPE_CONCEPT_SUBJECT_MISMATCH",
                "Problem type and concept must belong to the same subject.",
            )
        return self._create_unique(
            ProblemTypeConcept(**data.model_dump()),
            select(ProblemTypeConcept.problem_type_id).where(
                ProblemTypeConcept.problem_type_id == data.problem_type_id,
                ProblemTypeConcept.concept_id == data.concept_id,
            ),
            "PROBLEM_TYPE_CONCEPT_EXISTS",
            "Problem type concept mapping already exists.",
        )

    def map_problem_type_learning_outcome(
        self, data: ProblemTypeLearningOutcomeCreate
    ) -> ProblemTypeLearningOutcome:
        problem_type = self._require(
            ProblemType, data.problem_type_id, "PROBLEM_TYPE_NOT_FOUND"
        )
        outcome = self._require(
            LearningOutcome, data.learning_outcome_id, "LEARNING_OUTCOME_NOT_FOUND"
        )
        if self._problem_type_subject(problem_type.id) != outcome.subject_id:
            raise ApplicationError(
                422,
                "PROBLEM_TYPE_OUTCOME_SUBJECT_MISMATCH",
                "Problem type and learning outcome must belong to the same subject.",
            )
        return self._create_unique(
            ProblemTypeLearningOutcome(**data.model_dump()),
            select(ProblemTypeLearningOutcome.problem_type_id).where(
                ProblemTypeLearningOutcome.problem_type_id == data.problem_type_id,
                ProblemTypeLearningOutcome.learning_outcome_id == data.learning_outcome_id,
            ),
            "PROBLEM_TYPE_OUTCOME_EXISTS",
            "Problem type learning outcome mapping already exists.",
        )

    def get_chapters(self, subject_id: UUID) -> list[Chapter]:
        self._require(Subject, subject_id, "SUBJECT_NOT_FOUND")
        return list(
            self.session.scalars(
                select(Chapter)
                .where(Chapter.subject_id == subject_id)
                .order_by(Chapter.order_index, Chapter.code)
            )
        )

    def get_topics(self, chapter_id: UUID) -> list[Topic]:
        self._require(Chapter, chapter_id, "CHAPTER_NOT_FOUND")
        return list(
            self.session.scalars(
                select(Topic)
                .where(Topic.chapter_id == chapter_id)
                .order_by(Topic.order_index, Topic.code)
            )
        )

    def get_problem_types(self, topic_id: UUID) -> list[ProblemType]:
        self._require(Topic, topic_id, "TOPIC_NOT_FOUND")
        return list(
            self.session.scalars(
                select(ProblemType)
                .where(ProblemType.topic_id == topic_id)
                .order_by(ProblemType.order_index, ProblemType.code)
            )
        )

    def get_learning_outcomes(self, subject_id: UUID) -> list[LearningOutcome]:
        self._require(Subject, subject_id, "SUBJECT_NOT_FOUND")
        return list(
            self.session.scalars(
                select(LearningOutcome)
                .where(LearningOutcome.subject_id == subject_id)
                .order_by(
                    LearningOutcome.order_index.nulls_last(), LearningOutcome.code
                )
            )
        )

    def get_problem_type_concepts(self, problem_type_id: UUID) -> list[ProblemTypeConcept]:
        self._require(ProblemType, problem_type_id, "PROBLEM_TYPE_NOT_FOUND")
        return list(
            self.session.scalars(
                select(ProblemTypeConcept)
                .where(ProblemTypeConcept.problem_type_id == problem_type_id)
                .order_by(ProblemTypeConcept.is_primary.desc(), ProblemTypeConcept.concept_id)
            )
        )

    def get_problem_type_learning_outcomes(
        self, problem_type_id: UUID
    ) -> list[ProblemTypeLearningOutcome]:
        self._require(ProblemType, problem_type_id, "PROBLEM_TYPE_NOT_FOUND")
        return list(
            self.session.scalars(
                select(ProblemTypeLearningOutcome)
                .where(ProblemTypeLearningOutcome.problem_type_id == problem_type_id)
                .order_by(ProblemTypeLearningOutcome.learning_outcome_id)
            )
        )

    def get_problem_type_detail(self, problem_type_id: UUID) -> ProblemTypeDetail:
        problem_type = self._require(
            ProblemType, problem_type_id, "PROBLEM_TYPE_NOT_FOUND"
        )
        return ProblemTypeDetail(
            **ProblemTypeRead.model_validate(problem_type).model_dump(),
            concepts=self.get_problem_type_concepts(problem_type_id),
            learning_outcomes=self.get_problem_type_learning_outcomes(problem_type_id),
        )

    def get_subject_tree(self, subject_id: UUID) -> SubjectTree:
        subject = self._require(Subject, subject_id, "SUBJECT_NOT_FOUND")
        chapters = self.get_chapters(subject_id)
        chapter_ids = [chapter.id for chapter in chapters]
        topics = list(
            self.session.scalars(
                select(Topic)
                .where(Topic.chapter_id.in_(chapter_ids))
                .order_by(Topic.chapter_id, Topic.order_index, Topic.code)
            )
        ) if chapter_ids else []
        topic_ids = [topic.id for topic in topics]
        problem_types = list(
            self.session.scalars(
                select(ProblemType)
                .where(ProblemType.topic_id.in_(topic_ids))
                .order_by(ProblemType.topic_id, ProblemType.order_index, ProblemType.code)
            )
        ) if topic_ids else []
        problem_ids = [problem.id for problem in problem_types]
        concept_counts = dict(self.session.execute(
            select(ProblemTypeConcept.problem_type_id, func.count())
            .where(ProblemTypeConcept.problem_type_id.in_(problem_ids))
            .group_by(ProblemTypeConcept.problem_type_id)
        ).all()) if problem_ids else {}
        outcome_counts = dict(self.session.execute(
            select(ProblemTypeLearningOutcome.problem_type_id, func.count())
            .where(ProblemTypeLearningOutcome.problem_type_id.in_(problem_ids))
            .group_by(ProblemTypeLearningOutcome.problem_type_id)
        ).all()) if problem_ids else {}
        problems_by_topic: dict[UUID, list[ProblemTypeTreeNode]] = defaultdict(list)
        for problem in problem_types:
            problems_by_topic[problem.topic_id].append(ProblemTypeTreeNode(
                id=problem.id,
                code=problem.code,
                name=problem.name,
                order_index=problem.order_index,
                is_active=problem.is_active,
                concept_count=concept_counts.get(problem.id, 0),
                learning_outcome_count=outcome_counts.get(problem.id, 0),
            ))
        topics_by_chapter: dict[UUID, list[TopicTreeNode]] = defaultdict(list)
        for topic in topics:
            topics_by_chapter[topic.chapter_id].append(TopicTreeNode(
                id=topic.id,
                code=topic.code,
                name=topic.name,
                order_index=topic.order_index,
                problem_types=problems_by_topic[topic.id],
            ))
        return SubjectTree(
            id=subject.id,
            curriculum_version_id=subject.curriculum_version_id,
            code=subject.code,
            name=subject.name,
            grade_level=subject.grade_level,
            chapters=[ChapterTreeNode(
                id=chapter.id,
                code=chapter.code,
                name=chapter.name,
                order_index=chapter.order_index,
                topics=topics_by_chapter[chapter.id],
            ) for chapter in chapters],
        )

    def _problem_type_subject(self, problem_type_id: UUID) -> UUID:
        subject_id = self.session.scalar(
            select(Chapter.subject_id)
            .join(Topic, Topic.chapter_id == Chapter.id)
            .join(ProblemType, ProblemType.topic_id == Topic.id)
            .where(ProblemType.id == problem_type_id)
        )
        assert subject_id is not None
        return subject_id

    def _create_unique(self, instance, exists, code: str, message: str):
        if self.session.scalar(exists) is not None:
            raise ApplicationError(409, code, message)
        self.session.add(instance)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            if self.session.scalar(exists) is not None:
                raise ApplicationError(409, code, message) from None
            raise
        self.session.refresh(instance)
        logger.info("Curriculum entity created (type=%s, id=%s)", type(instance).__name__, getattr(instance, "id", None))
        return instance

    def _require(self, model, entity_id: UUID, code: str):
        entity = self.session.get(model, entity_id)
        if entity is None:
            raise ApplicationError(404, code, code.replace("_", " ").title())
        return entity
