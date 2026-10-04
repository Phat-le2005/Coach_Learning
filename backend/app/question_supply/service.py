"""Service layer for question bank sufficiency evaluation and supply gap tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.misconceptions.models import MisconceptionDefinition
from app.question_supply.models import (
    QuestionSupplyGap,
    QuestionSupplyGapObservation,
    QuestionSupplyHealth,
    QuestionSupplyObservationSourceKind,
    QuestionSupplyReasonCode,
    QuestionSupplySeverity,
    QuestionSupplyStatus,
    QuestionSupplyTargetType,
    QuestionSupplyUseCase,
)
from app.question_supply.policy import QuestionSupplyPolicy
from app.question_supply.schemas import (
    QuestionBankSufficiencyReport,
)
from app.questions.eligibility import standalone_question_only
from app.questions.evaluation_eligibility import is_deterministically_auto_evaluable
from app.questions.exposure import QuestionExposureService
from app.questions.models import Question, QuestionStatus, QuestionType
from app.subjects.models import Subject

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class QuestionSupplyRequirement:
    """Specification of learning inventory requirements."""

    subject_id: UUID
    use_case: QuestionSupplyUseCase
    target_type: QuestionSupplyTargetType
    concept_id: UUID | None = None
    problem_type_id: UUID | None = None
    misconception_definition_id: UUID | None = None
    desired_difficulty: float | None = None
    minimum_required_count: int | None = None
    preferred_count: int | None = None
    allowed_question_types: frozenset[QuestionType] | None = None
    require_auto_evaluable: bool | None = None


class QuestionBankSufficiencyService:
    """Evaluates question bank readiness against specific pedagogical requirements."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def validate_target(self, requirement: QuestionSupplyRequirement) -> None:
        """Validate subject and targets exist and match subject boundaries."""
        subject = self.session.get(Subject, requirement.subject_id)
        if subject is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject was not found.")

        if requirement.concept_id is not None:
            concept = self.session.get(Concept, requirement.concept_id)
            if concept is None:
                raise ApplicationError(404, "CONCEPT_NOT_FOUND", "Concept was not found.")
            if concept.subject_id != requirement.subject_id:
                raise ApplicationError(
                    422,
                    "QUESTION_SUPPLY_CONCEPT_SUBJECT_MISMATCH",
                    "Target concept does not belong to the requested subject.",
                )

        if requirement.problem_type_id is not None:
            owner_subject_id = self.session.scalar(
                select(Chapter.subject_id)
                .join(Topic, Topic.chapter_id == Chapter.id)
                .join(ProblemType, ProblemType.topic_id == Topic.id)
                .where(ProblemType.id == requirement.problem_type_id)
            )
            if owner_subject_id is None:
                raise ApplicationError(
                    404, "PROBLEM_TYPE_NOT_FOUND", "ProblemType was not found."
                )
            if owner_subject_id != requirement.subject_id:
                raise ApplicationError(
                    422,
                    "QUESTION_SUPPLY_PROBLEM_TYPE_SUBJECT_MISMATCH",
                    "Target problem type does not belong to the requested subject.",
                )

        if requirement.misconception_definition_id is not None:
            misc = self.session.get(
                MisconceptionDefinition, requirement.misconception_definition_id
            )
            if misc is None:
                raise ApplicationError(
                    404,
                    "MISCONCEPTION_DEFINITION_NOT_FOUND",
                    "Misconception definition was not found.",
                )
            concept = self.session.get(Concept, misc.concept_id)
            if concept is None or concept.subject_id != requirement.subject_id:
                raise ApplicationError(
                    422,
                    "QUESTION_SUPPLY_MISCONCEPTION_SUBJECT_MISMATCH",
                    "Misconception definition does not belong to the requested subject.",
                )

    def assess(
        self,
        requirement: QuestionSupplyRequirement,
        *,
        student_id: UUID | None = None,
        exclude_question_ids: set[UUID] | None = None,
    ) -> QuestionBankSufficiencyReport:
        """Evaluate inventory sufficiency, reporting production and fresh availability."""
        self.validate_target(requirement)

        (
            default_min,
            default_preferred,
            tolerance,
            default_auto_eval,
            default_types,
        ) = QuestionSupplyPolicy.get_defaults(requirement.use_case)

        minimum_required = requirement.minimum_required_count or default_min
        preferred = requirement.preferred_count or default_preferred
        require_auto_eval = (
            requirement.require_auto_evaluable
            if requirement.require_auto_evaluable is not None
            else default_auto_eval
        )
        allowed_types = (
            requirement.allowed_question_types
            if requirement.allowed_question_types is not None
            else default_types
        )

        diff_min, diff_max = QuestionSupplyPolicy.compute_difficulty_band(
            requirement.desired_difficulty, tolerance
        )

        # Resolve effective target identifiers for querying
        target_concept_id = requirement.concept_id
        target_problem_type_id = requirement.problem_type_id
        if (
            requirement.target_type == QuestionSupplyTargetType.MISCONCEPTION
            and requirement.misconception_definition_id is not None
            and target_concept_id is None
        ):
            misc = self.session.get(
                MisconceptionDefinition, requirement.misconception_definition_id
            )
            if misc is not None:
                target_concept_id = misc.concept_id

        # Base statement for production approved questions
        base_stmt = (
            select(Question)
            .options(
                selectinload(Question.options),
                selectinload(Question.concept_links),
                selectinload(Question.problem_type_links),
                selectinload(Question.learning_outcome_links),
            )
            .where(
                Question.subject_id == requirement.subject_id,
                standalone_question_only(),
                Question.concept_links.any(),
                Question.problem_type_links.any(),
                Question.learning_outcome_links.any(),
            )
        )

        stmt_approved = base_stmt.where(Question.status == QuestionStatus.APPROVED)
        stmt_pipeline = base_stmt.where(
            Question.status.in_([QuestionStatus.DRAFT, QuestionStatus.REVIEW])
        )

        # Apply target filters
        if requirement.target_type == QuestionSupplyTargetType.CONCEPT:
            if target_concept_id is not None:
                stmt_approved = stmt_approved.where(
                    Question.concept_links.any(concept_id=target_concept_id)
                )
                stmt_pipeline = stmt_pipeline.where(
                    Question.concept_links.any(concept_id=target_concept_id)
                )
        elif requirement.target_type == QuestionSupplyTargetType.PROBLEM_TYPE:
            if target_problem_type_id is not None:
                stmt_approved = stmt_approved.where(
                    Question.problem_type_links.any(problem_type_id=target_problem_type_id)
                )
                stmt_pipeline = stmt_pipeline.where(
                    Question.problem_type_links.any(problem_type_id=target_problem_type_id)
                )
        elif requirement.target_type == QuestionSupplyTargetType.MISCONCEPTION:
            if target_concept_id is not None:
                stmt_approved = stmt_approved.where(
                    Question.concept_links.any(concept_id=target_concept_id)
                )
                stmt_pipeline = stmt_pipeline.where(
                    Question.concept_links.any(concept_id=target_concept_id)
                )
            if (
                requirement.use_case == QuestionSupplyUseCase.ADAPTIVE_REPAIR
                and target_problem_type_id is not None
            ):
                stmt_approved = stmt_approved.where(
                    Question.problem_type_links.any(problem_type_id=target_problem_type_id)
                )
                stmt_pipeline = stmt_pipeline.where(
                    Question.problem_type_links.any(problem_type_id=target_problem_type_id)
                )

        # Fetch and filter candidates
        approved_candidates = list(self.session.scalars(stmt_approved))
        pipeline_candidates = list(self.session.scalars(stmt_pipeline))

        eligible_approved: list[Question] = []
        for q in approved_candidates:
            if allowed_types is not None and q.question_type not in allowed_types:
                continue
            if require_auto_eval and not is_deterministically_auto_evaluable(q):
                continue
            eligible_approved.append(q)

        eligible_pipeline: list[Question] = []
        for q in pipeline_candidates:
            if allowed_types is not None and q.question_type not in allowed_types:
                continue
            if require_auto_eval and not is_deterministically_auto_evaluable(q):
                continue
            eligible_pipeline.append(q)

        approved_in_band = [
            q
            for q in eligible_approved
            if diff_min <= (q.difficulty if q.difficulty is not None else 0.5) <= diff_max
        ]

        approved_eligible_count = len(eligible_approved)
        approved_in_band_count = len(approved_in_band)
        pipeline_candidate_count = len(eligible_pipeline)

        fresh_eligible_count: int | None = None
        fresh_in_band_count: int | None = None
        excluded_exposure_count = 0

        if student_id is not None:
            exposure_service = QuestionExposureService(self.session)
            student_exposed = exposure_service.get_recent_exposed_question_ids(student_id)
            total_exclusions = set(student_exposed)
            if exclude_question_ids:
                total_exclusions.update(exclude_question_ids)

            fresh_eligible = [q for q in eligible_approved if q.id not in total_exclusions]
            fresh_in_band = [q for q in approved_in_band if q.id not in total_exclusions]

            fresh_eligible_count = len(fresh_eligible)
            fresh_in_band_count = len(fresh_in_band)
            excluded_exposure_count = approved_eligible_count - fresh_eligible_count

            effective_count = fresh_eligible_count
            effective_in_band = fresh_in_band_count
        else:
            effective_count = approved_eligible_count
            effective_in_band = approved_in_band_count

        health = QuestionSupplyPolicy.evaluate_health(
            effective_count, minimum_required, preferred
        )
        severity = QuestionSupplyPolicy.evaluate_severity(
            effective_count, minimum_required, preferred, effective_in_band
        )
        is_startable = QuestionSupplyPolicy.evaluate_is_startable(
            requirement.use_case, effective_count
        )

        reason_code: QuestionSupplyReasonCode | None = None
        if (
            student_id is not None
            and approved_eligible_count >= minimum_required
            and (fresh_eligible_count is not None and fresh_eligible_count < minimum_required)
        ):
            reason_code = QuestionSupplyReasonCode.STUDENT_EXPOSURE_EXHAUSTED
        elif approved_eligible_count == 0:
            reason_code = QuestionSupplyReasonCode.NO_APPROVED_TARGET_QUESTIONS
        elif approved_eligible_count < minimum_required:
            reason_code = QuestionSupplyReasonCode.INSUFFICIENT_APPROVED_TARGET_COUNT
        elif approved_in_band_count < minimum_required:
            reason_code = QuestionSupplyReasonCode.INSUFFICIENT_DIFFICULTY_COVERAGE

        return QuestionBankSufficiencyReport(
            subject_id=requirement.subject_id,
            use_case=requirement.use_case,
            target_type=requirement.target_type,
            concept_id=requirement.concept_id,
            problem_type_id=requirement.problem_type_id,
            misconception_definition_id=requirement.misconception_definition_id,
            desired_difficulty=requirement.desired_difficulty,
            difficulty_min=diff_min,
            difficulty_max=diff_max,
            minimum_required_count=minimum_required,
            preferred_count=preferred,
            approved_eligible_count=approved_eligible_count,
            approved_in_band_count=approved_in_band_count,
            fresh_eligible_count=fresh_eligible_count,
            fresh_in_band_count=fresh_in_band_count,
            excluded_exposure_count=excluded_exposure_count,
            pipeline_candidate_count=pipeline_candidate_count,
            health=health,
            severity=severity,
            reason_code=reason_code,
            is_startable=is_startable,
        )


class QuestionSupplyGapService:
    """Records aggregate gaps and demand observations with idempotency."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.sufficiency_service = QuestionBankSufficiencyService(session)

    def assess_and_record(
        self,
        *,
        requirement: QuestionSupplyRequirement,
        source_kind: QuestionSupplyObservationSourceKind,
        source_entity_id: UUID | None = None,
        student_id: UUID | None = None,
        exclude_question_ids: set[UUID] | None = None,
        commit: bool = False,
    ) -> tuple[QuestionBankSufficiencyReport, QuestionSupplyGap | None]:
        """Assess sufficiency and record gap if inventory is deficient (THIN or INSUFFICIENT)."""
        report = self.sufficiency_service.assess(
            requirement,
            student_id=student_id,
            exclude_question_ids=exclude_question_ids,
        )

        gap = self.record_gap(
            requirement=requirement,
            report=report,
            source_kind=source_kind,
            source_entity_id=source_entity_id,
            student_id=student_id,
            commit=commit,
        )
        return report, gap

    def record_gap(
        self,
        *,
        requirement: QuestionSupplyRequirement,
        report: QuestionBankSufficiencyReport,
        source_kind: QuestionSupplyObservationSourceKind,
        source_entity_id: UUID | None = None,
        student_id: UUID | None = None,
        commit: bool = False,
    ) -> QuestionSupplyGap | None:
        """Record aggregate gap and occurrence observation if report indicates shortage."""
        if report.health == QuestionSupplyHealth.SUFFICIENT:
            return None

        (
            _,
            _,
            _,
            default_auto_eval,
            default_types,
        ) = QuestionSupplyPolicy.get_defaults(requirement.use_case)
        require_auto_eval = (
            requirement.require_auto_evaluable
            if requirement.require_auto_evaluable is not None
            else default_auto_eval
        )
        allowed_types = (
            requirement.allowed_question_types
            if requirement.allowed_question_types is not None
            else default_types
        )

        signature = QuestionSupplyPolicy.compute_signature(
            subject_id=requirement.subject_id,
            use_case=requirement.use_case,
            target_type=requirement.target_type,
            concept_id=requirement.concept_id,
            problem_type_id=requirement.problem_type_id,
            misconception_definition_id=requirement.misconception_definition_id,
            difficulty_min=report.difficulty_min,
            difficulty_max=report.difficulty_max,
            minimum_required_count=report.minimum_required_count,
            allowed_question_types=allowed_types,
            require_auto_evaluable=require_auto_eval,
        )

        now = datetime.now(timezone.utc)
        gap = self.session.scalar(
            select(QuestionSupplyGap).where(QuestionSupplyGap.signature == signature)
        )

        is_new_gap = gap is None
        if gap is None:
            gap = QuestionSupplyGap(
                signature=signature,
                subject_id=requirement.subject_id,
                use_case=requirement.use_case,
                target_type=requirement.target_type,
                concept_id=requirement.concept_id,
                problem_type_id=requirement.problem_type_id,
                misconception_definition_id=requirement.misconception_definition_id,
                desired_difficulty=requirement.desired_difficulty,
                difficulty_min=report.difficulty_min,
                difficulty_max=report.difficulty_max,
                minimum_required_count=report.minimum_required_count,
                preferred_count=report.preferred_count,
                approved_eligible_count=report.approved_eligible_count,
                approved_in_band_count=report.approved_in_band_count,
                pipeline_candidate_count=report.pipeline_candidate_count,
                severity=report.severity,
                status=QuestionSupplyStatus.OPEN,
                demand_count=1,
                first_observed_at=now,
                last_observed_at=now,
                last_assessed_at=now,
            )
            self.session.add(gap)
            self.session.flush()
        else:
            # Update snapshot
            gap.approved_eligible_count = report.approved_eligible_count
            gap.approved_in_band_count = report.approved_in_band_count
            gap.pipeline_candidate_count = report.pipeline_candidate_count
            gap.severity = report.severity
            gap.last_assessed_at = now
            if gap.status == QuestionSupplyStatus.RESOLVED:
                gap.status = QuestionSupplyStatus.OPEN
                gap.last_observed_at = now

        # Record observation with idempotency
        existing_obs = None
        if source_entity_id is not None:
            existing_obs = self.session.scalar(
                select(QuestionSupplyGapObservation).where(
                    QuestionSupplyGapObservation.gap_id == gap.id,
                    QuestionSupplyGapObservation.source_kind == source_kind,
                    QuestionSupplyGapObservation.source_entity_id == source_entity_id,
                )
            )

        if existing_obs is None:
            obs = QuestionSupplyGapObservation(
                gap_id=gap.id,
                student_id=student_id,
                source_kind=source_kind,
                source_entity_id=source_entity_id,
                reason_code=report.reason_code or QuestionSupplyReasonCode.INSUFFICIENT_APPROVED_TARGET_COUNT,
                observed_approved_eligible_count=report.approved_eligible_count,
                observed_approved_in_band_count=report.approved_in_band_count,
                observed_fresh_eligible_count=report.fresh_eligible_count,
                observed_fresh_in_band_count=report.fresh_in_band_count,
                observed_excluded_exposure_count=report.excluded_exposure_count,
                created_at=now,
            )
            self.session.add(obs)
            if not is_new_gap:
                gap.demand_count += 1
                gap.last_observed_at = now

        self.session.flush()
        if commit:
            self.session.commit()
        return gap

    def reassess_gap(self, gap_id: UUID, *, commit: bool = True) -> QuestionSupplyGap:
        """Reassess inventory against persisted gap requirement, resolving if satisfied."""
        gap = self.session.get(QuestionSupplyGap, gap_id)
        if gap is None:
            raise ApplicationError(404, "QUESTION_SUPPLY_GAP_NOT_FOUND", "Supply gap was not found.")

        req = QuestionSupplyRequirement(
            subject_id=gap.subject_id,
            use_case=gap.use_case,
            target_type=gap.target_type,
            concept_id=gap.concept_id,
            problem_type_id=gap.problem_type_id,
            misconception_definition_id=gap.misconception_definition_id,
            desired_difficulty=gap.desired_difficulty,
            minimum_required_count=gap.minimum_required_count,
            preferred_count=gap.preferred_count,
        )
        report = self.sufficiency_service.assess(req)

        now = datetime.now(timezone.utc)
        gap.approved_eligible_count = report.approved_eligible_count
        gap.approved_in_band_count = report.approved_in_band_count
        gap.pipeline_candidate_count = report.pipeline_candidate_count
        gap.severity = report.severity
        gap.last_assessed_at = now

        if report.approved_eligible_count >= gap.preferred_count:
            gap.status = QuestionSupplyStatus.RESOLVED
        elif report.approved_eligible_count >= gap.minimum_required_count:
            if gap.status == QuestionSupplyStatus.RESOLVED:
                gap.status = QuestionSupplyStatus.OPEN
        else:
            gap.status = QuestionSupplyStatus.OPEN

        self.session.flush()
        if commit:
            self.session.commit()
        return gap

    def reassess_open_gaps(self, *, commit: bool = True) -> list[QuestionSupplyGap]:
        """Reassess all open gaps."""
        open_gaps = list(
            self.session.scalars(
                select(QuestionSupplyGap).where(QuestionSupplyGap.status == QuestionSupplyStatus.OPEN)
            )
        )
        results: list[QuestionSupplyGap] = []
        for gap in open_gaps:
            reassessed = self.reassess_gap(gap.id, commit=False)
            results.append(reassessed)
        if commit:
            self.session.commit()
        return results

    def get_gap(self, gap_id: UUID) -> QuestionSupplyGap | None:
        return self.session.scalar(
            select(QuestionSupplyGap)
            .options(selectinload(QuestionSupplyGap.observations))
            .where(QuestionSupplyGap.id == gap_id)
        )

    def list_gaps(
        self,
        *,
        status: QuestionSupplyStatus | None = None,
        subject_id: UUID | None = None,
        use_case: QuestionSupplyUseCase | None = None,
        severity: QuestionSupplySeverity | None = None,
        target_type: QuestionSupplyTargetType | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[QuestionSupplyGap]:
        stmt = select(QuestionSupplyGap)
        if status is not None:
            stmt = stmt.where(QuestionSupplyGap.status == status)
        if subject_id is not None:
            stmt = stmt.where(QuestionSupplyGap.subject_id == subject_id)
        if use_case is not None:
            stmt = stmt.where(QuestionSupplyGap.use_case == use_case)
        if severity is not None:
            stmt = stmt.where(QuestionSupplyGap.severity == severity)
        if target_type is not None:
            stmt = stmt.where(QuestionSupplyGap.target_type == target_type)

        stmt = stmt.order_by(
            QuestionSupplyGap.last_observed_at.desc(), QuestionSupplyGap.id.desc()
        ).offset(offset).limit(limit)

        return list(self.session.scalars(stmt))
