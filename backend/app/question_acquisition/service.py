"""Service layer for question acquisition planning, source ingestion, and artifact extraction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import tempfile
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.exceptions import ApplicationError
from app.question_acquisition.fetcher import SafePdfFetcher
from app.question_acquisition.models import (
    QuestionAcquisitionArtifact,
    QuestionAcquisitionDiscoveryMethod,
    QuestionAcquisitionExtractionStatus,
    QuestionAcquisitionExistingCandidate,
    QuestionAcquisitionPage,
    QuestionAcquisitionRequest,
    QuestionAcquisitionRequestStatus,
    QuestionAcquisitionRightsStatus,
    QuestionAcquisitionSource,
    QuestionAcquisitionSourceArtifact,
    QuestionAcquisitionSourceKind,
    QuestionAcquisitionSourceStatus,
    QuestionAcquisitionStrategy,
)
from app.question_acquisition.pdf_extraction import ExtractedPdfResult, PdfExtractor
from app.question_acquisition.planner import QuestionAcquisitionPlanner
from app.question_acquisition.policy import QuestionAcquisitionPolicy
from app.question_acquisition.schemas import RegisterSourceRequest
from app.question_acquisition.storage import (
    LocalQuestionAcquisitionStorage,
    QuestionAcquisitionStorage,
)
from app.question_supply.models import (
    QuestionSupplyGap,
    QuestionSupplyStatus,
)
from app.question_supply.service import QuestionSupplyGapService

logger = logging.getLogger(__name__)

ACTIVE_REQUEST_STATUSES = {
    QuestionAcquisitionRequestStatus.PLANNED,
    QuestionAcquisitionRequestStatus.AWAITING_SOURCE,
    QuestionAcquisitionRequestStatus.ACQUIRING,
    QuestionAcquisitionRequestStatus.STAGED,
    QuestionAcquisitionRequestStatus.READY_FOR_REVIEW,
}


@dataclass(frozen=True)
class PreparedSourceFetch:
    source_id: UUID
    request_id: UUID
    normalized_url: str


class QuestionAcquisitionService:
    """Manages acquisition request planning, source registration, fetching, and upload."""

    def __init__(
        self,
        session: Session,
        storage: QuestionAcquisitionStorage | None = None,
        fetcher: SafePdfFetcher | None = None,
    ) -> None:
        self.session = session
        settings = get_settings()
        self.storage = storage or LocalQuestionAcquisitionStorage(
            settings.question_acquisition_storage_dir
        )
        self.fetcher = fetcher or SafePdfFetcher(
            allowed_domains=settings.question_acquisition_allowed_domains,
            max_bytes=settings.question_acquisition_max_bytes,
        )
        self.max_bytes = settings.question_acquisition_max_bytes
        self.gap_service = QuestionSupplyGapService(session)

    def plan_or_get_active_request(
        self,
        gap_id: UUID,
        *,
        created_by: UUID | None = None,
        commit: bool = True,
    ) -> QuestionAcquisitionRequest:
        """Create a new acquisition request plan or return existing active request idempotently."""
        # 1. Reassess gap first (Section 10)
        gap = self.gap_service.reassess_gap(gap_id, commit=False)
        if gap.status == QuestionSupplyStatus.RESOLVED:
            raise ApplicationError(
                409,
                "QUESTION_SUPPLY_GAP_ALREADY_RESOLVED",
                "Supply gap is already resolved by existing question inventory.",
            )

        # 2. Check for active request idempotency (Section 8)
        existing_active = self.session.scalar(
            select(QuestionAcquisitionRequest)
            .where(
                QuestionAcquisitionRequest.gap_id == gap_id,
                QuestionAcquisitionRequest.status.in_(ACTIVE_REQUEST_STATUSES),
            )
            .order_by(QuestionAcquisitionRequest.attempt_index.desc())
        )
        if existing_active is not None:
            return existing_active

        # 3. Calculate next attempt index
        max_attempt = self.session.scalar(
            select(func.coalesce(func.max(QuestionAcquisitionRequest.attempt_index), 0)).where(
                QuestionAcquisitionRequest.gap_id == gap_id
            )
        )
        attempt_index = (max_attempt or 0) + 1

        # 4. Run planner (Section 15)
        planner = QuestionAcquisitionPlanner(self.session)
        plan = planner.plan_for_gap(gap)

        # 5. Determine initial status (Section 17 & 18)
        if plan.strategy == QuestionAcquisitionStrategy.REVIEW_EXISTING_PIPELINE:
            initial_status = QuestionAcquisitionRequestStatus.READY_FOR_REVIEW
        else:
            initial_status = QuestionAcquisitionRequestStatus.AWAITING_SOURCE

        now = datetime.now(timezone.utc)
        req = QuestionAcquisitionRequest(
            gap_id=gap.id,
            attempt_index=attempt_index,
            strategy=plan.strategy,
            status=initial_status,
            subject_id=gap.subject_id,
            use_case=gap.use_case,
            target_type=gap.target_type,
            concept_id=gap.concept_id,
            problem_type_id=gap.problem_type_id,
            misconception_definition_id=gap.misconception_definition_id,
            difficulty_min=gap.difficulty_min,
            difficulty_max=gap.difficulty_max,
            desired_difficulty=gap.desired_difficulty,
            minimum_required_count=gap.minimum_required_count,
            preferred_count=gap.preferred_count,
            shortage_reason_code=gap.reason_code,
            approved_eligible_count_snapshot=gap.approved_eligible_count,
            approved_in_band_count_snapshot=gap.approved_in_band_count,
            pipeline_candidate_count_snapshot=gap.pipeline_candidate_count,
            pipeline_runtime_eligible_count_snapshot=gap.pipeline_runtime_eligible_count,
            required_new_candidate_count=plan.required_new_candidate_count,
            existing_candidate_count=plan.existing_candidate_count,
            external_candidate_target_count=plan.external_candidate_target_count,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )

        try:
            with self.session.begin_nested():
                self.session.add(req)
                self.session.flush()

                # 6. Freeze ranked candidate links (Section 12 & 61)
                for cand_info in plan.ranked_candidates:
                    link = QuestionAcquisitionExistingCandidate(
                        request_id=req.id,
                        question_id=cand_info.question.id,
                        difficulty_in_band=cand_info.difficulty_in_band,
                        runtime_eligible=cand_info.runtime_eligible,
                        selection_rank=cand_info.selection_rank,
                        selection_score=cand_info.selection_score,
                        created_at=now,
                    )
                    self.session.add(link)

                # 7. Update gap status to IN_PROGRESS (Section 11)
                gap.status = QuestionSupplyStatus.IN_PROGRESS
                gap.last_observed_at = now
                self.session.flush()

        except IntegrityError:
            # Concurrent creation race (Section 9)
            winner = self.session.scalar(
                select(QuestionAcquisitionRequest)
                .where(
                    QuestionAcquisitionRequest.gap_id == gap_id,
                    QuestionAcquisitionRequest.status.in_(ACTIVE_REQUEST_STATUSES),
                )
                .order_by(QuestionAcquisitionRequest.attempt_index.desc())
            )
            if winner is not None:
                return winner
            raise

        if commit:
            self.session.commit()
        return req

    def cancel_request(
        self,
        request_id: UUID,
        *,
        reason: str | None = None,
        commit: bool = True,
    ) -> QuestionAcquisitionRequest:
        """Cancel an acquisition request and reopen supply gap if no active request remains."""
        req = self.session.get(QuestionAcquisitionRequest, request_id)
        if req is None:
            raise ApplicationError(
                404,
                "QUESTION_ACQUISITION_REQUEST_NOT_FOUND",
                "Acquisition request was not found.",
            )

        if req.status in {
            QuestionAcquisitionRequestStatus.CANCELLED,
            QuestionAcquisitionRequestStatus.FAILED,
        }:
            return req

        now = datetime.now(timezone.utc)
        req.status = QuestionAcquisitionRequestStatus.CANCELLED
        req.failure_code = "CANCELLED"
        req.updated_at = now
        req.completed_at = now

        # Reopen gap if no other active request exists (Section 56)
        other_active = self.session.scalar(
            select(QuestionAcquisitionRequest).where(
                QuestionAcquisitionRequest.gap_id == req.gap_id,
                QuestionAcquisitionRequest.id != req.id,
                QuestionAcquisitionRequest.status.in_(ACTIVE_REQUEST_STATUSES),
            )
        )
        if other_active is None:
            gap = self.session.get(QuestionSupplyGap, req.gap_id)
            if gap is not None and gap.status == QuestionSupplyStatus.IN_PROGRESS:
                gap.status = QuestionSupplyStatus.OPEN

        self.session.flush()
        if commit:
            self.session.commit()
        return req

    def get_usable_source_artifact(
        self, source_id: UUID
    ) -> QuestionAcquisitionArtifact | None:
        """Find the latest usable (COMPLETE or PARTIAL extraction) artifact linked to this source."""
        stmt = (
            select(QuestionAcquisitionArtifact)
            .join(
                QuestionAcquisitionSourceArtifact,
                QuestionAcquisitionSourceArtifact.artifact_id == QuestionAcquisitionArtifact.id,
            )
            .where(
                QuestionAcquisitionSourceArtifact.source_id == source_id,
                QuestionAcquisitionArtifact.extraction_status.in_(
                    [
                        QuestionAcquisitionExtractionStatus.COMPLETE,
                        QuestionAcquisitionExtractionStatus.PARTIAL,
                    ]
                ),
            )
            .order_by(
                QuestionAcquisitionArtifact.created_at.desc(),
                QuestionAcquisitionArtifact.id.desc(),
            )
            .limit(1)
        )
        return self.session.scalar(stmt)

    def refresh_request_staging_status(
        self, request_id: UUID
    ) -> QuestionAcquisitionRequestStatus | None:
        """Synchronize request staging status based on acquisition strategy and presence of usable sources."""
        req = self.session.get(QuestionAcquisitionRequest, request_id)
        if req is None:
            return None

        if req.status in {
            QuestionAcquisitionRequestStatus.CANCELLED,
            QuestionAcquisitionRequestStatus.FAILED,
        }:
            return req.status

        now = datetime.now(timezone.utc)
        if req.strategy == QuestionAcquisitionStrategy.REVIEW_EXISTING_PIPELINE:
            if req.status != QuestionAcquisitionRequestStatus.READY_FOR_REVIEW:
                req.status = QuestionAcquisitionRequestStatus.READY_FOR_REVIEW
                req.updated_at = now
                self.session.flush()
            return req.status

        # For MIXED and EXTERNAL_SOURCE_REQUIRED, check for active usable non-blocked sources
        usable_sources_count = (
            self.session.scalar(
                select(func.count(func.distinct(QuestionAcquisitionSource.id)))
                .join(QuestionAcquisitionSource.source_artifacts)
                .join(QuestionAcquisitionSourceArtifact.artifact)
                .where(
                    QuestionAcquisitionSource.request_id == req.id,
                    QuestionAcquisitionSource.rights_status
                    != QuestionAcquisitionRightsStatus.BLOCKED,
                    QuestionAcquisitionSource.status
                    == QuestionAcquisitionSourceStatus.FETCHED,
                    QuestionAcquisitionArtifact.extraction_status.in_(
                        [
                            QuestionAcquisitionExtractionStatus.COMPLETE,
                            QuestionAcquisitionExtractionStatus.PARTIAL,
                        ]
                    ),
                )
            )
            or 0
        )

        if usable_sources_count > 0:
            if req.status != QuestionAcquisitionRequestStatus.READY_FOR_REVIEW:
                req.status = QuestionAcquisitionRequestStatus.READY_FOR_REVIEW
                req.updated_at = now
                self.session.flush()
        else:
            if req.status in {
                QuestionAcquisitionRequestStatus.READY_FOR_REVIEW,
                QuestionAcquisitionRequestStatus.STAGED,
                QuestionAcquisitionRequestStatus.ACQUIRING,
            }:
                req.status = QuestionAcquisitionRequestStatus.AWAITING_SOURCE
                req.updated_at = now
                self.session.flush()

        return req.status

    def register_source(
        self,
        request_id: UUID,
        payload: RegisterSourceRequest,
        *,
        registered_by: UUID | None = None,
        commit: bool = True,
    ) -> QuestionAcquisitionSource:
        """Register an external source entry under an acquisition request."""
        req = self.session.get(QuestionAcquisitionRequest, request_id)
        if req is None:
            raise ApplicationError(
                404,
                "QUESTION_ACQUISITION_REQUEST_NOT_FOUND",
                "Acquisition request was not found.",
            )

        if req.status == QuestionAcquisitionRequestStatus.CANCELLED:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_REQUEST_CANCELLED",
                "Cannot register source under a cancelled request.",
            )

        provenance = (payload.provenance_note or "").strip()
        if not provenance:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_PROVENANCE_REQUIRED",
                "Provenance note is required for all acquisition sources.",
            )

        norm_url: str | None = None
        url_hash: str | None = None
        if payload.url:
            norm_url, url_hash = QuestionAcquisitionPolicy.normalize_url(payload.url)
            # Idempotency check: return existing source for same (request_id, url_hash)
            existing_source = self.session.scalar(
                select(QuestionAcquisitionSource).where(
                    QuestionAcquisitionSource.request_id == request_id,
                    QuestionAcquisitionSource.url_hash == url_hash,
                )
            )
            if existing_source is not None:
                return existing_source
        elif payload.source_kind == QuestionAcquisitionSourceKind.PDF_URL:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_URL_REQUIRED",
                "URL is required for PDF_URL source kind.",
            )

        now = datetime.now(timezone.utc)
        source = QuestionAcquisitionSource(
            request_id=request_id,
            source_kind=payload.source_kind,
            discovery_method=payload.discovery_method,
            original_url=payload.url,
            normalized_url=norm_url,
            url_hash=url_hash,
            title=payload.title,
            publisher=payload.publisher,
            source_year=payload.source_year,
            rights_status=QuestionAcquisitionRightsStatus.REVIEW_REQUIRED,
            status=QuestionAcquisitionSourceStatus.REGISTERED,
            provenance_note=provenance,
            registered_by=registered_by,
            created_at=now,
            updated_at=now,
        )

        try:
            with self.session.begin_nested():
                self.session.add(source)
                self.session.flush()
        except IntegrityError:
            if url_hash:
                winner = self.session.scalar(
                    select(QuestionAcquisitionSource).where(
                        QuestionAcquisitionSource.request_id == request_id,
                        QuestionAcquisitionSource.url_hash == url_hash,
                    )
                )
                if winner is not None:
                    return winner
            raise

        if commit:
            self.session.commit()
        return source

    def _ingest_artifact_file(
        self,
        source: QuestionAcquisitionSource,
        file_path: Path,
        sha256: str,
        file_size_bytes: int,
        *,
        mime_type: str = "application/pdf",
    ) -> QuestionAcquisitionArtifact:
        """Internal helper to ingest a file into storage, extract pages, link to source, and update status."""
        now = datetime.now(timezone.utc)
        artifact = self.session.scalar(
            select(QuestionAcquisitionArtifact).where(
                QuestionAcquisitionArtifact.sha256 == sha256
            )
        )

        extraction: ExtractedPdfResult | None = None
        if artifact is None:
            storage_key = self.storage.compute_storage_key(sha256)
            self.storage.save_file(storage_key, file_path)

            extraction = PdfExtractor.extract_from_file(file_path)

            try:
                with self.session.begin_nested():
                    artifact = QuestionAcquisitionArtifact(
                        sha256=sha256,
                        mime_type=mime_type,
                        file_size_bytes=file_size_bytes,
                        page_count=(
                            extraction.page_count
                            if extraction.page_count and extraction.page_count > 0
                            else None
                        ),
                        storage_key=storage_key,
                        extraction_status=extraction.extraction_status,
                        created_at=now,
                    )
                    self.session.add(artifact)
                    self.session.flush()

                    for p in extraction.pages:
                        page = QuestionAcquisitionPage(
                            artifact_id=artifact.id,
                            page_number=p.page_number,
                            text=p.text,
                            text_sha256=p.text_sha256,
                            char_count=p.char_count,
                            created_at=now,
                        )
                        self.session.add(page)
                    self.session.flush()
            except IntegrityError:
                # Concurrent race: another worker ingested exact same sha256 artifact
                artifact = self.session.scalar(
                    select(QuestionAcquisitionArtifact).where(
                        QuestionAcquisitionArtifact.sha256 == sha256
                    )
                )
                if artifact is None:
                    raise

        # Concurrency-safe link between source and artifact
        try:
            with self.session.begin_nested():
                link = QuestionAcquisitionSourceArtifact(
                    source_id=source.id,
                    artifact_id=artifact.id,
                    created_at=now,
                )
                self.session.add(link)
                self.session.flush()
        except IntegrityError:
            pass

        # Query aggregate usable artifact state over all linked artifacts for this source
        usable_artifact = self.get_usable_source_artifact(source.id)

        # Update source status and failure markers based on aggregate precedence:
        # 1. BLOCKED is authoritative operational override: preserve BLOCKED status and original reason.
        # 2. Otherwise, ANY usable linked artifact (COMPLETE or PARTIAL) means source is FETCHED.
        # 3. Otherwise, if no usable artifact exists, source is FAILED with extraction error.
        if (
            source.rights_status == QuestionAcquisitionRightsStatus.BLOCKED
            or source.status == QuestionAcquisitionSourceStatus.BLOCKED
        ):
            source.status = QuestionAcquisitionSourceStatus.BLOCKED
        elif usable_artifact is not None:
            source.status = QuestionAcquisitionSourceStatus.FETCHED
            source.failure_code = None
            source.failure_detail = None
            source.fetched_at = source.fetched_at or now
        else:
            source.status = QuestionAcquisitionSourceStatus.FAILED
            source.failure_code = "QUESTION_ACQUISITION_PDF_EXTRACTION_FAILED"
            if extraction is not None and extraction.error_message:
                source.failure_detail = extraction.error_message[:1000]
            else:
                source.failure_detail = "PDF contains no extractable text or is invalid."

        source.updated_at = now
        self.session.flush()

        self.refresh_request_staging_status(source.request_id)
        self.session.flush()
        return artifact

    def _prepare_source_fetch(
        self, source_id: UUID
    ) -> tuple[QuestionAcquisitionArtifact | None, PreparedSourceFetch | None]:
        """Phase A: Validate source and commit FETCHING state in a short transaction before network I/O."""
        source = self.session.get(QuestionAcquisitionSource, source_id)
        if source is None:
            raise ApplicationError(
                404,
                "QUESTION_ACQUISITION_SOURCE_NOT_FOUND",
                "Acquisition source was not found.",
            )

        if source.rights_status == QuestionAcquisitionRightsStatus.BLOCKED:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_SOURCE_BLOCKED",
                "Cannot fetch a blocked acquisition source.",
            )

        if (
            source.source_kind != QuestionAcquisitionSourceKind.PDF_URL
            or not source.normalized_url
        ):
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_CANNOT_FETCH",
                "Source is not a fetchable PDF URL.",
            )

        # Idempotency: only short-circuit if source was already successfully FETCHED and has a usable artifact
        if source.status == QuestionAcquisitionSourceStatus.FETCHED:
            usable_artifact = self.get_usable_source_artifact(source.id)
            if usable_artifact is not None:
                return usable_artifact, None

        # Clear previous failure markers if retrying previously failed source
        now = datetime.now(timezone.utc)
        source.status = QuestionAcquisitionSourceStatus.FETCHING
        source.failure_code = None
        source.failure_detail = None
        source.updated_at = now

        prepared = PreparedSourceFetch(
            source_id=source.id,
            request_id=source.request_id,
            normalized_url=source.normalized_url,
        )

        self.session.flush()
        self.session.commit()
        return None, prepared

    def _load_source_for_finalization(
        self, source_id: UUID
    ) -> QuestionAcquisitionSource | None:
        """Load acquisition source with row lock and fresh DB attributes, bypassing stale identity-map caching."""
        stmt = (
            select(QuestionAcquisitionSource)
            .where(QuestionAcquisitionSource.id == source_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return self.session.scalar(stmt)

    def _finalize_fetch_failure(
        self,
        source_id: UUID,
        *,
        failure_code: str,
        failure_detail: str | None = None,
        commit: bool = True,
    ) -> None:
        """Phase C (Failure): Finalize failed fetch in a short transaction, protecting any concurrent usable state.

        Concurrency state precedence:
        1. BLOCKED is authoritative operational override: preserve BLOCKED status and original reason.
        2. Otherwise, a usable artifact means FETCHED: late failure does not overwrite successful acquisition.
        3. Otherwise, failed attempt means FAILED: persist failure code and detail.
        """
        source = self._load_source_for_finalization(source_id)
        if source is None:
            return

        # Precedence 1: BLOCKED is authoritative operational override
        if (
            source.rights_status == QuestionAcquisitionRightsStatus.BLOCKED
            or source.status == QuestionAcquisitionSourceStatus.BLOCKED
        ):
            source.status = QuestionAcquisitionSourceStatus.BLOCKED
            # Preserve existing manual block failure_code and failure_detail
            self.refresh_request_staging_status(source.request_id)
            self.session.flush()
            if commit:
                self.session.commit()
            return

        # Precedence 2: Usable artifact means FETCHED
        usable_artifact = self.get_usable_source_artifact(source.id)
        if usable_artifact is not None:
            source.status = QuestionAcquisitionSourceStatus.FETCHED
            source.failure_code = None
            source.failure_detail = None
            self.refresh_request_staging_status(source.request_id)
            self.session.flush()
            if commit:
                self.session.commit()
            return

        # Precedence 3: Failed attempt means FAILED
        now_err = datetime.now(timezone.utc)
        source.status = QuestionAcquisitionSourceStatus.FAILED
        source.failure_code = failure_code
        source.failure_detail = (failure_detail or "")[:1000]
        source.updated_at = now_err
        self.refresh_request_staging_status(source.request_id)
        self.session.flush()
        if commit:
            self.session.commit()

    def _finalize_fetch_success(
        self,
        prepared: PreparedSourceFetch,
        fetch_result: Any,
        *,
        commit: bool = True,
    ) -> QuestionAcquisitionArtifact:
        """Phase C (Success): Ingest and link artifact in a short transaction after network I/O.

        Concurrency state precedence:
        1. BLOCKED is authoritative operational override: preserve BLOCKED status, original failure_code and reason.
        2. Otherwise, successful ingest and extraction promotes source to FETCHED.
        """
        source = self._load_source_for_finalization(prepared.source_id)
        if source is None:
            raise ApplicationError(
                404,
                "QUESTION_ACQUISITION_SOURCE_NOT_FOUND",
                "Acquisition source was not found.",
            )

        artifact = self._ingest_artifact_file(
            source=source,
            file_path=fetch_result.temp_file_path,
            sha256=fetch_result.sha256,
            file_size_bytes=fetch_result.file_size_bytes,
            mime_type=fetch_result.mime_type,
        )
        if commit:
            self.session.commit()
        return artifact

    def fetch_source(
        self,
        source_id: UUID,
        *,
        commit: bool = True,
    ) -> QuestionAcquisitionArtifact:
        """Safely fetch and ingest external PDF artifact with strict three-phase transaction boundaries.

        Note: fetch_source orchestrates multiple transactions (Phase A prepare commit, Phase B network
        outside transaction, and Phase C finalize commit). commit=False is deprecated because Phase A
        must always commit before network I/O.
        """
        # PHASE A: PREPARE (short DB transaction committed before network I/O)
        usable_artifact, prepared = self._prepare_source_fetch(source_id)
        if usable_artifact is not None:
            return usable_artifact
        assert prepared is not None

        # PHASE B: NETWORK (assert no DB transaction is active)
        if self.session.in_transaction():
            raise RuntimeError(
                "Database transaction must not be active during network fetch."
            )

        fetch_result = None
        try:
            try:
                fetch_result = self.fetcher.fetch_pdf(prepared.normalized_url)
            except ApplicationError as exc:
                self._finalize_fetch_failure(
                    prepared.source_id,
                    failure_code=exc.code,
                    failure_detail=exc.message,
                    commit=commit,
                )
                raise
            except Exception as exc:
                self._finalize_fetch_failure(
                    prepared.source_id,
                    failure_code="QUESTION_ACQUISITION_FETCH_FAILED",
                    failure_detail=str(exc),
                    commit=commit,
                )
                raise

            # PHASE C: FINALIZE SUCCESS (short DB transaction)
            artifact = self._finalize_fetch_success(
                prepared=prepared,
                fetch_result=fetch_result,
                commit=commit,
            )
            return artifact
        finally:
            if fetch_result is not None:
                fetch_result.temp_file_path.unlink(missing_ok=True)

    def upload_artifact_from_file(
        self,
        request_id: UUID,
        *,
        file_path: Path,
        sha256: str,
        file_size_bytes: int,
        provenance_note: str,
        title: str | None = None,
        publisher: str | None = None,
        source_year: int | None = None,
        registered_by: UUID | None = None,
        commit: bool = True,
    ) -> tuple[QuestionAcquisitionSource, QuestionAcquisitionArtifact]:
        """Ingest manually uploaded PDF document from a stream-buffered file into the acquisition request."""
        req = self.session.get(QuestionAcquisitionRequest, request_id)
        if req is None:
            raise ApplicationError(
                404,
                "QUESTION_ACQUISITION_REQUEST_NOT_FOUND",
                "Acquisition request was not found.",
            )

        if req.status == QuestionAcquisitionRequestStatus.CANCELLED:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_REQUEST_CANCELLED",
                "Cannot upload artifact to a cancelled request.",
            )

        provenance = (provenance_note or "").strip()
        if not provenance:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_PROVENANCE_REQUIRED",
                "Provenance note is mandatory for manual PDF uploads.",
            )

        if file_size_bytes > self.max_bytes:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_FILE_TOO_LARGE",
                f"Uploaded file exceeds maximum limit ({self.max_bytes} bytes).",
            )

        now = datetime.now(timezone.utc)
        source = QuestionAcquisitionSource(
            request_id=req.id,
            source_kind=QuestionAcquisitionSourceKind.MANUAL_PDF_UPLOAD,
            discovery_method=QuestionAcquisitionDiscoveryMethod.ADMIN_UPLOAD,
            title=title,
            publisher=publisher,
            source_year=source_year,
            rights_status=QuestionAcquisitionRightsStatus.REVIEW_REQUIRED,
            status=QuestionAcquisitionSourceStatus.REGISTERED,
            provenance_note=provenance,
            registered_by=registered_by,
            created_at=now,
            updated_at=now,
        )
        self.session.add(source)
        self.session.flush()

        artifact = self._ingest_artifact_file(
            source=source,
            file_path=file_path,
            sha256=sha256,
            file_size_bytes=file_size_bytes,
        )

        if commit:
            self.session.commit()
        return source, artifact

    def upload_artifact(
        self,
        request_id: UUID,
        *,
        file_bytes: bytes,
        provenance_note: str,
        title: str | None = None,
        publisher: str | None = None,
        source_year: int | None = None,
        registered_by: UUID | None = None,
        commit: bool = True,
    ) -> tuple[QuestionAcquisitionSource, QuestionAcquisitionArtifact]:
        """Ingest manual upload from raw bytes (delegates to stream-safe file ingestion)."""
        if len(file_bytes) > self.max_bytes:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_FILE_TOO_LARGE",
                f"Uploaded file exceeds maximum limit ({self.max_bytes} bytes).",
            )

        if not file_bytes.startswith(b"%PDF-"):
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_NOT_PDF",
                "Uploaded file is not a valid PDF document.",
            )

        sha256 = hashlib.sha256(file_bytes).hexdigest()
        with tempfile.NamedTemporaryFile(prefix="acq_up_", suffix=".tmp", delete=False) as tf:
            tf.write(file_bytes)
            temp_path = Path(tf.name)

        try:
            return self.upload_artifact_from_file(
                request_id,
                file_path=temp_path,
                sha256=sha256,
                file_size_bytes=len(file_bytes),
                provenance_note=provenance_note,
                title=title,
                publisher=publisher,
                source_year=source_year,
                registered_by=registered_by,
                commit=commit,
            )
        finally:
            temp_path.unlink(missing_ok=True)

    def block_source(
        self,
        source_id: UUID,
        *,
        reason: str,
        commit: bool = True,
    ) -> QuestionAcquisitionSource:
        """Mark a source as blocked with a recorded reason and demote request if no usable sources remain."""
        source = self.session.get(QuestionAcquisitionSource, source_id)
        if source is None:
            raise ApplicationError(
                404,
                "QUESTION_ACQUISITION_SOURCE_NOT_FOUND",
                "Acquisition source was not found.",
            )

        now = datetime.now(timezone.utc)
        source.rights_status = QuestionAcquisitionRightsStatus.BLOCKED
        source.status = QuestionAcquisitionSourceStatus.BLOCKED
        source.failure_code = "MANUALLY_BLOCKED"
        source.failure_detail = reason
        source.updated_at = now

        self.refresh_request_staging_status(source.request_id)

        self.session.flush()
        if commit:
            self.session.commit()
        return source

    def get_request(self, request_id: UUID) -> QuestionAcquisitionRequest | None:
        """Retrieve full details of an acquisition request."""
        return self.session.scalar(
            select(QuestionAcquisitionRequest)
            .options(
                selectinload(QuestionAcquisitionRequest.existing_candidates).selectinload(
                    QuestionAcquisitionExistingCandidate.question
                ),
                selectinload(QuestionAcquisitionRequest.sources).selectinload(
                    QuestionAcquisitionSource.source_artifacts
                ).selectinload(QuestionAcquisitionSourceArtifact.artifact),
            )
            .where(QuestionAcquisitionRequest.id == request_id)
        )

    def list_requests(
        self,
        *,
        status: QuestionAcquisitionRequestStatus | None = None,
        strategy: QuestionAcquisitionStrategy | None = None,
        subject_id: UUID | None = None,
        gap_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[QuestionAcquisitionRequest]:
        """List acquisition requests with optional filters."""
        stmt = select(QuestionAcquisitionRequest)
        if status is not None:
            stmt = stmt.where(QuestionAcquisitionRequest.status == status)
        if strategy is not None:
            stmt = stmt.where(QuestionAcquisitionRequest.strategy == strategy)
        if subject_id is not None:
            stmt = stmt.where(QuestionAcquisitionRequest.subject_id == subject_id)
        if gap_id is not None:
            stmt = stmt.where(QuestionAcquisitionRequest.gap_id == gap_id)

        stmt = (
            stmt.order_by(QuestionAcquisitionRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(stmt))
