"""FastAPI router for question bank supply gaps (Admin operations only)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.exceptions import ApplicationError
from app.database.session import get_db
from app.question_supply.models import (
    QuestionSupplySeverity,
    QuestionSupplyStatus,
    QuestionSupplyTargetType,
    QuestionSupplyUseCase,
)
from app.question_supply.schemas import (
    ManualAssessmentRequest,
    QuestionBankSufficiencyReport,
    QuestionSupplyGapDetailRead,
    QuestionSupplyGapRead,
)
from app.question_supply.service import (
    QuestionBankSufficiencyService,
    QuestionSupplyGapService,
    QuestionSupplyRequirement,
)
from app.users.models import Role

router = APIRouter(
    prefix="/question-supply",
    tags=["question-supply"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)


@router.get("/gaps", response_model=list[QuestionSupplyGapRead])
def list_supply_gaps(
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    status: QuestionSupplyStatus | None = Query(default=None),
    subject_id: UUID | None = Query(default=None),
    use_case: QuestionSupplyUseCase | None = Query(default=None),
    severity: QuestionSupplySeverity | None = Query(default=None),
    target_type: QuestionSupplyTargetType | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[QuestionSupplyGapRead]:
    """List aggregate question supply gaps with optional filters."""
    response.headers["Cache-Control"] = "no-store"
    service = QuestionSupplyGapService(session)
    gaps = service.list_gaps(
        status=status,
        subject_id=subject_id,
        use_case=use_case,
        severity=severity,
        target_type=target_type,
        offset=offset,
        limit=limit,
    )
    return [QuestionSupplyGapRead.model_validate(g) for g in gaps]


@router.get("/gaps/{gap_id}", response_model=QuestionSupplyGapDetailRead)
def get_supply_gap_detail(
    gap_id: UUID,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
) -> QuestionSupplyGapDetailRead:
    """Retrieve details and observations of a specific supply gap."""
    response.headers["Cache-Control"] = "no-store"
    service = QuestionSupplyGapService(session)
    gap = service.get_gap(gap_id)
    if gap is None:
        raise ApplicationError(404, "QUESTION_SUPPLY_GAP_NOT_FOUND", "Supply gap was not found.")
    return QuestionSupplyGapDetailRead.model_validate(gap)


@router.post("/gaps/{gap_id}/reassess", response_model=QuestionSupplyGapDetailRead)
def reassess_supply_gap(
    gap_id: UUID,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
) -> QuestionSupplyGapDetailRead:
    """Reassess a specific supply gap against current question inventory."""
    response.headers["Cache-Control"] = "no-store"
    service = QuestionSupplyGapService(session)
    service.reassess_gap(gap_id, commit=True)
    reloaded = service.get_gap(gap_id)
    if reloaded is None:
        raise ApplicationError(404, "QUESTION_SUPPLY_GAP_NOT_FOUND", "Supply gap was not found.")
    return QuestionSupplyGapDetailRead.model_validate(reloaded)


@router.post("/gaps/reassess-open", response_model=list[QuestionSupplyGapRead])
def reassess_all_open_gaps(
    response: Response,
    session: Annotated[Session, Depends(get_db)],
) -> list[QuestionSupplyGapRead]:
    """Reassess all open supply gaps against current inventory."""
    response.headers["Cache-Control"] = "no-store"
    service = QuestionSupplyGapService(session)
    reassessed = service.reassess_open_gaps(commit=True)
    return [QuestionSupplyGapRead.model_validate(g) for g in reassessed]


@router.post("/assess", response_model=QuestionBankSufficiencyReport)
def manual_assess_sufficiency(
    payload: ManualAssessmentRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
) -> QuestionBankSufficiencyReport:
    """Read-only assessment of question sufficiency for a given requirement."""
    response.headers["Cache-Control"] = "no-store"
    sufficiency_service = QuestionBankSufficiencyService(session)
    requirement = QuestionSupplyRequirement(
        subject_id=payload.subject_id,
        use_case=payload.use_case,
        target_type=payload.target_type,
        concept_id=payload.concept_id,
        problem_type_id=payload.problem_type_id,
        misconception_definition_id=payload.misconception_definition_id,
        desired_difficulty=payload.desired_difficulty,
        minimum_required_count=payload.minimum_required_count,
        preferred_count=payload.preferred_count,
    )
    return sufficiency_service.assess(requirement, student_id=payload.student_id)
