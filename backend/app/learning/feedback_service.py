from __future__ import annotations

from datetime import datetime, timezone
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ApplicationError
from app.knowledge_gap.models import (
    RootCauseVerificationTarget,
    RootCauseVerificationTargetType,
)
from app.learning.feedback_models import (
    LearningFeedbackAction,
    LearningFeedbackDecision,
    LearningFeedbackReasonCode,
)
from app.learning.feedback_policy import LearningFeedbackPolicy
from app.learning.feedback_schemas import (
    LearningFeedbackDecisionRead,
    LearningFeedbackNextLearningInfo,
    LearningFeedbackQuestionInfo,
    LearningFeedbackQuestionOptionInfo,
    LearningFeedbackRetryInfo,
    LearningFeedbackReviewInfo,
    LearningFeedbackTargetInfo,
)
from app.questions.models import Question, QuestionStatus
from app.recommendations.priority_service import LearningPriorityService
from app.recommendations.question_service import QuestionRecommendationService
from app.recommendations.schemas import PriorityReasonCode
from app.repair.lineage import RepairLineageExposureService
from app.repair.models import AdaptiveRepairOutcome, AdaptiveRepairSession, AdaptiveRepairStatus
from app.review.models import ReviewSchedule
from app.review.service import ReviewScheduleService

logger = logging.getLogger(__name__)


class LearningFeedbackService:
    """Deterministic, idempotent feedback resolver following adaptive root-cause repair."""

    def __init__(
        self,
        session: Session,
        *,
        policy: LearningFeedbackPolicy | None = None,
        review_service: ReviewScheduleService | None = None,
        priority_service: LearningPriorityService | None = None,
        recommendation_service: QuestionRecommendationService | None = None,
        lineage_service: RepairLineageExposureService | None = None,
    ) -> None:
        self.session = session
        self.policy = policy or LearningFeedbackPolicy()
        self.review_service = review_service or ReviewScheduleService(session)
        self.priority_service = priority_service or LearningPriorityService(session)
        self.recommendations = recommendation_service or QuestionRecommendationService(session)
        self.lineage_service = lineage_service or RepairLineageExposureService(session)

    def resolve_feedback(self, adaptive_session_id: UUID) -> LearningFeedbackDecisionRead:
        """Resolve or retrieve the idempotent learning feedback decision for a completed repair session."""
        adaptive = self.session.get(AdaptiveRepairSession, adaptive_session_id)
        if adaptive is None:
            raise ApplicationError(404, "ADAPTIVE_REPAIR_NOT_FOUND", "Adaptive repair session was not found.")

        if adaptive.status != AdaptiveRepairStatus.COMPLETED or adaptive.outcome == AdaptiveRepairOutcome.PENDING:
            raise ApplicationError(
                409,
                "ADAPTIVE_REPAIR_NOT_COMPLETED",
                "Learning feedback cannot be resolved for an incomplete adaptive repair session.",
            )

        existing = self.session.scalar(
            select(LearningFeedbackDecision).where(
                LearningFeedbackDecision.adaptive_repair_session_id == adaptive.id
            )
        )
        if existing is not None:
            return self._build_read(existing, adaptive)

        review_schedule_id: UUID | None = None
        recommended_question_id: UUID | None = None

        if adaptive.outcome == AdaptiveRepairOutcome.RESOLVED:
            # 1. Schedule spaced review with failure isolation
            review_schedule_id = self._schedule_review_isolated(adaptive)

            # 2. Query next learning priorities (excluding repaired target)
            priorities = self.priority_service.get_priorities(adaptive.student_id, adaptive.subject_id)
            filtered = [
                p
                for p in priorities
                if not (
                    (adaptive.target_problem_type_id and p.problem_type_id == adaptive.target_problem_type_id)
                    or (adaptive.target_concept_id and p.concept_id == adaptive.target_concept_id)
                    or p.reason_code == PriorityReasonCode.VERIFIED_ROOT_CAUSE
                )
            ]
            current_lesson_p = next(
                (p for p in filtered if p.reason_code == PriorityReasonCode.CURRENT_LESSON), None
            )
            has_current_lesson = current_lesson_p is not None
            has_other_priority = bool(filtered)

            action, reason_code, retry_allowed = self.policy.decide(
                outcome=adaptive.outcome,
                repair_cycle_index=adaptive.repair_cycle_index,
                has_fresh_question=False,
                has_current_lesson=has_current_lesson,
                has_other_learning_priority=has_other_priority,
            )

            chosen_priority = current_lesson_p or (filtered[0] if filtered else None)
            if chosen_priority is not None:
                try:
                    rec = self.recommendations.recommend(
                        adaptive.student_id,
                        adaptive.subject_id,
                        target_problem_type_id=chosen_priority.problem_type_id,
                        target_concept_id=chosen_priority.concept_id,
                    )
                    if rec is not None:
                        recommended_question_id = rec.question_id
                except Exception as e:
                    logger.warning("Optional question recommendation failed for next learning priority")

        elif adaptive.outcome == AdaptiveRepairOutcome.NEEDS_MORE_PRACTICE:
            has_fresh_question = False
            if adaptive.repair_cycle_index < self.policy.max_cycles:
                has_fresh_question = self._has_fresh_retry_question(adaptive)

            action, reason_code, retry_allowed = self.policy.decide(
                outcome=adaptive.outcome,
                repair_cycle_index=adaptive.repair_cycle_index,
                has_fresh_question=has_fresh_question,
                has_current_lesson=False,
                has_other_learning_priority=False,
            )

        elif adaptive.outcome == AdaptiveRepairOutcome.BANK_EXHAUSTED:
            action, reason_code, retry_allowed = self.policy.decide(
                outcome=adaptive.outcome,
                repair_cycle_index=adaptive.repair_cycle_index,
                has_fresh_question=False,
                has_current_lesson=False,
                has_other_learning_priority=False,
            )
        else:
            raise ApplicationError(
                409,
                "ADAPTIVE_REPAIR_INVALID_OUTCOME",
                f"Unhandled repair outcome: {adaptive.outcome}",
            )

        decision = LearningFeedbackDecision(
            student_id=adaptive.student_id,
            subject_id=adaptive.subject_id,
            adaptive_repair_session_id=adaptive.id,
            action=action,
            reason_code=reason_code,
            target_type=adaptive.target_type,
            target_concept_id=adaptive.target_concept_id,
            target_problem_type_id=adaptive.target_problem_type_id,
            recommended_question_id=recommended_question_id,
            review_schedule_id=review_schedule_id,
            repair_cycle_index=adaptive.repair_cycle_index,
            retry_allowed=retry_allowed,
        )
        self.session.add(decision)
        self.session.flush()

        return self._build_read(decision, adaptive)

    def get_latest_feedback(
        self, student_id: UUID, subject_id: UUID | None = None
    ) -> LearningFeedbackDecisionRead | None:
        """Fetch the most recent learning feedback decision for a student."""
        query = (
            select(LearningFeedbackDecision)
            .where(LearningFeedbackDecision.student_id == student_id)
            .order_by(LearningFeedbackDecision.created_at.desc(), LearningFeedbackDecision.id.desc())
        )
        if subject_id is not None:
            query = query.where(LearningFeedbackDecision.subject_id == subject_id)
        decision = self.session.scalar(query)
        if decision is None:
            return None
        adaptive = self.session.get(AdaptiveRepairSession, decision.adaptive_repair_session_id)
        if adaptive is None:
            return None
        return self._build_read(decision, adaptive)

    def _schedule_review_isolated(self, adaptive: AdaptiveRepairSession) -> UUID | None:
        try:
            with self.session.begin_nested():
                schedule: ReviewSchedule | None = None
                # Misconceptions belong to concepts; schedule concept review
                if adaptive.target_type == RootCauseVerificationTargetType.CONCEPT or (
                    adaptive.target_type == RootCauseVerificationTargetType.MISCONCEPTION
                    and adaptive.target_concept_id is not None
                ):
                    schedule = self.review_service.ensure_concept_schedule(
                        adaptive.student_id,
                        adaptive.target_concept_id,
                        initial_interval_days=self.policy.resolved_review_interval_days,
                    )
                elif adaptive.target_type == RootCauseVerificationTargetType.PROBLEM_TYPE:
                    if adaptive.target_problem_type_id is not None:
                        schedule = self.review_service.ensure_problem_type_schedule(
                            adaptive.student_id,
                            adaptive.target_problem_type_id,
                            initial_interval_days=self.policy.resolved_review_interval_days,
                        )
                elif adaptive.target_concept_id is not None:
                    schedule = self.review_service.ensure_concept_schedule(
                        adaptive.student_id,
                        adaptive.target_concept_id,
                        initial_interval_days=self.policy.resolved_review_interval_days,
                    )
                return schedule.id if schedule is not None else None
        except Exception:
            logger.exception("Failed to schedule review for resolved session %s", adaptive.id)
            return None

    def _has_fresh_retry_question(self, adaptive: AdaptiveRepairSession) -> bool:
        target = self.session.get(RootCauseVerificationTarget, adaptive.verification_target_id)
        if target is None:
            return False

        exclusions = self.lineage_service.get_lineage_excluded_question_ids(
            verification_target_id=adaptive.verification_target_id,
            student_id=adaptive.student_id,
            diagnosis_id=adaptive.diagnosis_id,
            verification_id=adaptive.verification_id,
        )
        retry_difficulty = self.policy.retry_initial_difficulty(adaptive.current_difficulty)

        from app.repair.adaptive_service import AdaptiveRepairService

        adaptive_svc = AdaptiveRepairService(self.session)
        rec = adaptive_svc.find_repair_question(
            adaptive.student_id,
            adaptive.subject_id,
            target,
            desired_difficulty=retry_difficulty,
            excluded=exclusions,
        )
        return rec is not None

    def _build_read(
        self, decision: LearningFeedbackDecision, adaptive: AdaptiveRepairSession
    ) -> LearningFeedbackDecisionRead:
        # Build review info if schedule exists
        review_info: LearningFeedbackReviewInfo | None = None
        if decision.review_schedule_id is not None:
            sched = self.session.get(ReviewSchedule, decision.review_schedule_id)
            if sched is not None:
                review_info = LearningFeedbackReviewInfo(
                    schedule_id=sched.id,
                    next_review_at=sched.next_review_at,
                )

        # Build next learning info
        next_learning: LearningFeedbackNextLearningInfo | None = None
        if decision.action == LearningFeedbackAction.RETURN_TO_CURRENT_LEARNING:
            priorities = self.priority_service.get_priorities(adaptive.student_id, adaptive.subject_id)
            filtered = [
                p
                for p in priorities
                if not (
                    (adaptive.target_problem_type_id and p.problem_type_id == adaptive.target_problem_type_id)
                    or (adaptive.target_concept_id and p.concept_id == adaptive.target_concept_id)
                    or p.reason_code == PriorityReasonCode.VERIFIED_ROOT_CAUSE
                )
            ]
            current_lesson_p = next(
                (p for p in filtered if p.reason_code == PriorityReasonCode.CURRENT_LESSON), None
            )
            chosen_priority = current_lesson_p or (filtered[0] if filtered else None)

            recommended_q_info: LearningFeedbackQuestionInfo | None = None
            if decision.recommended_question_id is not None:
                question = self.session.scalar(
                    select(Question)
                    .options(selectinload(Question.options))
                    .where(Question.id == decision.recommended_question_id)
                )
                if question is not None:
                    recommended_q_info = LearningFeedbackQuestionInfo(
                        id=question.id,
                        content=question.content,
                        question_type=question.question_type,
                        difficulty=question.difficulty,
                        options=[
                            LearningFeedbackQuestionOptionInfo(
                                id=opt.id,
                                label=opt.label,
                                content=opt.content,
                                order_index=opt.order_index,
                            )
                            for opt in question.options
                        ],
                    )

            if chosen_priority is not None:
                next_learning = LearningFeedbackNextLearningInfo(
                    target_type=chosen_priority.target_type,
                    concept_id=chosen_priority.concept_id,
                    problem_type_id=chosen_priority.problem_type_id,
                    reason_code=chosen_priority.reason_code,
                    recommended_question_id=decision.recommended_question_id,
                    recommended_question=recommended_q_info,
                )

        return LearningFeedbackDecisionRead(
            id=decision.id,
            adaptive_repair_session_id=decision.adaptive_repair_session_id,
            action=decision.action,
            reason_code=decision.reason_code,
            repair_cycle_index=decision.repair_cycle_index,
            target=LearningFeedbackTargetInfo(
                type=decision.target_type,
                concept_id=decision.target_concept_id,
                problem_type_id=decision.target_problem_type_id,
                name=adaptive.target_name,
                code=adaptive.target_code,
            ),
            review=review_info,
            next_learning=next_learning,
            retry=LearningFeedbackRetryInfo(
                allowed=decision.retry_allowed,
                max_cycles=self.policy.max_cycles,
                current_cycle=decision.repair_cycle_index,
            ),
            created_at=decision.created_at,
        )
