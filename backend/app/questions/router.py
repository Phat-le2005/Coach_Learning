from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status as http_status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_any_role, require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.questions.models import CognitiveLevel, QuestionStatus, QuestionType
from app.questions.import_schemas import QuestionImportBatchRead
from app.questions.import_service import QuestionImportService
from app.questions.schemas import QuestionCreate, QuestionPatch, QuestionRead
from app.questions.service import QuestionService
from app.users.models import Role, User

router = APIRouter(
    prefix="/questions",
    tags=["Question Bank"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)

TeacherUser = Annotated[User, Depends(require_role(Role.TEACHER))]
StaffUser = Annotated[User, Depends(require_any_role(Role.TEACHER, Role.ADMIN))]
AdminUser = Annotated[User, Depends(require_role(Role.ADMIN))]
Database = Annotated[Session, Depends(get_db)]


@router.post("", response_model=QuestionRead, status_code=http_status.HTTP_201_CREATED)
def create_question(data: QuestionCreate, current_user: TeacherUser, session: Database) -> QuestionRead:
    return QuestionRead.model_validate(QuestionService(session).create(current_user, data))


@router.get("", response_model=list[QuestionRead])
def list_questions(
    current_user: StaffUser,
    session: Database,
    subject: UUID | None = None,
    concept: UUID | None = None,
    problem_type: UUID | None = None,
    learning_outcome: UUID | None = None,
    difficulty_min: Annotated[float | None, Query(ge=0.0, le=1.0, allow_inf_nan=False)] = None,
    difficulty_max: Annotated[float | None, Query(ge=0.0, le=1.0, allow_inf_nan=False)] = None,
    question_type: QuestionType | None = None,
    status: QuestionStatus | None = None,
    cognitive_level: CognitiveLevel | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[QuestionRead]:
    questions = QuestionService(session).list(
        current_user,
        subject_id=subject,
        concept_id=concept,
        problem_type_id=problem_type,
        learning_outcome_id=learning_outcome,
        difficulty_min=difficulty_min,
        difficulty_max=difficulty_max,
        question_type=question_type,
        status=status,
        cognitive_level=cognitive_level,
        offset=offset,
        limit=limit,
    )
    return [QuestionRead.model_validate(question) for question in questions]


@router.post(
    "/import/preview",
    response_model=QuestionImportBatchRead,
    status_code=http_status.HTTP_201_CREATED,
)
async def preview_question_import(
    current_user: StaffUser,
    session: Database,
    file: Annotated[UploadFile, File()],
    trusted_seed_data: bool = False,
) -> QuestionImportBatchRead:
    content = await file.read(QuestionImportService.MAX_FILE_BYTES + 1)
    await file.close()
    return QuestionImportService(session).preview(
        current_user,
        file_name=file.filename or "upload",
        content=content,
        trusted_seed_data=trusted_seed_data,
    )


@router.post("/import/{batch_id}/confirm", response_model=QuestionImportBatchRead)
def confirm_question_import(
    batch_id: UUID, current_user: StaffUser, session: Database
) -> QuestionImportBatchRead:
    return QuestionImportService(session).confirm(current_user, batch_id)


@router.post("/{question_id}/submit-review", response_model=QuestionRead)
def submit_question_for_review(
    question_id: UUID, current_user: StaffUser, session: Database
) -> QuestionRead:
    return QuestionRead.model_validate(
        QuestionService(session).submit_review(current_user, question_id)
    )


@router.post("/{question_id}/approve", response_model=QuestionRead)
def approve_question(
    question_id: UUID, current_user: AdminUser, session: Database
) -> QuestionRead:
    return QuestionRead.model_validate(QuestionService(session).approve(current_user, question_id))


@router.get("/{question_id}", response_model=QuestionRead)
def get_question(question_id: UUID, current_user: StaffUser, session: Database) -> QuestionRead:
    return QuestionRead.model_validate(QuestionService(session).get(current_user, question_id))


@router.patch("/{question_id}", response_model=QuestionRead)
def patch_question(
    question_id: UUID, data: QuestionPatch, current_user: StaffUser, session: Database
) -> QuestionRead:
    return QuestionRead.model_validate(QuestionService(session).patch(current_user, question_id, data))
