"""Service layer for question bank sufficiency evaluation and supply gap tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
        """Validate subject and targets exist, match subject boundaries, and validate requirements."""
        subject = self.session.get(Subject, requirement.subject_id)
        if subject is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject was not found.")

        # 1. Target shape validation
        if requirement.target_type == QuestionSupplyTargetType.CONCEPT:
            if requirement.concept_id is None:
                raise ApplicationError(
                    422,
                    "QUESTION_SUPPLY_CONCEPT_REQUIRED",
                    "Concept target requires concept_id.",
                )
            concept = self.session.get(Concept, requirement.concept_id)
            if concept is None:
                raise ApplicationError(404, "CONCEPT_NOT_FOUND", "Concept was not found.")
            if concept.subject_id != requirement.subject_id:
                raise ApplicationError(
                    422,
                    "QUESTION_SUPPLY_CONCEPT_SUBJECT_MISMATCH",
                    "Target concept does not belong to the requested subject.",
                )
        elif requirement.target_type == QuestionSupplyTargetType.PROBLEM_TYPE:
            if requirement.problem_type_id is None:
                raise ApplicationError(
                    422,
                    "QUESTION_SUPPLY_PROBLEM_TYPE_REQUIRED",
                    "ProblemType target requires problem_type_id.",
                )
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
        elif requirement.target_type == QuestionSupplyTargetType.MISCONCEPTION:
            if requirement.misconception_definition_id is None:
                raise ApplicationError(
                    422,
                    "QUESTION_SUPPLY_MISCONCEPTION_REQUIRED",
                    "Misconception target requires misconception_definition_id.",
                )
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
            if requirement.concept_id is not None and requirement.concept_id != misc.concept_id:
                raise ApplicationError(
                    422,
                    "QUESTION_SUPPLY_MISCONCEPTION_CONCEPT_MISMATCH",
                    "Target concept_id does not match misconception definition concept.",
                )
            if requirement.problem_type_id is not None:
                pt_subject_id = self.session.scalar(
                    select(Chapter.subject_id)
                    .join(Topic, Topic.chapter_id == Chapter.id)
                    .join(ProblemType, ProblemType.topic_id == Topic.id)
                    .where(ProblemType.id == requirement.problem_type_id)
                )
                if pt_subject_id is None:
                    raise ApplicationError(
                        404, "PROBLEM_TYPE_NOT_FOUND", "ProblemType was not found."
                    )
                if pt_subject_id != requirement.subject_id:
                    raise ApplicationError(
                        422,
                        "QUESTION_SUPPLY_PROBLEM_TYPE_SUBJECT_MISMATCH",
                        "Target problem type does not belong to the requested subject.",
                    )

        # 2. Difficulty validation
        if requirement.desired_difficulty is not None:
            if not (0.0 <= float(requirement.desired_difficulty) <= 1.0):
                raise ApplicationError(
                    422,
                    "INVALID_QUESTION_SUPPLY_DIFFICULTY",
                    "Desired difficulty must be between 0.0 and 1.0.",
                )

        # 3. Count overrides validation
        (default_min, default_preferred, _, _, _) = QuestionSupplyPolicy.get_defaults(
            requirement.use_case
        )
        if requirement.minimum_required_count is not None:
            if requirement.minimum_required_count <= 0:
                raise ApplicationError(
                    422,
                    "INVALID_QUESTION_SUPPLY_MINIMUM_COUNT",
                    "Minimum required count must be positive.",
                )
        if requirement.preferred_count is not None:
            if requirement.preferred_count <= 0:
                raise ApplicationError(
                    422,
                    "INVALID_QUESTION_SUPPLY_PREFERRED_COUNT",
                    "Preferred count must be positive.",
                )

        effective_min = requirement.minimum_required_count or default_min
        if requirement.preferred_count is not None:
            if requirement.preferred_count < effective_min:
                raise ApplicationError(
                    422,
                    "INVALID_QUESTION_SUPPLY_PREFERRED_COUNT",
                    "Preferred count cannot be less than minimum required count.",
                )

        # 4. Allowed question types validation
        if requirement.allowed_question_types is not None:
            if len(requirement.allowed_question_types) == 0:
                raise ApplicationError(
                    422,
                    "INVALID_QUESTION_SUPPLY_ALLOWED_TYPES",
                    "Allowed question types must not be empty.",
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
        if requirement.preferred_count is not None:
            preferred = requirement.preferred_count
        else:
            preferred = max(default_preferred, minimum_required)

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
            assert requirement.concept_id is not None
            stmt_approved = stmt_approved.where(
                Question.concept_links.any(concept_id=requirement.concept_id)
            )
            stmt_pipeline = stmt_pipeline.where(
                Question.concept_links.any(concept_id=requirement.concept_id)
            )
        elif requirement.target_type == QuestionSupplyTargetType.PROBLEM_TYPE:
            assert requirement.problem_type_id is not None
            stmt_approved = stmt_approved.where(
                Question.problem_type_links.any(problem_type_id=requirement.problem_type_id)
            )
            stmt_pipeline = stmt_pipeline.where(
                Question.problem_type_links.any(problem_type_id=requirement.problem_type_id)
            )
        elif requirement.target_type == QuestionSupplyTargetType.MISCONCEPTION:
            assert requirement.misconception_definition_id is not None
            misc = self.session.get(MisconceptionDefinition, requirement.misconception_definition_id)
            target_concept_id = misc.concept_id if misc else requirement.concept_id
            assert target_concept_id is not None
            stmt_approved = stmt_approved.where(
                Question.concept_links.any(concept_id=target_concept_id)
            )
            stmt_pipeline = stmt_pipeline.where(
                Question.concept_links.any(concept_id=target_concept_id)
            )
            if (
                requirement.use_case == QuestionSupplyUseCase.ADAPTIVE_REPAIR
                and requirement.problem_type_id is not None
            ):
                stmt_approved = stmt_approved.where(
                    Question.problem_type_links.any(problem_type_id=requirement.problem_type_id)
                )
                stmt_pipeline = stmt_pipeline.where(
                    Question.problem_type_links.any(problem_type_id=requirement.problem_type_id)
                )

        # Fetch raw candidates
        approved_target_candidates = list(self.session.scalars(stmt_approved))
        pipeline_target_candidates = list(self.session.scalars(stmt_pipeline))

        raw_approved_target_count = len(approved_target_candidates)

        # Filter by allowed question types
        type_filtered_approved = [
            q
            for q in approved_target_candidates
            if allowed_types is None or q.question_type in allowed_types
        ]
        approved_type_eligible_count = len(type_filtered_approved)

        # Filter by auto-evaluable
        eligible_approved = [
            q
            for q in type_filtered_approved
            if not require_auto_eval or is_deterministically_auto_evaluable(q)
        ]

        approved_in_band = [
            q
            for q in eligible_approved
            if diff_min <= (q.difficulty if q.difficulty is not None else 0.5) <= diff_max
        ]

        approved_eligible_count = len(eligible_approved)
        approved_in_band_count = len(approved_in_band)

        # Pipeline candidate count: raw DRAFT/REVIEW candidates matching structural & target criteria
        pipeline_candidate_count = len(pipeline_target_candidates)

        # Pipeline runtime eligible count: subset satisfying runtime allowed types and auto-evaluable
        eligible_pipeline = [
            q
            for q in pipeline_target_candidates
            if (allowed_types is None or q.question_type in allowed_types)
            and (not require_auto_eval or is_deterministically_auto_evaluable(q))
        ]
        pipeline_runtime_eligible_count = len(eligible_pipeline)

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
            effective_count=effective_count,
            effective_in_band_count=effective_in_band,
            minimum_required=minimum_required,
            preferred=preferred,
        )
        severity = QuestionSupplyPolicy.evaluate_severity(
            effective_count=effective_count,
            effective_in_band_count=effective_in_band,
            minimum_required=minimum_required,
            preferred=preferred,
        )
        is_startable = QuestionSupplyPolicy.evaluate_is_startable(
            requirement.use_case, effective_count
        )

        reason_code: QuestionSupplyReasonCode | None = None
        if health == QuestionSupplyHealth.SUFFICIENT:
            reason_code = None
        elif (
            student_id is not None
            and approved_eligible_count >= minimum_required
            and approved_in_band_count >= minimum_required
            and (effective_count < minimum_required or effective_in_band < minimum_required)
        ):
            reason_code = QuestionSupplyReasonCode.STUDENT_EXPOSURE_EXHAUSTED
        elif raw_approved_target_count == 0:
            reason_code = QuestionSupplyReasonCode.NO_APPROVED_TARGET_QUESTIONS
        elif require_auto_eval and approved_eligible_count == 0:
            reason_code = QuestionSupplyReasonCode.NO_AUTO_EVALUABLE_TARGET_QUESTIONS
        elif effective_count < minimum_required:
            reason_code = QuestionSupplyReasonCode.INSUFFICIENT_APPROVED_TARGET_COUNT
        elif effective_in_band < minimum_required:
            reason_code = QuestionSupplyReasonCode.INSUFFICIENT_DIFFICULTY_COVERAGE
        elif health == QuestionSupplyHealth.THIN:
            if effective_count < preferred:
                reason_code = QuestionSupplyReasonCode.THIN_APPROVED_TARGET_COUNT
            else:
                reason_code = QuestionSupplyReasonCode.THIN_DIFFICULTY_COVERAGE

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
            approved_target_count=raw_approved_target_count,
            approved_type_eligible_count=approved_type_eligible_count,
            fresh_eligible_count=fresh_eligible_count,
            fresh_in_band_count=fresh_in_band_count,
            excluded_exposure_count=excluded_exposure_count,
            pipeline_candidate_count=pipeline_candidate_count,
            pipeline_runtime_eligible_count=pipeline_runtime_eligible_count,
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

        # Requirement 34: Non-manual persistent observations must provide source_entity_id
        if (
            source_kind != QuestionSupplyObservationSourceKind.MANUAL_ASSESSMENT
            and source_entity_id is None
        ):
            raise ApplicationError(
                422,
                "QUESTION_SUPPLY_SOURCE_ENTITY_REQUIRED",
                "Persistent supply gap observation requires source_entity_id.",
            )

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

        is_new_gap = False
        if gap is None:
            try:
                with self.session.begin_nested():
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
                        pipeline_runtime_eligible_count=report.pipeline_runtime_eligible_count,
                        severity=report.severity,
                        status=QuestionSupplyStatus.OPEN,
                        reason_code=report.reason_code or QuestionSupplyReasonCode.INSUFFICIENT_APPROVED_TARGET_COUNT,
                        demand_count=0,
                        first_observed_at=now,
                        last_observed_at=now,
                        last_assessed_at=now,
                    )
                    self.session.add(gap)
                    self.session.flush()
                    is_new_gap = True
            except IntegrityError:
                # Concurrent transaction won the race on unique signature
                gap = self.session.scalar(
                    select(QuestionSupplyGap).where(QuestionSupplyGap.signature == signature)
                )
                if gap is None:
                    raise

        if not is_new_gap:
            # Update snapshot
            gap.approved_eligible_count = report.approved_eligible_count
            gap.approved_in_band_count = report.approved_in_band_count
            gap.pipeline_candidate_count = report.pipeline_candidate_count
            gap.pipeline_runtime_eligible_count = report.pipeline_runtime_eligible_count
            gap.severity = report.severity
            if report.reason_code:
                gap.reason_code = report.reason_code
            gap.last_assessed_at = now
            if gap.status == QuestionSupplyStatus.RESOLVED:
                gap.status = QuestionSupplyStatus.OPEN
                gap.last_observed_at = now

        # Record observation with idempotency & concurrency safety
        if source_entity_id is not None:
            existing_obs = self.session.scalar(
                select(QuestionSupplyGapObservation).where(
                    QuestionSupplyGapObservation.gap_id == gap.id,
                    QuestionSupplyGapObservation.source_kind == source_kind,
                    QuestionSupplyGapObservation.source_entity_id == source_entity_id,
                )
            )
            if existing_obs is None:
                try:
                    with self.session.begin_nested():
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
                        self.session.flush()
                        gap.demand_count += 1
                        gap.last_observed_at = now
                except IntegrityError:
                    # Concurrent duplicate observation race
                    pass
        elif is_new_gap and gap.demand_count == 0:
            gap.demand_count = 1

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

        assessment_student_id: UUID | None = None
        if gap.reason_code == QuestionSupplyReasonCode.STUDENT_EXPOSURE_EXHAUSTED:
            # Reassess against latest observation student context
            latest_obs = self.session.scalar(
                select(QuestionSupplyGapObservation)
                .where(
                    QuestionSupplyGapObservation.gap_id == gap.id,
                    QuestionSupplyGapObservation.student_id.is_not(None),
                )
                .order_by(QuestionSupplyGapObservation.created_at.desc())
            )
            if latest_obs is not None:
                assessment_student_id = latest_obs.student_id

        report = self.sufficiency_service.assess(req, student_id=assessment_student_id)

        now = datetime.now(timezone.utc)
        gap.approved_eligible_count = report.approved_eligible_count
        gap.approved_in_band_count = report.approved_in_band_count
        gap.pipeline_candidate_count = report.pipeline_candidate_count
        gap.pipeline_runtime_eligible_count = report.pipeline_runtime_eligible_count
        gap.severity = report.severity
        gap.last_assessed_at = now
        if report.reason_code:
            gap.reason_code = report.reason_code

        # Health must be SUFFICIENT to resolve. THIN or INSUFFICIENT remain OPEN!
        if report.health == QuestionSupplyHealth.SUFFICIENT:
            gap.status = QuestionSupplyStatus.RESOLVED
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
