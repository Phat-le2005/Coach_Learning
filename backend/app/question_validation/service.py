"""Application service for validation batches, candidates, revisions and reviews."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ApplicationError
from app.question_acquisition.models import (
    QuestionAcquisitionArtifact,
    QuestionAcquisitionExtractionStatus,
    QuestionAcquisitionPage,
    QuestionAcquisitionRequest,
    QuestionAcquisitionRequestStatus,
    QuestionAcquisitionRightsStatus,
    QuestionAcquisitionSource,
    QuestionAcquisitionSourceArtifact,
    QuestionAcquisitionSourceStatus,
    QuestionAcquisitionStrategy,
)
from app.question_validation.models import (
    MANUAL_CHECK_TYPES,
    REQUIRED_CHECK_TYPES,
    QuestionValidationBatch,
    QuestionValidationBatchStatus,
    QuestionValidationCandidate,
    QuestionValidationCandidateConcept,
    QuestionValidationCandidateLearningOutcome,
    QuestionValidationCandidateOption,
    QuestionValidationCandidateProblemType,
    QuestionValidationCandidateSpan,
    QuestionValidationCandidateStatus,
    QuestionValidationCheck,
    QuestionValidationCheckResult,
    QuestionValidationCheckType,
    QuestionValidationRightsDecision,
)
from app.question_validation.policy import ACTIVE_BATCH_STATUSES
from app.question_validation.schemas import (
    CandidateCreate,
    CandidatePatch,
    CandidateRejectInput,
    CandidateSpanInput,
    ManualReviewInput,
)
from app.question_validation.validator import QuestionCandidateValidator
from app.questions.fingerprint import question_content_hash

logger = logging.getLogger(__name__)


CANDIDATE_LOAD_OPTIONS = (
    selectinload(QuestionValidationCandidate.batch).selectinload(
        QuestionValidationBatch.acquisition_request
    ),
    selectinload(QuestionValidationCandidate.spans),
    selectinload(QuestionValidationCandidate.options),
    selectinload(QuestionValidationCandidate.concept_links),
    selectinload(QuestionValidationCandidate.problem_type_links),
    selectinload(QuestionValidationCandidate.learning_outcome_links),
    selectinload(QuestionValidationCandidate.checks),
)


class QuestionValidationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.validator = QuestionCandidateValidator(session)

    def create_or_get_batch(
        self,
        acquisition_request_id: UUID,
        *,
        created_by: UUID | None,
        commit: bool = True,
    ) -> QuestionValidationBatch:
        request = self.session.scalar(
            select(QuestionAcquisitionRequest)
            .where(QuestionAcquisitionRequest.id == acquisition_request_id)
            .with_for_update()
        )
        if request is None:
            raise ApplicationError(
                404,
                "QUESTION_ACQUISITION_REQUEST_NOT_FOUND",
                "Acquisition request was not found.",
            )
        existing = self.session.scalar(
            select(QuestionValidationBatch)
            .where(
                QuestionValidationBatch.acquisition_request_id == request.id,
                QuestionValidationBatch.status.in_(ACTIVE_BATCH_STATUSES),
            )
            .order_by(QuestionValidationBatch.attempt_index.desc())
        )
        if existing is not None:
            return existing
        self._ensure_batch_input(request)
        promoted_count = int(
            self.session.scalar(
                select(func.count(QuestionValidationCandidate.id))
                .join(QuestionValidationCandidate.batch)
                .where(
                    QuestionValidationBatch.acquisition_request_id == request.id,
                    QuestionValidationCandidate.status
                    == QuestionValidationCandidateStatus.PROMOTED,
                )
            )
            or 0
        )
        residual = max(0, request.external_candidate_target_count - promoted_count)
        if residual == 0:
            raise ApplicationError(
                409,
                "QUESTION_VALIDATION_TARGET_ALREADY_SATISFIED",
                "The external candidate target is already satisfied.",
            )
        next_attempt = int(
            self.session.scalar(
                select(func.max(QuestionValidationBatch.attempt_index)).where(
                    QuestionValidationBatch.acquisition_request_id == request.id
                )
            )
            or 0
        ) + 1
        batch = QuestionValidationBatch(
            acquisition_request_id=request.id,
            attempt_index=next_attempt,
            status=QuestionValidationBatchStatus.OPEN,
            target_candidate_count_snapshot=residual,
            created_by=created_by,
        )
        try:
            with self.session.begin_nested():
                self.session.add(batch)
                self.session.flush()
        except IntegrityError:
            winner = self.session.scalar(
                select(QuestionValidationBatch)
                .where(
                    QuestionValidationBatch.acquisition_request_id == request.id,
                    QuestionValidationBatch.status.in_(ACTIVE_BATCH_STATUSES),
                )
                .order_by(QuestionValidationBatch.attempt_index.desc())
            )
            if winner is None:
                raise
            return winner
        if commit:
            self.session.commit()
        logger.info("question validation batch created batch_id=%s request_id=%s", batch.id, request.id)
        return batch

    def _ensure_batch_input(self, request: QuestionAcquisitionRequest) -> None:
        if request.strategy == QuestionAcquisitionStrategy.REVIEW_EXISTING_PIPELINE:
            raise ApplicationError(
                409,
                "QUESTION_VALIDATION_EXTERNAL_STAGING_NOT_REQUIRED",
                "This acquisition strategy uses existing pipeline questions.",
            )
        if request.status != QuestionAcquisitionRequestStatus.READY_FOR_REVIEW:
            raise ApplicationError(
                409,
                "QUESTION_VALIDATION_REQUEST_NOT_READY",
                "The acquisition request is not ready for review.",
            )
        if request.external_candidate_target_count <= 0:
            raise ApplicationError(
                409,
                "QUESTION_VALIDATION_NO_EXTERNAL_TARGET",
                "The acquisition request has no external candidate target.",
            )
        if not self._request_has_usable_evidence(request.id):
            raise ApplicationError(
                409,
                "QUESTION_VALIDATION_NO_USABLE_ARTIFACT",
                "The acquisition request has no usable source artifact.",
            )

    def _request_has_usable_evidence(self, request_id: UUID) -> bool:
        return self.session.scalar(
            select(QuestionAcquisitionSource.id)
            .join(
                QuestionAcquisitionSourceArtifact,
                QuestionAcquisitionSourceArtifact.source_id == QuestionAcquisitionSource.id,
            )
            .join(
                QuestionAcquisitionArtifact,
                QuestionAcquisitionArtifact.id
                == QuestionAcquisitionSourceArtifact.artifact_id,
            )
            .where(
                QuestionAcquisitionSource.request_id == request_id,
                QuestionAcquisitionSource.status != QuestionAcquisitionSourceStatus.BLOCKED,
                QuestionAcquisitionSource.rights_status
                != QuestionAcquisitionRightsStatus.BLOCKED,
                QuestionAcquisitionArtifact.extraction_status.in_(
                    {
                        QuestionAcquisitionExtractionStatus.COMPLETE,
                        QuestionAcquisitionExtractionStatus.PARTIAL,
                    }
                ),
            )
            .limit(1)
        ) is not None

    def list_batches(
        self,
        *,
        status: QuestionValidationBatchStatus | None = None,
        acquisition_request_id: UUID | None = None,
        subject_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[QuestionValidationBatch]:
        stmt = select(QuestionValidationBatch).join(
            QuestionValidationBatch.acquisition_request
        )
        if status is not None:
            stmt = stmt.where(QuestionValidationBatch.status == status)
        if acquisition_request_id is not None:
            stmt = stmt.where(
                QuestionValidationBatch.acquisition_request_id
                == acquisition_request_id
            )
        if subject_id is not None:
            stmt = stmt.where(QuestionAcquisitionRequest.subject_id == subject_id)
        return list(
            self.session.scalars(
                stmt.order_by(QuestionValidationBatch.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )

    def get_batch(self, batch_id: UUID) -> QuestionValidationBatch:
        batch = self.session.scalar(
            select(QuestionValidationBatch)
            .options(
                selectinload(QuestionValidationBatch.acquisition_request),
                selectinload(QuestionValidationBatch.candidates).selectinload(
                    QuestionValidationCandidate.spans
                ),
                selectinload(QuestionValidationBatch.candidates).selectinload(
                    QuestionValidationCandidate.options
                ),
                selectinload(QuestionValidationBatch.candidates).selectinload(
                    QuestionValidationCandidate.concept_links
                ),
                selectinload(QuestionValidationBatch.candidates).selectinload(
                    QuestionValidationCandidate.problem_type_links
                ),
                selectinload(QuestionValidationBatch.candidates).selectinload(
                    QuestionValidationCandidate.learning_outcome_links
                ),
                selectinload(QuestionValidationBatch.candidates).selectinload(
                    QuestionValidationCandidate.checks
                ),
            )
            .where(QuestionValidationBatch.id == batch_id)
        )
        if batch is None:
            raise ApplicationError(404, "QUESTION_VALIDATION_BATCH_NOT_FOUND", "Validation batch was not found.")
        return batch

    def create_candidate(
        self,
        batch_id: UUID,
        payload: CandidateCreate,
        *,
        created_by: UUID | None,
        commit: bool = True,
    ) -> QuestionValidationCandidate:
        if payload.group_structure_required:
            raise ApplicationError(
                409,
                "QUESTION_VALIDATION_GROUP_STRUCTURE_REQUIRED",
                "Grouped questions must use the dedicated QuestionGroup pipeline.",
            )
        if not payload.spans:
            raise ApplicationError(
                422,
                "QUESTION_VALIDATION_SOURCE_SPAN_REQUIRED",
                "At least one immutable source span is required.",
            )
        batch = self.session.scalar(
            select(QuestionValidationBatch)
            .options(selectinload(QuestionValidationBatch.acquisition_request))
            .where(QuestionValidationBatch.id == batch_id)
            .with_for_update()
        )
        if batch is None:
            raise ApplicationError(404, "QUESTION_VALIDATION_BATCH_NOT_FOUND", "Validation batch was not found.")
        if batch.status not in ACTIVE_BATCH_STATUSES:
            raise ApplicationError(409, "QUESTION_VALIDATION_BATCH_NOT_ACTIVE", "Validation batch is not active.")
        source = self.session.get(QuestionAcquisitionSource, payload.source_id)
        if source is None or source.request_id != batch.acquisition_request_id:
            raise ApplicationError(
                409,
                "QUESTION_VALIDATION_PAGE_OUTSIDE_REQUEST",
                "Candidate source is outside this acquisition request.",
            )
        self._validate_collection_uniqueness(payload)
        candidate = QuestionValidationCandidate(
            batch=batch,
            batch_id=batch.id,
            source_id=source.id,
            revision=1,
            status=QuestionValidationCandidateStatus.DRAFT,
            subject_id=batch.acquisition_request.subject_id,
            content=payload.content,
            question_type=payload.question_type,
            difficulty=payload.difficulty,
            correct_answer=payload.correct_answer,
            explanation=payload.explanation,
            cognitive_level=payload.cognitive_level,
            exam_weight=payload.exam_weight,
            source_year=payload.source_year,
            visual_required=payload.visual_required,
            rights_decision=payload.rights_decision,
            content_hash=question_content_hash(payload.content),
            created_by=created_by,
            updated_by=created_by,
        )
        with self.session.no_autoflush:
            self._replace_children(candidate, payload)
        self.session.add(candidate)
        self.session.flush()
        self.refresh_batch_status(batch, commit=False)
        if commit:
            self.session.commit()
        logger.info("question validation candidate created candidate_id=%s batch_id=%s", candidate.id, batch.id)
        return self.get_candidate(candidate.id)

    def get_candidate(
        self, candidate_id: UUID, *, for_update: bool = False
    ) -> QuestionValidationCandidate:
        stmt = (
            select(QuestionValidationCandidate)
            .options(*CANDIDATE_LOAD_OPTIONS)
            .where(QuestionValidationCandidate.id == candidate_id)
        )
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        candidate = self.session.scalar(stmt)
        if candidate is None:
            raise ApplicationError(404, "QUESTION_VALIDATION_CANDIDATE_NOT_FOUND", "Validation candidate was not found.")
        return candidate

    def patch_candidate(
        self,
        candidate_id: UUID,
        payload: CandidatePatch,
        *,
        updated_by: UUID | None,
        commit: bool = True,
    ) -> QuestionValidationCandidate:
        if payload.group_structure_required:
            raise ApplicationError(409, "QUESTION_VALIDATION_GROUP_STRUCTURE_REQUIRED", "Grouped questions must use the dedicated QuestionGroup pipeline.")
        candidate = self.get_candidate(candidate_id, for_update=True)
        self._ensure_editable(candidate)
        if candidate.revision != payload.expected_revision:
            raise ApplicationError(409, "QUESTION_VALIDATION_REVISION_CONFLICT", "Candidate revision is stale.")
        fields = payload.model_fields_set - {"expected_revision", "group_structure_required"}
        if not fields:
            return candidate
        collection_fields = {"spans", "options", "concepts", "problem_types", "learning_outcomes"}
        if "spans" in fields and not payload.spans:
            raise ApplicationError(
                422,
                "QUESTION_VALIDATION_SOURCE_SPAN_REQUIRED",
                "At least one immutable source span is required.",
            )
        scalar_fields = fields - collection_fields
        for field in scalar_fields:
            setattr(candidate, field, getattr(payload, field))
        if "content" in fields:
            candidate.content_hash = question_content_hash(candidate.content)
        self._validate_collection_uniqueness(payload)
        self._replace_selected_children(candidate, payload, fields)
        candidate.revision += 1
        candidate.status = QuestionValidationCandidateStatus.IN_REVIEW
        candidate.updated_by = updated_by
        candidate.updated_at = datetime.now(timezone.utc)
        candidate.rejection_reason = None
        self.session.flush()
        self.refresh_batch_status(candidate.batch, commit=False)
        if commit:
            self.session.commit()
        logger.info("question validation candidate revised candidate_id=%s revision=%s", candidate.id, candidate.revision)
        return self.get_candidate(candidate.id)

    def run_system_validation(
        self,
        candidate_id: UUID,
        *,
        commit: bool = True,
    ) -> QuestionValidationCandidate:
        candidate = self.get_candidate(candidate_id, for_update=True)
        self._ensure_reviewable(candidate)
        for check_type, outcome in self.validator.validate(candidate).items():
            self._upsert_check(
                candidate,
                check_type,
                outcome.result,
                checked_by=None,
                note=outcome.code,
                details=outcome.details,
            )
        if self.validator.source_blocked(candidate):
            self._upsert_check(
                candidate,
                QuestionValidationCheckType.RIGHTS_REVIEW,
                QuestionValidationCheckResult.FAIL,
                checked_by=None,
                note="QUESTION_VALIDATION_SOURCE_BLOCKED",
                details={"errors": ["QUESTION_VALIDATION_SOURCE_BLOCKED"]},
            )
        self.refresh_candidate_status(candidate)
        self.refresh_batch_status(candidate.batch, commit=False)
        if commit:
            self.session.commit()
        return self.get_candidate(candidate.id)

    def record_manual_review(
        self,
        candidate_id: UUID,
        payload: ManualReviewInput,
        *,
        checked_by: UUID,
        commit: bool = True,
    ) -> QuestionValidationCandidate:
        candidate = self.get_candidate(candidate_id, for_update=True)
        self._ensure_reviewable(candidate)
        if payload.check_type not in MANUAL_CHECK_TYPES:
            raise ApplicationError(422, "QUESTION_VALIDATION_MANUAL_CHECK_TYPE_REQUIRED", "Only manual review check types are accepted.")
        if payload.check_type == QuestionValidationCheckType.RIGHTS_REVIEW and payload.result == QuestionValidationCheckResult.PASS:
            if candidate.rights_decision != QuestionValidationRightsDecision.ALLOW_DRAFT:
                raise ApplicationError(409, "QUESTION_VALIDATION_RIGHTS_DECISION_REQUIRED", "ALLOW_DRAFT is required for a passing rights review.")
            if self.validator.source_blocked(candidate):
                payload = payload.model_copy(update={"result": QuestionValidationCheckResult.FAIL})
        self._upsert_check(
            candidate,
            payload.check_type,
            payload.result,
            checked_by=checked_by,
            note=payload.note,
            details={},
        )
        self.refresh_candidate_status(candidate)
        self.refresh_batch_status(candidate.batch, commit=False)
        if commit:
            self.session.commit()
        logger.info("question validation review recorded candidate_id=%s check=%s", candidate.id, payload.check_type.value)
        return self.get_candidate(candidate.id)

    def reject_candidate(
        self,
        candidate_id: UUID,
        payload: CandidateRejectInput,
        *,
        updated_by: UUID,
        commit: bool = True,
    ) -> QuestionValidationCandidate:
        candidate = self.get_candidate(candidate_id, for_update=True)
        self._ensure_editable(candidate)
        candidate.status = QuestionValidationCandidateStatus.REJECTED
        candidate.rejection_reason = payload.reason
        candidate.updated_by = updated_by
        candidate.updated_at = datetime.now(timezone.utc)
        self.refresh_batch_status(candidate.batch, commit=False)
        if commit:
            self.session.commit()
        logger.info("question validation candidate rejected candidate_id=%s", candidate.id)
        return self.get_candidate(candidate.id)

    def refresh_candidate_status(self, candidate: QuestionValidationCandidate) -> None:
        if candidate.status in {
            QuestionValidationCandidateStatus.REJECTED,
            QuestionValidationCandidateStatus.PROMOTED,
        }:
            return
        current = {
            check.check_type: check.result
            for check in candidate.checks
            if check.candidate_revision == candidate.revision
        }
        is_verified = all(
            current.get(check_type) == QuestionValidationCheckResult.PASS
            for check_type in REQUIRED_CHECK_TYPES
        )
        previous = candidate.status
        candidate.status = (
            QuestionValidationCandidateStatus.VERIFIED
            if is_verified
            else QuestionValidationCandidateStatus.IN_REVIEW
        )
        if is_verified and previous != QuestionValidationCandidateStatus.VERIFIED:
            logger.info("question validation candidate verified candidate_id=%s revision=%s", candidate.id, candidate.revision)

    def refresh_batch_status(
        self, batch: QuestionValidationBatch, *, commit: bool = False
    ) -> None:
        # API sessions intentionally disable autoflush. Status derivation must still
        # observe the candidate transition made immediately before this call.
        self.session.flush()
        request_target = batch.acquisition_request.external_candidate_target_count
        promoted_count = int(
            self.session.scalar(
                select(func.count(QuestionValidationCandidate.id))
                .join(QuestionValidationCandidate.batch)
                .where(
                    QuestionValidationBatch.acquisition_request_id
                    == batch.acquisition_request_id,
                    QuestionValidationCandidate.status
                    == QuestionValidationCandidateStatus.PROMOTED,
                )
            )
            or 0
        )
        now = datetime.now(timezone.utc)
        if promoted_count >= request_target:
            batch.status = QuestionValidationBatchStatus.COMPLETED
            batch.completed_at = batch.completed_at or now
        else:
            candidate_statuses = list(
                self.session.scalars(
                    select(QuestionValidationCandidate.status).where(
                        QuestionValidationCandidate.batch_id == batch.id
                    )
                )
            )
            if not candidate_statuses:
                batch.status = QuestionValidationBatchStatus.OPEN
            elif any(
                status == QuestionValidationCandidateStatus.VERIFIED
                for status in candidate_statuses
            ):
                batch.status = QuestionValidationBatchStatus.READY_FOR_PROMOTION
            else:
                batch.status = QuestionValidationBatchStatus.IN_REVIEW
            batch.completed_at = None
        batch.updated_at = now
        self.session.flush()
        if commit:
            self.session.commit()

    def _replace_children(self, candidate: QuestionValidationCandidate, payload: CandidateCreate) -> None:
        candidate.spans = self._build_spans(candidate, payload.source_id, payload.spans)
        candidate.options = [
            QuestionValidationCandidateOption(label=x.label, content=x.content, order_index=x.order_index)
            for x in payload.options
        ]
        candidate.concept_links = [
            QuestionValidationCandidateConcept(concept_id=x.concept_id, weight=x.weight)
            for x in payload.concepts
        ]
        candidate.problem_type_links = [
            QuestionValidationCandidateProblemType(
                problem_type_id=x.problem_type_id, weight=x.weight, is_primary=x.is_primary
            )
            for x in payload.problem_types
        ]
        candidate.learning_outcome_links = [
            QuestionValidationCandidateLearningOutcome(
                learning_outcome_id=x.learning_outcome_id, weight=x.weight
            )
            for x in payload.learning_outcomes
        ]

    def _replace_selected_children(self, candidate: QuestionValidationCandidate, payload: CandidatePatch, fields: set[str]) -> None:
        if "spans" in fields:
            assert payload.spans is not None
            candidate.spans = self._build_spans(candidate, candidate.source_id, payload.spans)
        if "options" in fields:
            candidate.options = [QuestionValidationCandidateOption(label=x.label, content=x.content, order_index=x.order_index) for x in (payload.options or [])]
        if "concepts" in fields:
            candidate.concept_links = [QuestionValidationCandidateConcept(concept_id=x.concept_id, weight=x.weight) for x in (payload.concepts or [])]
        if "problem_types" in fields:
            candidate.problem_type_links = [QuestionValidationCandidateProblemType(problem_type_id=x.problem_type_id, weight=x.weight, is_primary=x.is_primary) for x in (payload.problem_types or [])]
        if "learning_outcomes" in fields:
            candidate.learning_outcome_links = [QuestionValidationCandidateLearningOutcome(learning_outcome_id=x.learning_outcome_id, weight=x.weight) for x in (payload.learning_outcomes or [])]

    def _build_spans(
        self,
        candidate: QuestionValidationCandidate,
        source_id: UUID,
        spans: list[CandidateSpanInput],
    ) -> list[QuestionValidationCandidateSpan]:
        built: list[QuestionValidationCandidateSpan] = []
        request_id = candidate.batch.acquisition_request_id
        for span in spans:
            page = self.session.get(QuestionAcquisitionPage, span.page_id)
            if page is None:
                raise ApplicationError(409, "QUESTION_VALIDATION_PAGE_OUTSIDE_REQUEST", "Source page was not found in this acquisition request.")
            linked_source_ids = set(
                self.session.scalars(
                    select(QuestionAcquisitionSourceArtifact.source_id).where(
                        QuestionAcquisitionSourceArtifact.artifact_id == page.artifact_id
                    )
                )
            )
            request_source_ids = set(
                self.session.scalars(
                    select(QuestionAcquisitionSource.id).where(
                        QuestionAcquisitionSource.id.in_(linked_source_ids),
                        QuestionAcquisitionSource.request_id == request_id,
                    )
                )
            ) if linked_source_ids else set()
            if not request_source_ids:
                raise ApplicationError(409, "QUESTION_VALIDATION_PAGE_OUTSIDE_REQUEST", "Source page is outside this acquisition request.")
            if source_id not in linked_source_ids:
                raise ApplicationError(409, "QUESTION_VALIDATION_PAGE_NOT_LINKED_TO_SOURCE", "Source page is not linked to the candidate source.")
            if span.end_char > len(page.text):
                raise ApplicationError(422, "QUESTION_VALIDATION_SOURCE_SPAN_RANGE_INVALID", "Source span exceeds page text.")
            excerpt = page.text[span.start_char:span.end_char]
            if not excerpt.strip():
                raise ApplicationError(422, "QUESTION_VALIDATION_SOURCE_SPAN_EMPTY", "Source span must contain nonblank text.")
            built.append(
                QuestionValidationCandidateSpan(
                    page_id=page.id,
                    order_index=span.order_index,
                    start_char=span.start_char,
                    end_char=span.end_char,
                    excerpt=excerpt,
                    excerpt_sha256=hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                )
            )
        return built

    def _validate_collection_uniqueness(self, payload: object) -> None:
        for field, key in (("spans", "order_index"), ("options", "label"), ("concepts", "concept_id"), ("problem_types", "problem_type_id"), ("learning_outcomes", "learning_outcome_id")):
            values = getattr(payload, field, None)
            if values is None:
                continue
            keys = [getattr(item, key) for item in values]
            if len(keys) != len(set(keys)):
                raise ApplicationError(422, "QUESTION_VALIDATION_DUPLICATE_COLLECTION_ITEM", f"Duplicate {field} entries are not allowed.")
        options = getattr(payload, "options", None)
        if options is not None:
            orders = [item.order_index for item in options]
            if len(orders) != len(set(orders)):
                raise ApplicationError(422, "QUESTION_VALIDATION_DUPLICATE_COLLECTION_ITEM", "Duplicate option order indexes are not allowed.")
        spans = getattr(payload, "spans", None)
        if spans is not None:
            orders = [item.order_index for item in spans]
            if len(orders) != len(set(orders)):
                raise ApplicationError(422, "QUESTION_VALIDATION_DUPLICATE_COLLECTION_ITEM", "Duplicate span order indexes are not allowed.")

    def _upsert_check(
        self,
        candidate: QuestionValidationCandidate,
        check_type: QuestionValidationCheckType,
        result: QuestionValidationCheckResult,
        *,
        checked_by: UUID | None,
        note: str | None,
        details: dict[str, object],
    ) -> None:
        check = next(
            (
                item
                for item in candidate.checks
                if item.candidate_revision == candidate.revision
                and item.check_type == check_type
            ),
            None,
        )
        if check is None:
            check = QuestionValidationCheck(
                candidate_id=candidate.id,
                candidate_revision=candidate.revision,
                check_type=check_type,
            )
            candidate.checks.append(check)
        check.result = result
        check.checked_by = checked_by
        check.note = note
        check.details_json = details
        check.checked_at = datetime.now(timezone.utc)
        self.session.flush()

    @staticmethod
    def _ensure_editable(candidate: QuestionValidationCandidate) -> None:
        if candidate.status == QuestionValidationCandidateStatus.PROMOTED:
            raise ApplicationError(409, "QUESTION_VALIDATION_CANDIDATE_ALREADY_PROMOTED", "Promoted candidates are immutable.")
        if candidate.status == QuestionValidationCandidateStatus.REJECTED:
            raise ApplicationError(409, "QUESTION_VALIDATION_CANDIDATE_REJECTED", "Rejected candidates are immutable.")

    @classmethod
    def _ensure_reviewable(cls, candidate: QuestionValidationCandidate) -> None:
        cls._ensure_editable(candidate)
