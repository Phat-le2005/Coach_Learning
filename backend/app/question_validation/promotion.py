"""Atomic, explicit promotion from a verified candidate to one DRAFT Question."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.question_acquisition.models import (
    QuestionAcquisitionRightsStatus,
    QuestionAcquisitionSource,
    QuestionAcquisitionSourceStatus,
)
from app.question_supply.service import QuestionSupplyGapService
from app.question_validation.models import (
    REQUIRED_CHECK_TYPES,
    QuestionValidationCandidate,
    QuestionValidationCandidateStatus,
    QuestionValidationCheckResult,
    QuestionValidationCheckType,
)
from app.question_validation.policy import QUESTION_CREATION_ADVISORY_LOCK_KEY
from app.question_validation.service import QuestionValidationService
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
)

logger = logging.getLogger(__name__)


class QuestionValidationPromotionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.validation = QuestionValidationService(session)

    def promote(
        self,
        candidate_id: UUID,
        *,
        promoted_by: UUID,
        commit: bool = True,
    ) -> tuple[QuestionValidationCandidate, Question]:
        self._lock_question_creation()
        candidate = self.validation.get_candidate(candidate_id, for_update=True)
        if candidate.status == QuestionValidationCandidateStatus.PROMOTED:
            question = self.session.get(Question, candidate.promoted_question_id)
            if question is None:
                raise ApplicationError(409, "QUESTION_VALIDATION_PROMOTION_LINK_BROKEN", "Promoted question link is unavailable.")
            return candidate, question
        if candidate.status == QuestionValidationCandidateStatus.REJECTED:
            raise ApplicationError(409, "QUESTION_VALIDATION_CANDIDATE_REJECTED", "Rejected candidates cannot be promoted.")

        source = self.session.get(
            QuestionAcquisitionSource,
            candidate.source_id,
            populate_existing=True,
        )
        if source is None or source.status == QuestionAcquisitionSourceStatus.BLOCKED or source.rights_status == QuestionAcquisitionRightsStatus.BLOCKED:
            self._fail_current_check(
                candidate,
                QuestionValidationCheckType.RIGHTS_REVIEW,
                "QUESTION_VALIDATION_SOURCE_BLOCKED",
            )
            candidate.status = QuestionValidationCandidateStatus.IN_REVIEW
            self._finish_failed_promotion(candidate, commit)
            raise ApplicationError(409, "QUESTION_VALIDATION_SOURCE_BLOCKED", "The source is blocked.")

        outcomes = self.validation.validator.validate(candidate)
        for check_type, outcome in outcomes.items():
            self.validation._upsert_check(
                candidate,
                check_type,
                outcome.result,
                checked_by=None,
                note=outcome.code,
                details=outcome.details,
            )
        self.validation.refresh_candidate_status(candidate)

        failed_system = {
            check_type: outcome
            for check_type, outcome in outcomes.items()
            if outcome.result != QuestionValidationCheckResult.PASS
        }
        if failed_system:
            candidate.status = QuestionValidationCandidateStatus.IN_REVIEW
            self._finish_failed_promotion(candidate, commit)
            codes = {outcome.code for outcome in failed_system.values()}
            if "QUESTION_VALIDATION_DUPLICATE" in codes:
                code = "QUESTION_VALIDATION_DUPLICATE"
            elif any(
                check_type == QuestionValidationCheckType.TAXONOMY_INTEGRITY
                for check_type in failed_system
            ):
                taxonomy_errors = failed_system[
                    QuestionValidationCheckType.TAXONOMY_INTEGRITY
                ].details.get("errors", [])
                code = (
                    "QUESTION_VALIDATION_TARGET_MISMATCH"
                    if taxonomy_errors == ["QUESTION_VALIDATION_TARGET_MISMATCH"]
                    else "QUESTION_VALIDATION_TAXONOMY_STALE"
                )
            else:
                code = next(iter(codes))
            raise ApplicationError(409, code, "Candidate failed fresh promotion validation.")

        current_checks = {
            check.check_type: check.result
            for check in candidate.checks
            if check.candidate_revision == candidate.revision
        }
        if candidate.status != QuestionValidationCandidateStatus.VERIFIED or not all(
            current_checks.get(check_type) == QuestionValidationCheckResult.PASS
            for check_type in REQUIRED_CHECK_TYPES
        ):
            self._finish_failed_promotion(candidate, commit)
            raise ApplicationError(409, "QUESTION_VALIDATION_NOT_VERIFIED", "All current validation and review gates must pass before promotion.")
        if candidate.difficulty is None or candidate.exam_weight is None:
            raise ApplicationError(409, "QUESTION_VALIDATION_REQUIRED_FIELDS_MISSING", "Reviewed difficulty and exam weight are required.")

        question = Question(
            subject_id=candidate.subject_id,
            content=candidate.content,
            content_hash=candidate.content_hash,
            question_type=candidate.question_type,
            difficulty=candidate.difficulty,
            correct_answer=candidate.correct_answer,
            explanation=candidate.explanation,
            source_type="ACQUISITION",
            source_reference=f"acquisition:candidate:{candidate.id}",
            source_year=candidate.source_year,
            cognitive_level=candidate.cognitive_level,
            exam_weight=candidate.exam_weight,
            status=QuestionStatus.DRAFT,
            created_by=promoted_by,
        )
        question.options = [
            QuestionOption(label=item.label, content=item.content, order_index=item.order_index)
            for item in candidate.options
        ]
        question.concept_links = [
            QuestionConcept(concept_id=item.concept_id, weight=item.weight)
            for item in candidate.concept_links
        ]
        question.problem_type_links = [
            QuestionProblemType(
                problem_type_id=item.problem_type_id,
                weight=item.weight,
                is_primary=item.is_primary,
            )
            for item in candidate.problem_type_links
        ]
        question.learning_outcome_links = [
            QuestionLearningOutcome(
                learning_outcome_id=item.learning_outcome_id,
                weight=item.weight,
            )
            for item in candidate.learning_outcome_links
        ]
        self.session.add(question)
        try:
            self.session.flush()
            now = datetime.now(timezone.utc)
            candidate.promoted_question_id = question.id
            candidate.promoted_revision = candidate.revision
            candidate.promoted_by = promoted_by
            candidate.promoted_at = now
            candidate.status = QuestionValidationCandidateStatus.PROMOTED
            candidate.updated_by = promoted_by
            candidate.updated_at = now
            self.session.flush()
            self.validation.refresh_batch_status(candidate.batch, commit=False)
            QuestionSupplyGapService(self.session).reassess_gap(
                candidate.batch.acquisition_request.gap_id,
                commit=False,
            )
            if commit:
                self.session.commit()
        except IntegrityError:
            self.session.rollback()
            winner = self.validation.get_candidate(candidate_id)
            if winner.status == QuestionValidationCandidateStatus.PROMOTED:
                existing = self.session.get(Question, winner.promoted_question_id)
                if existing is not None:
                    return winner, existing
            raise ApplicationError(409, "QUESTION_VALIDATION_PROMOTION_CONFLICT", "Concurrent promotion could not be completed.")
        logger.info("question validation candidate promoted candidate_id=%s question_id=%s", candidate.id, question.id)
        return self.validation.get_candidate(candidate.id), question

    def _lock_question_creation(self) -> None:
        if self.session.get_bind().dialect.name == "postgresql":
            self.session.execute(
                select(
                    func.pg_advisory_xact_lock(
                        func.hashtext(QUESTION_CREATION_ADVISORY_LOCK_KEY)
                    )
                )
            )

    def _fail_current_check(
        self,
        candidate: QuestionValidationCandidate,
        check_type: QuestionValidationCheckType,
        code: str,
    ) -> None:
        self.validation._upsert_check(
            candidate,
            check_type,
            QuestionValidationCheckResult.FAIL,
            checked_by=None,
            note=code,
            details={"errors": [code]},
        )

    def _finish_failed_promotion(
        self, candidate: QuestionValidationCandidate, commit: bool
    ) -> None:
        self.validation.refresh_batch_status(candidate.batch, commit=False)
        if commit:
            self.session.commit()
