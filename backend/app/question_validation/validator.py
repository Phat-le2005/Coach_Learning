"""Deterministic system validation for acquisition-backed candidates."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, Topic
from app.misconceptions.models import MisconceptionDefinition
from app.question_acquisition.models import (
    QuestionAcquisitionExtractionStatus,
    QuestionAcquisitionArtifact,
    QuestionAcquisitionPage,
    QuestionAcquisitionRightsStatus,
    QuestionAcquisitionSource,
    QuestionAcquisitionSourceArtifact,
    QuestionAcquisitionSourceStatus,
)
from app.question_supply.models import QuestionSupplyTargetType
from app.question_validation.models import (
    QuestionValidationCandidate,
    QuestionValidationCandidateStatus,
    QuestionValidationCheckResult,
    QuestionValidationCheckType,
)
from app.question_validation.policy import CANONICAL_TRUE_FALSE_ANSWERS
from app.questions.duplicate_detection import ExactContentHashDuplicateDetector
from app.questions.models import QuestionType
from app.questions.fingerprint import question_content_hash


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    result: QuestionValidationCheckResult
    code: str
    details: dict[str, object]


def _outcome(
    errors: list[str], *, pass_code: str
) -> CheckOutcome:
    return CheckOutcome(
        result=(
            QuestionValidationCheckResult.FAIL
            if errors
            else QuestionValidationCheckResult.PASS
        ),
        code=errors[0] if errors else pass_code,
        details={"errors": errors},
    )


class QuestionCandidateValidator:
    """Checks only deterministic invariants; it never supplies human review."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.duplicate_detector = ExactContentHashDuplicateDetector()

    def validate(
        self, candidate: QuestionValidationCandidate
    ) -> dict[QuestionValidationCheckType, CheckOutcome]:
        return {
            QuestionValidationCheckType.STRUCTURE: self.check_structure(candidate),
            QuestionValidationCheckType.ANSWER_INTEGRITY: self.check_answer(candidate),
            QuestionValidationCheckType.TAXONOMY_INTEGRITY: self.check_taxonomy(candidate),
            QuestionValidationCheckType.DUPLICATE: self.check_duplicate(candidate),
            QuestionValidationCheckType.VISUAL_INTEGRITY: self.check_visual(candidate),
        }

    def source_is_usable(self, candidate: QuestionValidationCandidate) -> bool:
        source = self.session.get(QuestionAcquisitionSource, candidate.source_id)
        if source is None or source.request_id != candidate.batch.acquisition_request_id:
            return False
        if source.status == QuestionAcquisitionSourceStatus.BLOCKED:
            return False
        if source.rights_status == QuestionAcquisitionRightsStatus.BLOCKED:
            return False
        usable_count = self.session.scalar(
            select(func.count(QuestionAcquisitionSourceArtifact.id))
            .join(
                QuestionAcquisitionArtifact,
                QuestionAcquisitionSourceArtifact.artifact_id
                == QuestionAcquisitionArtifact.id,
            )
            .where(
                QuestionAcquisitionSourceArtifact.source_id == source.id,
                QuestionAcquisitionArtifact.extraction_status.in_(
                    {
                        QuestionAcquisitionExtractionStatus.COMPLETE,
                        QuestionAcquisitionExtractionStatus.PARTIAL,
                    }
                ),
            )
        )
        return bool(usable_count)

    def source_blocked(self, candidate: QuestionValidationCandidate) -> bool:
        source = self.session.get(
            QuestionAcquisitionSource,
            candidate.source_id,
            populate_existing=True,
        )
        return source is None or source.status == QuestionAcquisitionSourceStatus.BLOCKED or (
            source.rights_status == QuestionAcquisitionRightsStatus.BLOCKED
        )

    def check_structure(self, candidate: QuestionValidationCandidate) -> CheckOutcome:
        errors: list[str] = []
        if not candidate.content.strip():
            errors.append("QUESTION_VALIDATION_CONTENT_REQUIRED")
        if candidate.difficulty is None or not 0.0 <= candidate.difficulty <= 1.0:
            errors.append("QUESTION_VALIDATION_DIFFICULTY_REQUIRED")
        if candidate.exam_weight is None or not 0.0 <= candidate.exam_weight <= 1.0:
            errors.append("QUESTION_VALIDATION_EXAM_WEIGHT_REQUIRED")
        if not candidate.spans:
            errors.append("QUESTION_VALIDATION_SOURCE_SPAN_REQUIRED")
        if candidate.content_hash != question_content_hash(candidate.content):
            errors.append("QUESTION_VALIDATION_CONTENT_HASH_MISMATCH")
        if not self.source_is_usable(candidate):
            errors.append(
                "QUESTION_VALIDATION_SOURCE_BLOCKED"
                if self.source_blocked(candidate)
                else "QUESTION_VALIDATION_NO_USABLE_ARTIFACT"
            )
        errors.extend(self.provenance_errors(candidate))
        return _outcome(errors, pass_code="QUESTION_VALIDATION_STRUCTURE_VALID")

    def provenance_errors(
        self, candidate: QuestionValidationCandidate
    ) -> list[str]:
        errors: list[str] = []
        source = self.session.get(
            QuestionAcquisitionSource,
            candidate.source_id,
            populate_existing=True,
        )
        if source is None or source.request_id != candidate.batch.acquisition_request_id:
            return ["QUESTION_VALIDATION_PAGE_OUTSIDE_REQUEST"]
        usable_statuses = {
            QuestionAcquisitionExtractionStatus.COMPLETE,
            QuestionAcquisitionExtractionStatus.PARTIAL,
        }
        for span in candidate.spans:
            page = self.session.get(
                QuestionAcquisitionPage, span.page_id, populate_existing=True
            )
            if page is None:
                errors.append("QUESTION_VALIDATION_PAGE_OUTSIDE_REQUEST")
                continue
            link = self.session.scalar(
                select(QuestionAcquisitionSourceArtifact).where(
                    QuestionAcquisitionSourceArtifact.source_id == candidate.source_id,
                    QuestionAcquisitionSourceArtifact.artifact_id == page.artifact_id,
                )
            )
            if link is None:
                errors.append("QUESTION_VALIDATION_PAGE_NOT_LINKED_TO_SOURCE")
                continue
            artifact = self.session.get(
                QuestionAcquisitionArtifact,
                page.artifact_id,
                populate_existing=True,
            )
            if artifact is None or artifact.extraction_status not in usable_statuses:
                errors.append("QUESTION_VALIDATION_NO_USABLE_ARTIFACT")
                continue
            if span.end_char > len(page.text):
                errors.append("QUESTION_VALIDATION_SOURCE_SPAN_RANGE_INVALID")
                continue
            excerpt = page.text[span.start_char:span.end_char]
            if excerpt != span.excerpt or hashlib.sha256(
                excerpt.encode("utf-8")
            ).hexdigest() != span.excerpt_sha256:
                errors.append("QUESTION_VALIDATION_SOURCE_SPAN_STALE")
        return list(dict.fromkeys(errors))

    def check_answer(self, candidate: QuestionValidationCandidate) -> CheckOutcome:
        errors: list[str] = []
        answer = candidate.correct_answer.strip() if candidate.correct_answer else None
        options = list(candidate.options)
        if candidate.question_type == QuestionType.MULTIPLE_CHOICE:
            if len(options) < 2:
                errors.append("QUESTION_VALIDATION_MULTIPLE_CHOICE_OPTIONS_REQUIRED")
            labels = [item.label for item in options]
            orders = [item.order_index for item in options]
            if len(labels) != len(set(labels)) or len(orders) != len(set(orders)):
                errors.append("QUESTION_VALIDATION_OPTION_DUPLICATE")
            if any(not item.content.strip() for item in options):
                errors.append("QUESTION_VALIDATION_OPTION_CONTENT_REQUIRED")
            if answer is None or labels.count(answer) != 1:
                errors.append("QUESTION_VALIDATION_ANSWER_OPTION_MISMATCH")
        elif options:
            errors.append("QUESTION_VALIDATION_OPTIONS_NOT_ALLOWED")

        if candidate.question_type == QuestionType.TRUE_FALSE:
            if answer not in CANONICAL_TRUE_FALSE_ANSWERS:
                errors.append("QUESTION_VALIDATION_TRUE_FALSE_ANSWER_INVALID")
        elif candidate.question_type == QuestionType.SHORT_ANSWER and not answer:
            errors.append("QUESTION_VALIDATION_SHORT_ANSWER_REQUIRED")
        elif (
            candidate.question_type == QuestionType.OPEN_RESPONSE
            and not answer
            and not (candidate.explanation and candidate.explanation.strip())
        ):
            errors.append("QUESTION_VALIDATION_OPEN_RESPONSE_REVIEW_REQUIRED")
        return _outcome(errors, pass_code="QUESTION_VALIDATION_ANSWER_VALID")

    def check_taxonomy(self, candidate: QuestionValidationCandidate) -> CheckOutcome:
        errors: list[str] = []
        concept_ids = {link.concept_id for link in candidate.concept_links}
        problem_type_ids = {link.problem_type_id for link in candidate.problem_type_links}
        outcome_ids = {
            link.learning_outcome_id for link in candidate.learning_outcome_links
        }

        concepts = self._subject_concepts(concept_ids, candidate.subject_id)
        problem_types = self._subject_problem_types(problem_type_ids, candidate.subject_id)
        outcomes = self._subject_outcomes(outcome_ids, candidate.subject_id)
        if not concept_ids:
            errors.append("QUESTION_VALIDATION_CONCEPT_REQUIRED")
        if not problem_type_ids:
            errors.append("QUESTION_VALIDATION_PROBLEM_TYPE_REQUIRED")
        if not outcome_ids:
            errors.append("QUESTION_VALIDATION_LEARNING_OUTCOME_REQUIRED")
        if set(concepts) != concept_ids:
            errors.append("QUESTION_VALIDATION_TAXONOMY_CONCEPT_INVALID")
        if set(problem_types) != problem_type_ids:
            errors.append("QUESTION_VALIDATION_TAXONOMY_PROBLEM_TYPE_INVALID")
        if set(outcomes) != outcome_ids:
            errors.append("QUESTION_VALIDATION_TAXONOMY_LEARNING_OUTCOME_INVALID")
        if sum(link.is_primary for link in candidate.problem_type_links) != 1:
            errors.append("QUESTION_VALIDATION_PRIMARY_PROBLEM_TYPE_REQUIRED")
        if sum(link.weight for link in candidate.concept_links) > 1.000001:
            errors.append("QUESTION_VALIDATION_CONCEPT_WEIGHT_TOTAL_INVALID")
        if not self.matches_target(candidate, concept_ids, problem_type_ids):
            errors.append("QUESTION_VALIDATION_TARGET_MISMATCH")
        return _outcome(errors, pass_code="QUESTION_VALIDATION_TAXONOMY_VALID")

    def matches_target(
        self,
        candidate: QuestionValidationCandidate,
        concept_ids: set[UUID] | None = None,
        problem_type_ids: set[UUID] | None = None,
    ) -> bool:
        concept_ids = concept_ids or {link.concept_id for link in candidate.concept_links}
        problem_type_ids = problem_type_ids or {
            link.problem_type_id for link in candidate.problem_type_links
        }
        request = candidate.batch.acquisition_request
        if request.target_type == QuestionSupplyTargetType.CONCEPT:
            return request.concept_id is not None and request.concept_id in concept_ids
        if request.target_type == QuestionSupplyTargetType.PROBLEM_TYPE:
            return (
                request.problem_type_id is not None
                and request.problem_type_id in problem_type_ids
            )
        if request.target_type == QuestionSupplyTargetType.MISCONCEPTION:
            definition = self.session.get(
                MisconceptionDefinition, request.misconception_definition_id
            )
            if definition is None or definition.concept_id not in concept_ids:
                return False
            target_problem_type = request.problem_type_id or definition.problem_type_id
            return target_problem_type is None or target_problem_type in problem_type_ids
        return False

    def check_duplicate(self, candidate: QuestionValidationCandidate) -> CheckOutcome:
        production_match = self.duplicate_detector.detect(self.session, [candidate.content])
        duplicate_candidate = self.session.scalar(
            select(QuestionValidationCandidate.id).where(
                QuestionValidationCandidate.id != candidate.id,
                QuestionValidationCandidate.content_hash == candidate.content_hash,
                QuestionValidationCandidate.status.not_in(
                    {
                        QuestionValidationCandidateStatus.REJECTED,
                    }
                ),
            )
        )
        errors: list[str] = []
        details: dict[str, object] = {}
        if 0 in production_match:
            errors.append("QUESTION_VALIDATION_DUPLICATE")
            details["existing_question_id"] = str(
                production_match[0].existing_question_id
            )
        if duplicate_candidate is not None:
            errors.append("QUESTION_VALIDATION_DUPLICATE")
            details["duplicate_candidate_id"] = str(duplicate_candidate)
        outcome = _outcome(errors, pass_code="QUESTION_VALIDATION_DUPLICATE_CLEAR")
        return CheckOutcome(outcome.result, outcome.code, {**outcome.details, **details})

    def check_visual(self, candidate: QuestionValidationCandidate) -> CheckOutcome:
        return _outcome(
            ["QUESTION_VALIDATION_VISUAL_ASSET_REQUIRED"]
            if candidate.visual_required
            else [],
            pass_code="QUESTION_VALIDATION_VISUAL_NOT_REQUIRED",
        )

    def _subject_concepts(
        self, ids: Iterable[UUID], subject_id: UUID
    ) -> dict[UUID, Concept]:
        ids = set(ids)
        if not ids:
            return {}
        return {
            item.id: item
            for item in self.session.scalars(
                select(Concept).where(Concept.id.in_(ids), Concept.subject_id == subject_id)
            )
        }

    def _subject_problem_types(
        self, ids: Iterable[UUID], subject_id: UUID
    ) -> dict[UUID, ProblemType]:
        ids = set(ids)
        if not ids:
            return {}
        return {
            item.id: item
            for item in self.session.scalars(
                select(ProblemType)
                .join(Topic, ProblemType.topic_id == Topic.id)
                .join(Chapter, Topic.chapter_id == Chapter.id)
                .where(ProblemType.id.in_(ids), Chapter.subject_id == subject_id)
            )
        }

    def _subject_outcomes(
        self, ids: Iterable[UUID], subject_id: UUID
    ) -> dict[UUID, LearningOutcome]:
        ids = set(ids)
        if not ids:
            return {}
        return {
            item.id: item
            for item in self.session.scalars(
                select(LearningOutcome).where(
                    LearningOutcome.id.in_(ids),
                    LearningOutcome.subject_id == subject_id,
                )
            )
        }
