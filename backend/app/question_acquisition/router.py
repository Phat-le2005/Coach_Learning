"""FastAPI router for question acquisition planning, sources, and staging (Admin operations only)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.exceptions import ApplicationError
from app.database.session import get_db
from app.question_acquisition.models import (
    QuestionAcquisitionArtifact,
    QuestionAcquisitionExistingCandidate,
    QuestionAcquisitionRequest,
    QuestionAcquisitionRequestStatus,
    QuestionAcquisitionStrategy,
)
from app.question_acquisition.schemas import (
    BlockSourceRequest,
    CancelRequestPayload,
    QuestionAcquisitionArtifactRead,
    QuestionAcquisitionExistingCandidateRead,
    QuestionAcquisitionRequestDetailRead,
    QuestionAcquisitionRequestRead,
    QuestionAcquisitionSourceRead,
    RegisterSourceRequest,
)
from app.question_acquisition.service import QuestionAcquisitionService
from app.users.models import Role, User

router = APIRouter(
    prefix="/question-acquisition",
    tags=["question-acquisition"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)


@router.get("/requests", response_model=list[QuestionAcquisitionRequestRead])
def list_acquisition_requests(
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    status: QuestionAcquisitionRequestStatus | None = Query(default=None),
    strategy: QuestionAcquisitionStrategy | None = Query(default=None),
    subject_id: UUID | None = Query(default=None),
    gap_id: UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[QuestionAcquisitionRequestRead]:
    """List acquisition requests with optional filters."""
    response.headers["Cache-Control"] = "no-store"
    service = QuestionAcquisitionService(session)
    reqs = service.list_requests(
        status=status,
        strategy=strategy,
        subject_id=subject_id,
        gap_id=gap_id,
        offset=offset,
        limit=limit,
    )
    return [QuestionAcquisitionRequestRead.model_validate(r) for r in reqs]


@router.get("/requests/{request_id}", response_model=QuestionAcquisitionRequestDetailRead)
def get_acquisition_request_detail(
    request_id: UUID,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
) -> QuestionAcquisitionRequestDetailRead:
    """Retrieve full details of an acquisition request including candidate links and sources."""
    response.headers["Cache-Control"] = "no-store"
    service = QuestionAcquisitionService(session)
    req = service.get_request(request_id)
    if req is None:
        raise ApplicationError(
            404,
            "QUESTION_ACQUISITION_REQUEST_NOT_FOUND",
            "Acquisition request was not found.",
        )

    # Collect artifacts across sources
    artifacts_map: dict[UUID, QuestionAcquisitionArtifact] = {}
    for src in req.sources:
        for sa in src.source_artifacts:
            if sa.artifact is not None:
                artifacts_map[sa.artifact.id] = sa.artifact

    candidate_reads: list[QuestionAcquisitionExistingCandidateRead] = []
    for cand in req.existing_candidates:
        c_read = QuestionAcquisitionExistingCandidateRead(
            id=cand.id,
            request_id=cand.request_id,
            question_id=cand.question_id,
            difficulty_in_band=cand.difficulty_in_band,
            runtime_eligible=cand.runtime_eligible,
            selection_rank=cand.selection_rank,
            selection_score=cand.selection_score,
            created_at=cand.created_at,
            question_status=cand.question.status if cand.question else None,
            question_type=cand.question.question_type if cand.question else None,
            difficulty=cand.question.difficulty if cand.question else None,
        )
        candidate_reads.append(c_read)

    source_reads = [QuestionAcquisitionSourceRead.model_validate(s) for s in req.sources]
    artifact_reads = [
        QuestionAcquisitionArtifactRead.model_validate(a) for a in artifacts_map.values()
    ]

    base_data = QuestionAcquisitionRequestRead.model_validate(req).model_dump()
    return QuestionAcquisitionRequestDetailRead(
        **base_data,
        existing_candidates=candidate_reads,
        sources=source_reads,
        artifacts=artifact_reads,
    )


@router.post("/requests/{request_id}/cancel", response_model=QuestionAcquisitionRequestRead)
def cancel_acquisition_request(
    request_id: UUID,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    payload: CancelRequestPayload | None = None,
) -> QuestionAcquisitionRequestRead:
    """Cancel an active acquisition request."""
    response.headers["Cache-Control"] = "no-store"
    service = QuestionAcquisitionService(session)
    cancelled = service.cancel_request(
        request_id, reason=payload.reason if payload else None, commit=True
    )
    return QuestionAcquisitionRequestRead.model_validate(cancelled)


@router.post("/requests/{request_id}/sources", response_model=QuestionAcquisitionSourceRead)
def register_acquisition_source(
    request_id: UUID,
    payload: RegisterSourceRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> QuestionAcquisitionSourceRead:
    """Register an external source under an acquisition request."""
    response.headers["Cache-Control"] = "no-store"
    service = QuestionAcquisitionService(session)
    source = service.register_source(
        request_id, payload, registered_by=current_user.id, commit=True
    )
    return QuestionAcquisitionSourceRead.model_validate(source)


@router.post("/sources/{source_id}/fetch", response_model=QuestionAcquisitionArtifactRead)
def fetch_acquisition_source(
    source_id: UUID,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
) -> QuestionAcquisitionArtifactRead:
    """Trigger safe server-side fetch of a registered PDF source."""
    response.headers["Cache-Control"] = "no-store"
    service = QuestionAcquisitionService(session)
    artifact = service.fetch_source(source_id, commit=True)
    return QuestionAcquisitionArtifactRead.model_validate(artifact)


@router.post(
    "/requests/{request_id}/artifacts/upload",
    response_model=QuestionAcquisitionArtifactRead,
)
async def upload_acquisition_artifact(
    request_id: UUID,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(Role.ADMIN))],
    file: UploadFile = File(...),
    provenance_note: str = Form(...),
    title: str | None = Form(default=None),
    publisher: str | None = Form(default=None),
    source_year: int | None = Form(default=None),
) -> QuestionAcquisitionArtifactRead:
    """Upload a local PDF file into the acquisition request."""
    response.headers["Cache-Control"] = "no-store"
    content = await file.read()
    service = QuestionAcquisitionService(session)
    _, artifact = service.upload_artifact(
        request_id,
        file_bytes=content,
        provenance_note=provenance_note,
        title=title,
        publisher=publisher,
        source_year=source_year,
        registered_by=current_user.id,
        commit=True,
    )
    return QuestionAcquisitionArtifactRead.model_validate(artifact)


@router.post("/sources/{source_id}/block", response_model=QuestionAcquisitionSourceRead)
def block_acquisition_source(
    source_id: UUID,
    payload: BlockSourceRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
) -> QuestionAcquisitionSourceRead:
    """Block an acquisition source with a required reason."""
    response.headers["Cache-Control"] = "no-store"
    service = QuestionAcquisitionService(session)
    blocked = service.block_source(source_id, reason=payload.reason, commit=True)
    return QuestionAcquisitionSourceRead.model_validate(blocked)
