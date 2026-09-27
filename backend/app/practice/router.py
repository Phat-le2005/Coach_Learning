from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_gateway
from app.ai.gateway import AIGateway
from app.auth.dependencies import require_any_role, require_role
from app.core.errors import ErrorResponse
from app.core.exceptions import ApplicationError
from app.database.session import get_db
from app.practice.models import QuestionAttempt
from app.practice.open_response_evaluator import AIOpenResponseEvaluationService
from app.practice.open_response_schemas import AIEvaluateAttemptRequest
from app.practice.schemas import (
    PracticeAnswerCreate,
    PracticeGroupAnswerCreate,
    PracticeItemRead,
    PracticeQuestionRead,
    PracticeSessionCreate,
    PracticeSessionRead,
    QuestionAttemptRead,
    QuestionGroupAttemptRead,
)
from app.practice.service import PracticeService
from app.students.models import StudentProfile
from app.users.models import Role, User

router = APIRouter(
    prefix="/practice",
    tags=["Practice"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)

StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]
Database = Annotated[Session, Depends(get_db)]


@router.post(
    "/sessions",
    response_model=PracticeSessionRead,
    status_code=http_status.HTTP_201_CREATED,
)
def create_practice_session(
    data: PracticeSessionCreate, current_user: StudentUser, session: Database
) -> PracticeSessionRead:
    service = PracticeService(session)
    return service.to_read(service.create_session(current_user, data))


@router.get("/sessions/{practice_session_id}", response_model=PracticeSessionRead)
def get_practice_session(
    practice_session_id: UUID, current_user: StudentUser, session: Database
) -> PracticeSessionRead:
    service = PracticeService(session)
    return service.to_read(service.get_session(current_user, practice_session_id))


@router.get(
    "/sessions/{practice_session_id}/next-question",
    response_model=PracticeQuestionRead,
)
def get_next_practice_question(
    practice_session_id: UUID, current_user: StudentUser, session: Database
) -> PracticeQuestionRead:
    question = PracticeService(session).get_next_question(current_user, practice_session_id)
    return PracticeQuestionRead.model_validate(question)


@router.get(
    "/sessions/{practice_session_id}/next-item",
    response_model=PracticeItemRead,
)
def get_next_practice_item(
    practice_session_id: UUID, current_user: StudentUser, session: Database
) -> PracticeItemRead:
    return PracticeService(session).get_next_item(current_user, practice_session_id)


@router.post(
    "/sessions/{practice_session_id}/answer",
    response_model=QuestionAttemptRead,
    status_code=http_status.HTTP_201_CREATED,
)
def answer_practice_question(
    practice_session_id: UUID,
    data: PracticeAnswerCreate,
    current_user: StudentUser,
    session: Database,
) -> QuestionAttemptRead:
    attempt = PracticeService(session).answer(current_user, practice_session_id, data)
    return QuestionAttemptRead.model_validate(attempt)


@router.post(
    "/sessions/{practice_session_id}/group-answer",
    response_model=QuestionGroupAttemptRead,
    status_code=http_status.HTTP_201_CREATED,
)
def answer_practice_question_group(
    practice_session_id: UUID,
    data: PracticeGroupAnswerCreate,
    current_user: StudentUser,
    session: Database,
) -> QuestionGroupAttemptRead:
    attempt = PracticeService(session).answer_group(
        current_user, practice_session_id, data
    )
    return QuestionGroupAttemptRead.model_validate(attempt)


@router.post(
    "/attempts/{attempt_id}/ai-evaluate",
    response_model=QuestionAttemptRead,
)
async def evaluate_open_response_attempt(
    attempt_id: UUID,
    current_user: Annotated[User, Depends(require_any_role(Role.STUDENT, Role.TEACHER, Role.ADMIN))],
    session: Database,
    gateway: Annotated[AIGateway, Depends(get_ai_gateway)],
    data: AIEvaluateAttemptRequest | None = None,
) -> QuestionAttemptRead:
    attempt = session.get(QuestionAttempt, attempt_id)
    if attempt is None:
        raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Question attempt not found.")

    if current_user.role == Role.STUDENT:
        student = session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == current_user.id)
        )
        if student is None or attempt.student_id != student.id:
            raise ApplicationError(
                403, "ACCESS_DENIED", "You do not have access to evaluate this attempt."
            )

    eval_data = data or AIEvaluateAttemptRequest()
    service = AIOpenResponseEvaluationService(session, gateway=gateway)
    evaluated = await service.evaluate_attempt(
        attempt_id,
        rubric=eval_data.rubric,
        confidence_threshold=eval_data.confidence_threshold,
    )
    return QuestionAttemptRead.model_validate(evaluated)
