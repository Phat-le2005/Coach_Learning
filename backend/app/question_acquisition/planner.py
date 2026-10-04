"""Planning logic for question acquisition against open supply gaps."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.misconceptions.models import MisconceptionDefinition
from app.question_acquisition.models import QuestionAcquisitionStrategy
from app.question_acquisition.policy import (
    PlannedAcquisitionCounts,
    QuestionAcquisitionPolicy,
    RankedCandidateInfo,
)
from app.question_supply.models import (
    QuestionSupplyGap,
    QuestionSupplyGapObservation,
    QuestionSupplyReasonCode,
    QuestionSupplyTargetType,
    QuestionSupplyUseCase,
)
from app.question_supply.policy import QuestionSupplyPolicy
from app.questions.eligibility import standalone_question_only
from app.questions.models import Question, QuestionStatus


@dataclass
class AcquisitionPlan:
    gap_id: UUID
    strategy: QuestionAcquisitionStrategy
    required_new_candidate_count: int
    existing_candidate_count: int
    external_candidate_target_count: int
    ranked_candidates: list[RankedCandidateInfo]


class QuestionAcquisitionPlanner:
    """Evaluates question supply gap inventory and produces an acquisition plan."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def plan_for_gap(self, gap: QuestionSupplyGap) -> AcquisitionPlan:
        """Analyze gap and return acquisition strategy with ranked pipeline candidates."""
        base_stmt = (
            select(Question)
            .options(
                selectinload(Question.options),
                selectinload(Question.concept_links),
                selectinload(Question.problem_type_links),
                selectinload(Question.learning_outcome_links),
            )
            .where(
                Question.subject_id == gap.subject_id,
                Question.status.in_([QuestionStatus.DRAFT, QuestionStatus.REVIEW]),
                standalone_question_only(),
                Question.concept_links.any(),
                Question.problem_type_links.any(),
                Question.learning_outcome_links.any(),
            )
        )

        if gap.target_type == QuestionSupplyTargetType.CONCEPT:
            assert gap.concept_id is not None
            base_stmt = base_stmt.where(
                Question.concept_links.any(concept_id=gap.concept_id)
            )
        elif gap.target_type == QuestionSupplyTargetType.PROBLEM_TYPE:
            assert gap.problem_type_id is not None
            base_stmt = base_stmt.where(
                Question.problem_type_links.any(problem_type_id=gap.problem_type_id)
            )
        elif gap.target_type == QuestionSupplyTargetType.MISCONCEPTION:
            assert gap.misconception_definition_id is not None
            misc = self.session.get(MisconceptionDefinition, gap.misconception_definition_id)
            target_concept_id = misc.concept_id if misc else gap.concept_id
            assert target_concept_id is not None
            base_stmt = base_stmt.where(
                Question.concept_links.any(concept_id=target_concept_id)
            )
            if (
                gap.use_case == QuestionSupplyUseCase.ADAPTIVE_REPAIR
                and gap.problem_type_id is not None
            ):
                base_stmt = base_stmt.where(
                    Question.problem_type_links.any(problem_type_id=gap.problem_type_id)
                )

        raw_candidates = list(self.session.scalars(base_stmt))

        (
            _,
            _,
            _,
            default_auto_eval,
            default_types,
        ) = QuestionSupplyPolicy.get_defaults(gap.use_case)

        ranked = QuestionAcquisitionPolicy.rank_existing_candidates(
            raw_candidates,
            difficulty_min=gap.difficulty_min,
            difficulty_max=gap.difficulty_max,
            desired_difficulty=gap.desired_difficulty,
            allowed_types=default_types,
            require_auto_eval=default_auto_eval,
        )

        existing_in_band_count = sum(1 for c in ranked if c.difficulty_in_band)
        total_existing_count = len(ranked)

        fresh_in_band_count: int | None = None
        if gap.reason_code == QuestionSupplyReasonCode.STUDENT_EXPOSURE_EXHAUSTED:
            latest_obs = self.session.scalar(
                select(QuestionSupplyGapObservation)
                .where(QuestionSupplyGapObservation.gap_id == gap.id)
                .order_by(QuestionSupplyGapObservation.created_at.desc())
            )
            if latest_obs is not None:
                fresh_in_band_count = latest_obs.observed_fresh_in_band_count

        planned_counts: PlannedAcquisitionCounts = QuestionAcquisitionPolicy.calculate_acquisition_plan(
            preferred_count=gap.preferred_count,
            approved_in_band_count=gap.approved_in_band_count,
            fresh_in_band_count=fresh_in_band_count,
            reason_code=gap.reason_code,
            existing_in_band_candidates_count=existing_in_band_count,
            total_existing_candidates_count=total_existing_count,
        )

        return AcquisitionPlan(
            gap_id=gap.id,
            strategy=planned_counts.strategy,
            required_new_candidate_count=planned_counts.required_new_candidate_count,
            existing_candidate_count=planned_counts.existing_candidate_count,
            external_candidate_target_count=planned_counts.external_candidate_target_count,
            ranked_candidates=ranked,
        )
