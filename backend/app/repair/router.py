from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.database.session import get_db
from app.repair.schemas import (
    RepairAnswerResult,
    RepairAnswerSubmit,
    RepairEvaluationResult,
    RepairSessionCreate,
    RepairSessionRead,
)
from app.repair.service import RepairSessionService
from app.repair.adaptive_service import AdaptiveRepairService
from app.repair.schemas import (
    AdaptiveRepairAnswerResult,
    AdaptiveRepairAnswerSubmit,
    AdaptiveRepairSessionRead,
)
from app.users.models import Role, User

router = APIRouter(prefix="/repair", tags=["Repair Sessions"])


@router.post(
    "/sessions",
    response_model=RepairSessionRead,
    summary="Start a new Repair Session",
    description="Initializes a structured 5-step repair session targeting a weak ProblemType or prerequisite Concept.",
)
def start_repair_session(
    data: RepairSessionCreate,
    current_user: User = Depends(require_role(Role.STUDENT)),
    session: Session = Depends(get_db),
) -> RepairSessionRead:
    service = RepairSessionService(session)
    return service.start_repair_session(current_user, data)


@router.get(
    "/sessions/{session_id}",
    response_model=RepairSessionRead,
    summary="Get Repair Session details and progress",
    description="Retrieve the 5-step pedagogical sequence and current progress for a repair session.",
)
def get_repair_session(
    session_id: UUID,
    current_user: User = Depends(require_role(Role.STUDENT)),
    session: Session = Depends(get_db),
) -> RepairSessionRead:
    service = RepairSessionService(session)
    return service.get_repair_session(current_user, session_id)


@router.post(
    "/sessions/{session_id}/steps/{step_number}/answer",
    response_model=RepairAnswerResult,
    summary="Submit answer for a repair question step",
    description="Submit and evaluate an answer for question steps 2 to 5. Records standard QuestionAttempt and notifies Mastery Engine.",
)
def submit_step_answer(
    session_id: UUID,
    step_number: int,
    data: RepairAnswerSubmit,
    current_user: User = Depends(require_role(Role.STUDENT)),
    session: Session = Depends(get_db),
) -> RepairAnswerResult:
    service = RepairSessionService(session)
    return service.submit_step_answer(current_user, session_id, step_number, data)


@router.post(
    "/sessions/{session_id}/complete",
    response_model=RepairEvaluationResult,
    summary="Evaluate and complete Repair Session",
    description="Evaluates completion deterministically against policy thresholds (average score >= threshold and final recheck correct).",
)
def complete_repair_session(
    session_id: UUID,
    misconception_definition_id: UUID | None = Query(default=None),
    current_user: User = Depends(require_role(Role.STUDENT)),
    session: Session = Depends(get_db),
) -> RepairEvaluationResult:
    service = RepairSessionService(session)
    return service.evaluate_session_completion(
        current_user,
        session_id,
        misconception_definition_id=misconception_definition_id,
    )

# Adaptive verified-root-cause repair endpoints are intentionally separate from
# the legacy five-step API above.

student_router = APIRouter(prefix="/students/me", tags=["Adaptive Repair"])


@student_router.post(
    "/diagnostics/{diagnosis_id}/repair",
    response_model=AdaptiveRepairSessionRead,
    summary="Start adaptive repair from a supported root-cause verification",
)
def start_adaptive_repair(
    diagnosis_id: UUID,
    current_user: User = Depends(require_role(Role.STUDENT)),
    session: Session = Depends(get_db),
) -> AdaptiveRepairSessionRead:
    return AdaptiveRepairService(session).start(current_user, diagnosis_id)


@router.get(
    "/adaptive/{adaptive_session_id}",
    response_model=AdaptiveRepairSessionRead,
    summary="Get frozen adaptive repair state",
)
def get_adaptive_repair(
    adaptive_session_id: UUID,
    current_user: User = Depends(require_role(Role.STUDENT)),
    session: Session = Depends(get_db),
) -> AdaptiveRepairSessionRead:
    return AdaptiveRepairService(session).get(current_user, adaptive_session_id)


@router.post(
    "/adaptive/{adaptive_session_id}/current/answer",
    response_model=AdaptiveRepairAnswerResult,
    summary="Answer the frozen current adaptive repair item",
)
def answer_adaptive_repair_current_item(
    adaptive_session_id: UUID,
    data: AdaptiveRepairAnswerSubmit,
    current_user: User = Depends(require_role(Role.STUDENT)),
    session: Session = Depends(get_db),
) -> AdaptiveRepairAnswerResult:
    return AdaptiveRepairService(session).answer_current(current_user, adaptive_session_id, data)
