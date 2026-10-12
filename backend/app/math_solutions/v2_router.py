from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.math_solutions.schemas import (
    AttemptCreateRequest,
    AttemptMutationToken,
    ReorderStepsRequest,
    RollbackStepRequest,
    SolutionAttemptRead,
    StepMutationRequest,
    StepRevisionRead,
)
from app.math_solutions.service import MathSolutionService
from app.users.models import Role, User


def _disable_solution_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


router = APIRouter(
    prefix="/math-solutions",
    tags=["Math Solutions"],
    dependencies=[Depends(_disable_solution_caching)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)

StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]
Database = Annotated[Session, Depends(get_db)]


@router.post(
    "/attempts",
    response_model=SolutionAttemptRead,
    status_code=status.HTTP_201_CREATED,
)
def create_attempt(
    data: AttemptCreateRequest,
    current_user: StudentUser,
    session: Database,
) -> dict[str, object]:
    return MathSolutionService(session).create(current_user.id, **data.model_dump())


@router.get("/attempts/{attempt_id}", response_model=SolutionAttemptRead)
def get_attempt(
    attempt_id: UUID,
    current_user: StudentUser,
    session: Database,
) -> dict[str, object]:
    return MathSolutionService(session).get(current_user.id, attempt_id)


@router.post(
    "/attempts/{attempt_id}/steps",
    response_model=SolutionAttemptRead,
    status_code=status.HTTP_201_CREATED,
)
def add_step(
    attempt_id: UUID,
    data: StepMutationRequest,
    current_user: StudentUser,
    session: Database,
) -> dict[str, object]:
    return MathSolutionService(session).add_step(
        current_user.id,
        attempt_id,
        expected_attempt_revision=data.expected_attempt_revision,
        client_action_id=data.client_action_id,
        draft=data.to_draft(),
    )


@router.patch(
    "/attempts/{attempt_id}/steps/{step_id}",
    response_model=SolutionAttemptRead,
)
def update_step(
    attempt_id: UUID,
    step_id: UUID,
    data: StepMutationRequest,
    current_user: StudentUser,
    session: Database,
) -> dict[str, object]:
    return MathSolutionService(session).update_step(
        current_user.id,
        attempt_id,
        step_id,
        expected_attempt_revision=data.expected_attempt_revision,
        client_action_id=data.client_action_id,
        draft=data.to_draft(),
    )


@router.post(
    "/attempts/{attempt_id}/steps/{step_id}/delete",
    response_model=SolutionAttemptRead,
)
def delete_step(
    attempt_id: UUID,
    step_id: UUID,
    data: AttemptMutationToken,
    current_user: StudentUser,
    session: Database,
) -> dict[str, object]:
    return MathSolutionService(session).delete_step(
        current_user.id, attempt_id, step_id, **data.model_dump()
    )


@router.post(
    "/attempts/{attempt_id}/steps/{step_id}/restore",
    response_model=SolutionAttemptRead,
)
def restore_step(
    attempt_id: UUID,
    step_id: UUID,
    data: AttemptMutationToken,
    current_user: StudentUser,
    session: Database,
) -> dict[str, object]:
    return MathSolutionService(session).restore_step(
        current_user.id, attempt_id, step_id, **data.model_dump()
    )


@router.post(
    "/attempts/{attempt_id}/reorder",
    response_model=SolutionAttemptRead,
)
def reorder_steps(
    attempt_id: UUID,
    data: ReorderStepsRequest,
    current_user: StudentUser,
    session: Database,
) -> dict[str, object]:
    return MathSolutionService(session).reorder_steps(
        current_user.id,
        attempt_id,
        expected_attempt_revision=data.expected_attempt_revision,
        client_action_id=data.client_action_id,
        step_ids=data.step_ids,
    )


@router.get(
    "/attempts/{attempt_id}/steps/{step_id}/revisions",
    response_model=list[StepRevisionRead],
)
def list_step_revisions(
    attempt_id: UUID,
    step_id: UUID,
    current_user: StudentUser,
    session: Database,
) -> list[dict[str, object]]:
    return MathSolutionService(session).list_revisions(
        current_user.id, attempt_id, step_id
    )


@router.post(
    "/attempts/{attempt_id}/steps/{step_id}/rollback",
    response_model=SolutionAttemptRead,
)
def rollback_step(
    attempt_id: UUID,
    step_id: UUID,
    data: RollbackStepRequest,
    current_user: StudentUser,
    session: Database,
) -> dict[str, object]:
    return MathSolutionService(session).rollback_step(
        current_user.id,
        attempt_id,
        step_id,
        expected_attempt_revision=data.expected_attempt_revision,
        client_action_id=data.client_action_id,
        to_revision=data.to_revision,
    )


@router.post(
    "/attempts/{attempt_id}/submit",
    response_model=SolutionAttemptRead,
)
def submit_attempt(
    attempt_id: UUID,
    data: AttemptMutationToken,
    current_user: StudentUser,
    session: Database,
) -> dict[str, object]:
    return MathSolutionService(session).submit(
        current_user.id, attempt_id, **data.model_dump()
    )