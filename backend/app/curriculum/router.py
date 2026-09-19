from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.curriculum.schemas import (
    ChapterCreate,
    ChapterRead,
    CurriculumCreate,
    CurriculumRead,
    CurriculumVersionCreate,
    CurriculumVersionRead,
    LearningOutcomeCreate,
    LearningOutcomeRead,
    ProblemTypeConceptCreate,
    ProblemTypeConceptRead,
    ProblemTypeCreate,
    ProblemTypeDetail,
    ProblemTypeLearningOutcomeCreate,
    ProblemTypeLearningOutcomeRead,
    ProblemTypeRead,
    SubjectTree,
    TopicCreate,
    TopicRead,
)
from app.curriculum.service import CurriculumService
from app.database.session import get_db
from app.users.models import Role

router = APIRouter(
    prefix="/admin",
    tags=["Admin curriculum"],
    dependencies=[Depends(require_role(Role.ADMIN))],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
Database = Annotated[Session, Depends(get_db)]


@router.post("/curricula", response_model=CurriculumRead, status_code=201)
def create_curriculum(data: CurriculumCreate, session: Database) -> CurriculumRead:
    return CurriculumRead.model_validate(CurriculumService(session).create_curriculum(data))


@router.get("/curricula", response_model=list[CurriculumRead])
def list_curricula(session: Database) -> list[CurriculumRead]:
    return [
        CurriculumRead.model_validate(item)
        for item in CurriculumService(session).list_curricula()
    ]


@router.post("/curriculum-versions", response_model=CurriculumVersionRead, status_code=201)
def create_curriculum_version(
    data: CurriculumVersionCreate, session: Database
) -> CurriculumVersionRead:
    return CurriculumVersionRead.model_validate(CurriculumService(session).create_version(data))


@router.get("/curriculum-versions", response_model=list[CurriculumVersionRead])
def list_curriculum_versions(
    session: Database, curriculum_id: UUID | None = None
) -> list[CurriculumVersionRead]:
    return [
        CurriculumVersionRead.model_validate(item)
        for item in CurriculumService(session).list_versions(curriculum_id)
    ]


@router.post("/chapters", response_model=ChapterRead, status_code=201)
def create_chapter(data: ChapterCreate, session: Database) -> ChapterRead:
    return ChapterRead.model_validate(CurriculumService(session).create_chapter(data))


@router.get("/subjects/{subject_id}/chapters", response_model=list[ChapterRead])
def list_chapters(subject_id: UUID, session: Database) -> list[ChapterRead]:
    return [
        ChapterRead.model_validate(item)
        for item in CurriculumService(session).get_chapters(subject_id)
    ]


@router.post("/topics", response_model=TopicRead, status_code=201)
def create_topic(data: TopicCreate, session: Database) -> TopicRead:
    return TopicRead.model_validate(CurriculumService(session).create_topic(data))


@router.get("/chapters/{chapter_id}/topics", response_model=list[TopicRead])
def list_topics(chapter_id: UUID, session: Database) -> list[TopicRead]:
    return [
        TopicRead.model_validate(item)
        for item in CurriculumService(session).get_topics(chapter_id)
    ]


@router.post("/problem-types", response_model=ProblemTypeRead, status_code=201)
def create_problem_type(data: ProblemTypeCreate, session: Database) -> ProblemTypeRead:
    return ProblemTypeRead.model_validate(
        CurriculumService(session).create_problem_type(data)
    )


@router.get("/topics/{topic_id}/problem-types", response_model=list[ProblemTypeRead])
def list_problem_types(topic_id: UUID, session: Database) -> list[ProblemTypeRead]:
    return [
        ProblemTypeRead.model_validate(item)
        for item in CurriculumService(session).get_problem_types(topic_id)
    ]


@router.get("/problem-types/{problem_type_id}", response_model=ProblemTypeDetail)
def get_problem_type(problem_type_id: UUID, session: Database) -> ProblemTypeDetail:
    return CurriculumService(session).get_problem_type_detail(problem_type_id)


@router.post("/learning-outcomes", response_model=LearningOutcomeRead, status_code=201)
def create_learning_outcome(
    data: LearningOutcomeCreate, session: Database
) -> LearningOutcomeRead:
    return LearningOutcomeRead.model_validate(
        CurriculumService(session).create_learning_outcome(data)
    )


@router.get(
    "/subjects/{subject_id}/learning-outcomes",
    response_model=list[LearningOutcomeRead],
)
def list_learning_outcomes(
    subject_id: UUID, session: Database
) -> list[LearningOutcomeRead]:
    return [
        LearningOutcomeRead.model_validate(item)
        for item in CurriculumService(session).get_learning_outcomes(subject_id)
    ]


@router.post(
    "/problem-type-concepts", response_model=ProblemTypeConceptRead, status_code=201
)
def map_problem_type_concept(
    data: ProblemTypeConceptCreate, session: Database
) -> ProblemTypeConceptRead:
    return ProblemTypeConceptRead.model_validate(
        CurriculumService(session).map_problem_type_concept(data)
    )


@router.post(
    "/problem-type-learning-outcomes",
    response_model=ProblemTypeLearningOutcomeRead,
    status_code=201,
)
def map_problem_type_learning_outcome(
    data: ProblemTypeLearningOutcomeCreate, session: Database
) -> ProblemTypeLearningOutcomeRead:
    return ProblemTypeLearningOutcomeRead.model_validate(
        CurriculumService(session).map_problem_type_learning_outcome(data)
    )


@router.get("/subjects/{subject_id}/curriculum-tree", response_model=SubjectTree)
def get_curriculum_tree(subject_id: UUID, session: Database) -> SubjectTree:
    return CurriculumService(session).get_subject_tree(subject_id)
