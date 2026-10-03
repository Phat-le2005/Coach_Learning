from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ApplicationError
from app.knowledge_gap.models import (
    RootCauseDiagnosis,
    RootCauseVerification,
    RootCauseVerificationOutcome,
    RootCauseVerificationStatus,
    RootCauseVerificationTarget,
)
from app.knowledge_gap.schemas import NextDiagnosticActionType
from app.knowledge_gap.target_resolver import VerifiedLearningTargetService
from app.mastery.evidence import MasteryAttemptEvidencePublisher
from app.practice.evaluation import AnswerEvaluationService
from app.practice.evidence import AttemptEvaluatedEvidence, AttemptEvidencePublisher
from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionConcept,
    PracticeSessionProblemType,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.questions.exposure import QuestionExposureService
from app.questions.models import Question, QuestionType
from app.recommendations.question_service import QuestionRecommendationService
from app.recommendations.schemas import PriorityReasonCode, QuestionRecommendationRead
from app.repair.adaptive_policy import AdaptiveRepairPolicy
from app.repair.models import (
    AdaptiveRepairDecision,
    AdaptiveRepairDecisionReason,
    AdaptiveRepairItem,
    AdaptiveRepairItemRole,
    AdaptiveRepairOutcome,
    AdaptiveRepairPhase,
    AdaptiveRepairSession,
    AdaptiveRepairStatus,
)
from app.repair.schemas import (
    AdaptiveRepairAnswerResult,
    AdaptiveRepairAnswerSubmit,
    AdaptiveRepairAttemptRead,
    AdaptiveRepairCurrentItemRead,
    AdaptiveRepairHistoryItemRead,
    AdaptiveRepairProgressRead,
    AdaptiveRepairQuestionOptionRead,
    AdaptiveRepairSessionRead,
    AdaptiveRepairTargetRead,
)
from app.students.models import StudentProfile
from app.users.models import User


AUTO_EVALUABLE_REPAIR_TYPES = frozenset(
    {QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE, QuestionType.SHORT_ANSWER}
)
COMPLETED_EVALUATION_STATUSES = frozenset(
    {EvaluationStatus.AUTO_EVALUATED, EvaluationStatus.EVALUATED}
)


class AdaptiveRepairService:
    """One-question-at-a-time repair for an empirically supported root cause."""

    def __init__(
        self,
        session: Session,
        *,
        policy: AdaptiveRepairPolicy | None = None,
        evaluator: AnswerEvaluationService | None = None,
        evidence_publisher: AttemptEvidencePublisher | None = None,
        recommendation_service: QuestionRecommendationService | None = None,
    ) -> None:
        self.session = session
        self.policy = policy or AdaptiveRepairPolicy()
        self.evaluator = evaluator or AnswerEvaluationService()
        self.evidence_publisher = evidence_publisher or MasteryAttemptEvidencePublisher()
        self.recommendations = recommendation_service or QuestionRecommendationService(session)
        self.exposure = QuestionExposureService(session)

    def start(self, current_user: User, diagnosis_id: UUID) -> AdaptiveRepairSessionRead:
        student = self._student_for_user(current_user.id)
        existing = self.session.scalar(
            select(AdaptiveRepairSession).where(
                AdaptiveRepairSession.student_id == student.id,
                AdaptiveRepairSession.diagnosis_id == diagnosis_id,
                AdaptiveRepairSession.repair_cycle_index == 1,
            )
        )
        if existing is not None:
            return self._build_read(existing)

        action = VerifiedLearningTargetService(self.session).resolve_next_action(
            student.id, diagnosis_id
        )
        if action.action != NextDiagnosticActionType.PRACTICE_REPAIR:
            raise ApplicationError(
                409,
                f"ADAPTIVE_REPAIR_{action.action.value}",
                f"Adaptive repair cannot start while the diagnostic next action is {action.action.value}.",
            )

        diagnosis, verification, target = self._supported_context(student.id, diagnosis_id)
        target = self.session.scalar(
            select(RootCauseVerificationTarget)
            .where(RootCauseVerificationTarget.id == target.id)
            .with_for_update()
        )
        if target is None:
            raise ApplicationError(409, "ADAPTIVE_REPAIR_TARGET_MISSING", "Verified target no longer exists.")
        concurrent_existing = self.session.scalar(
            select(AdaptiveRepairSession).where(
                AdaptiveRepairSession.verification_target_id == target.id,
                AdaptiveRepairSession.repair_cycle_index == 1,
            )
        )
        if concurrent_existing is not None:
            return self._build_read(concurrent_existing)
        initial = self.policy.initial_difficulty(target.target_type, target.average_score)
        phase = self.policy.initial_phase(target.average_score)
        excluded = self._verification_exclusions(diagnosis, verification)
        recommendation = self._recommend(
            student.id,
            diagnosis.subject_id,
            target,
            desired_difficulty=initial,
            excluded=excluded,
        )
        if recommendation is None:
            raise ApplicationError(
                409,
                "ADAPTIVE_REPAIR_NO_CANONICAL_QUESTION",
                "No fresh auto-evaluable canonical question is available for the verified target.",
            )

        from sqlalchemy.exc import IntegrityError

        try:
            with self.session.begin_nested():
                practice_session = PracticeSession(
                    student_id=student.id,
                    subject_id=diagnosis.subject_id,
                    session_type=PracticeSessionType.REPAIR,
                    status=PracticeSessionStatus.ACTIVE,
                )
                self.session.add(practice_session)
                self.session.flush()
                if target.target_concept_id is not None:
                    self.session.add(
                        PracticeSessionConcept(
                            practice_session_id=practice_session.id,
                            concept_id=target.target_concept_id,
                        )
                    )
                if target.target_problem_type_id is not None:
                    self.session.add(
                        PracticeSessionProblemType(
                            practice_session_id=practice_session.id,
                            problem_type_id=target.target_problem_type_id,
                        )
                    )

                adaptive = AdaptiveRepairSession(
                    practice_session_id=practice_session.id,
                    student_id=student.id,
                    subject_id=diagnosis.subject_id,
                    diagnosis_id=diagnosis.id,
                    verification_id=verification.id,
                    verification_target_id=target.id,
                    target_type=target.target_type,
                    target_concept_id=target.target_concept_id,
                    target_problem_type_id=target.target_problem_type_id,
                    misconception_definition_id=target.misconception_definition_id,
                    target_name=action.verified_target.target_name if action.verified_target else None,
                    target_code=action.verified_target.target_code if action.verified_target else None,
                    repair_cycle_index=1,
                    phase=phase,
                    initial_difficulty=initial,
                    current_difficulty=initial,
                    target_exit_difficulty=self.policy.exit_difficulty(target.target_type),
                    verification_average_score=target.average_score,
                    max_questions=self.policy.max_questions,
                )
                self.session.add(adaptive)
                self.session.flush()
                self._persist_item(adaptive, recommendation.question_id, phase, initial)
            self.session.commit()
            return self._build_read(adaptive)
        except IntegrityError:
            concurrent_existing = self.session.scalar(
                select(AdaptiveRepairSession).where(
                    AdaptiveRepairSession.verification_target_id == target.id,
                    AdaptiveRepairSession.repair_cycle_index == 1,
                )
            )
            if concurrent_existing is not None:
                return self._build_read(concurrent_existing)
            raise

    def get(self, current_user: User, adaptive_session_id: UUID) -> AdaptiveRepairSessionRead:
        student = self._student_for_user(current_user.id)
        adaptive = self._get_session(adaptive_session_id)
        self._authorize(adaptive, student.id)
        return self._build_read(adaptive)

    def answer_current(
        self,
        current_user: User,
        adaptive_session_id: UUID,
        data: AdaptiveRepairAnswerSubmit,
    ) -> AdaptiveRepairAnswerResult:
        student = self._student_for_user(current_user.id)
        adaptive = self.session.scalar(
            select(AdaptiveRepairSession)
            .where(AdaptiveRepairSession.id == adaptive_session_id)
            .with_for_update()
        )
        if adaptive is None:
            raise ApplicationError(404, "ADAPTIVE_REPAIR_NOT_FOUND", "Adaptive repair session was not found.")
        self._authorize(adaptive, student.id)
        if adaptive.status != AdaptiveRepairStatus.ACTIVE:
            raise ApplicationError(409, "ADAPTIVE_REPAIR_NOT_ACTIVE", "Adaptive repair session is complete.")

        submitted_item = self.session.get(AdaptiveRepairItem, data.item_id)
        if (
            submitted_item is not None
            and submitted_item.adaptive_repair_session_id == adaptive.id
            and submitted_item.attempt_id is not None
        ):
            raise ApplicationError(409, "REPAIR_ITEM_ALREADY_ATTEMPTED", "This repair item was already attempted.")

        pending = list(
            self.session.scalars(
                select(AdaptiveRepairItem)
                .where(
                    AdaptiveRepairItem.adaptive_repair_session_id == adaptive.id,
                    AdaptiveRepairItem.attempt_id.is_(None),
                )
                .order_by(AdaptiveRepairItem.order_index)
            )
        )
        if len(pending) != 1:
            raise ApplicationError(409, "ADAPTIVE_REPAIR_PENDING_ITEM_INVALID", "Adaptive repair must have exactly one current item.")
        item = pending[0]
        if item.id != data.item_id:
            raise ApplicationError(409, "REPAIR_ITEM_MISMATCH", "The submitted item is not the frozen current item.")
        if item.attempt_id is not None:
            raise ApplicationError(409, "REPAIR_ITEM_ALREADY_ATTEMPTED", "This repair item was already attempted.")

        question = self.session.scalar(
            select(Question).options(
                selectinload(Question.options),
                selectinload(Question.concept_links),
                selectinload(Question.problem_type_links),
                selectinload(Question.learning_outcome_links),
            ).where(Question.id == item.question_id)
        )
        if question is None:
            raise ApplicationError(404, "REPAIR_QUESTION_NOT_FOUND", "Repair question was not found.")
        if question.question_type not in AUTO_EVALUABLE_REPAIR_TYPES:
            raise ApplicationError(409, "REPAIR_QUESTION_NOT_AUTO_EVALUABLE", "Current repair question is not auto-evaluable.")

        evaluation = self.evaluator.evaluate(question, data.student_answer)
        if (
            evaluation.status not in COMPLETED_EVALUATION_STATUSES
            or evaluation.is_correct is None
            or evaluation.score is None
        ):
            raise ApplicationError(409, "REPAIR_ANSWER_NOT_EVALUATED", "Repair answer could not be evaluated deterministically.")

        now = datetime.now(timezone.utc)
        phase_before = adaptive.phase
        difficulty_before = adaptive.current_difficulty
        attempt = QuestionAttempt(
            practice_session_id=adaptive.practice_session_id,
            student_id=student.id,
            question_id=question.id,
            student_answer=data.student_answer,
            is_correct=evaluation.is_correct,
            score=evaluation.score,
            response_time_seconds=data.response_time_seconds,
            hint_count=data.hint_count,
            attempt_number=adaptive.attempted_count + 1,
            evaluation_status=evaluation.status,
        )
        self.session.add(attempt)
        self.session.flush()

        self.evidence_publisher.publish(
            self._make_evidence(adaptive, attempt, question, now), self.session
        )

        adaptive.attempted_count += 1
        if evaluation.is_correct:
            adaptive.correct_count += 1
            adaptive.consecutive_correct += 1
            adaptive.consecutive_wrong = 0
        else:
            adaptive.consecutive_wrong += 1
            adaptive.consecutive_correct = 0
        adaptive.current_difficulty = self.policy.adjusted_difficulty(
            adaptive.current_difficulty,
            is_correct=evaluation.is_correct,
            hint_count=data.hint_count,
        )
        item.attempt_id = attempt.id
        item.answered_at = now
        item.difficulty_after = adaptive.current_difficulty

        recent_scores = self._recent_scores(adaptive.id)
        reason = self._transition(
            adaptive,
            phase_before=phase_before,
            is_correct=evaluation.is_correct,
            hint_count=data.hint_count,
            recent_scores=recent_scores,
        )

        if adaptive.outcome == AdaptiveRepairOutcome.PENDING:
            if adaptive.attempted_count >= adaptive.max_questions:
                self._complete(adaptive, AdaptiveRepairOutcome.NEEDS_MORE_PRACTICE, now)
                reason = AdaptiveRepairDecisionReason.MAX_QUESTIONS_REACHED
            else:
                excluded = self._all_exclusions(adaptive)
                desired = (
                    adaptive.target_exit_difficulty
                    if adaptive.phase == AdaptiveRepairPhase.FINAL_RECHECK
                    else adaptive.current_difficulty
                )
                target = self.session.get(RootCauseVerificationTarget, adaptive.verification_target_id)
                recommendation = None if target is None else self._recommend(
                    adaptive.student_id,
                    adaptive.subject_id,
                    target,
                    desired_difficulty=desired,
                    excluded=excluded,
                )
                if recommendation is None:
                    self._complete(adaptive, AdaptiveRepairOutcome.BANK_EXHAUSTED, now)
                    reason = AdaptiveRepairDecisionReason.QUESTION_BANK_EXHAUSTED
                else:
                    self._persist_item(adaptive, recommendation.question_id, adaptive.phase, desired)

        decision = AdaptiveRepairDecision(
            adaptive_repair_session_id=adaptive.id,
            adaptive_repair_item_id=item.id,
            decision_index=adaptive.attempted_count,
            phase_before=phase_before,
            phase_after=adaptive.phase,
            difficulty_before=difficulty_before,
            difficulty_after=adaptive.current_difficulty,
            reason_code=reason,
        )
        self.session.add(decision)
        self.session.commit()

        result = AdaptiveRepairAnswerResult(
            attempt=AdaptiveRepairAttemptRead(
                id=attempt.id,
                item_id=item.id,
                question_id=question.id,
                is_correct=evaluation.is_correct,
                score=evaluation.score,
                evaluation_status=evaluation.status,
            ),
            previous_phase=phase_before,
            next_phase=adaptive.phase,
            difficulty_before=difficulty_before,
            difficulty_after=adaptive.current_difficulty,
            reason_code=reason,
            session=self._build_read(adaptive),
        )
        return result

    def _transition(
        self,
        adaptive: AdaptiveRepairSession,
        *,
        phase_before: AdaptiveRepairPhase,
        is_correct: bool,
        hint_count: int,
        recent_scores: list[float],
    ) -> AdaptiveRepairDecisionReason:
        if phase_before == AdaptiveRepairPhase.FINAL_RECHECK:
            if self.policy.can_resolve(
                attempted_count=adaptive.attempted_count,
                recent_scores=recent_scores,
                final_correct=is_correct,
            ):
                self._complete(adaptive, AdaptiveRepairOutcome.RESOLVED, datetime.now(timezone.utc))
                return AdaptiveRepairDecisionReason.FINAL_RECHECK_PASSED
            adaptive.phase = (
                AdaptiveRepairPhase.GUIDED
                if adaptive.consecutive_wrong >= 2
                else AdaptiveRepairPhase.TARGET_PRACTICE
            )
            return AdaptiveRepairDecisionReason.FINAL_RECHECK_FAILED

        if phase_before == AdaptiveRepairPhase.FOUNDATION:
            adaptive.phase = AdaptiveRepairPhase.TARGET_PRACTICE if is_correct else AdaptiveRepairPhase.GUIDED
        elif phase_before == AdaptiveRepairPhase.GUIDED:
            if is_correct:
                adaptive.phase = AdaptiveRepairPhase.TARGET_PRACTICE
                return AdaptiveRepairDecisionReason.RECOVERED_EXIT_GUIDED
        elif not is_correct and adaptive.consecutive_wrong >= 2:
            adaptive.phase = AdaptiveRepairPhase.GUIDED
            return AdaptiveRepairDecisionReason.REPEATED_WRONG_ENTER_GUIDED

        if is_correct and self.policy.ready_for_final(
            attempted_count=adaptive.attempted_count,
            consecutive_correct=adaptive.consecutive_correct,
            current_difficulty=adaptive.current_difficulty,
            target_exit_difficulty=adaptive.target_exit_difficulty,
            recent_scores=recent_scores,
        ):
            adaptive.phase = AdaptiveRepairPhase.FINAL_RECHECK
            return AdaptiveRepairDecisionReason.READY_FOR_FINAL_RECHECK
        if is_correct:
            return (
                AdaptiveRepairDecisionReason.CORRECT_WITH_HINT_SMALL_ADVANCE
                if hint_count > 0
                else AdaptiveRepairDecisionReason.CORRECT_ADVANCE_DIFFICULTY
            )
        return AdaptiveRepairDecisionReason.WRONG_REDUCE_DIFFICULTY

    def _supported_context(
        self, student_id: UUID, diagnosis_id: UUID
    ) -> tuple[RootCauseDiagnosis, RootCauseVerification, RootCauseVerificationTarget]:
        diagnosis = self.session.scalar(
            select(RootCauseDiagnosis)
            .options(
                selectinload(RootCauseDiagnosis.verifications)
                .selectinload(RootCauseVerification.targets)
                .selectinload(RootCauseVerificationTarget.items)
            )
            .where(RootCauseDiagnosis.id == diagnosis_id)
        )
        if diagnosis is None:
            raise ApplicationError(404, "DIAGNOSIS_NOT_FOUND", "Diagnosis not found.")
        if diagnosis.student_id != student_id:
            raise ApplicationError(403, "DIAGNOSIS_ACCESS_DENIED", "Access denied to diagnosis.")
        if not diagnosis.verifications:
            raise ApplicationError(409, "ADAPTIVE_REPAIR_VERIFY_ROOT_CAUSE", "Diagnosis is not verified.")
        verification = sorted(diagnosis.verifications, key=lambda row: row.created_at, reverse=True)[0]
        if verification.status != RootCauseVerificationStatus.COMPLETED:
            raise ApplicationError(409, "ADAPTIVE_REPAIR_VERIFY_ROOT_CAUSE", "Root-cause verification is not complete.")
        supported = sorted(
            (target for target in verification.targets if target.outcome == RootCauseVerificationOutcome.SUPPORTED),
            key=lambda row: row.priority_order,
        )
        if not supported:
            raise ApplicationError(409, "ADAPTIVE_REPAIR_COLLECT_MORE_EVIDENCE", "Verification has no supported target.")
        return diagnosis, verification, supported[0]

    def find_repair_question(
        self,
        student_id: UUID,
        subject_id: UUID,
        target: RootCauseVerificationTarget,
        *,
        desired_difficulty: float,
        excluded: set[UUID],
    ) -> QuestionRecommendationRead | None:
        return self._recommend(
            student_id,
            subject_id,
            target,
            desired_difficulty=desired_difficulty,
            excluded=excluded,
        )

    def _recommend(
        self,
        student_id: UUID,
        subject_id: UUID,
        target: RootCauseVerificationTarget,
        *,
        desired_difficulty: float,
        excluded: set[UUID],
    ) -> QuestionRecommendationRead | None:
        effective_exclusions = set(excluded)
        while True:
            recommendation = self.recommendations.recommend(
                student_id,
                subject_id,
                target_problem_type_id=target.target_problem_type_id,
                target_concept_id=target.target_concept_id,
                desired_difficulty=desired_difficulty,
                exclude_question_ids=effective_exclusions,
                reason_code_override=PriorityReasonCode.VERIFIED_ROOT_CAUSE,
                isolation_boost=True,
                allowed_question_types=AUTO_EVALUABLE_REPAIR_TYPES,
            )
            if recommendation is None:
                return None
            question = self.session.scalar(
                select(Question)
                .options(selectinload(Question.options))
                .where(Question.id == recommendation.question_id)
            )
            if question is not None and self._is_auto_evaluable(question):
                return recommendation
            effective_exclusions.add(recommendation.question_id)

    def _is_auto_evaluable(self, question: Question) -> bool:
        expected = self.evaluator.normalize(question.correct_answer or "")
        if not expected or question.question_type not in AUTO_EVALUABLE_REPAIR_TYPES:
            return False
        if question.question_type == QuestionType.TRUE_FALSE:
            return expected in {"true", "false"}
        if question.question_type == QuestionType.MULTIPLE_CHOICE:
            labels = {self.evaluator.normalize(option.label) for option in question.options}
            return expected in labels
        return True

    def _persist_item(
        self,
        adaptive: AdaptiveRepairSession,
        question_id: UUID,
        phase: AdaptiveRepairPhase,
        desired_difficulty: float,
    ) -> AdaptiveRepairItem:
        role = {
            AdaptiveRepairPhase.FOUNDATION: AdaptiveRepairItemRole.FOUNDATION,
            AdaptiveRepairPhase.GUIDED: AdaptiveRepairItemRole.GUIDED,
            AdaptiveRepairPhase.TARGET_PRACTICE: AdaptiveRepairItemRole.PRACTICE,
            AdaptiveRepairPhase.FINAL_RECHECK: AdaptiveRepairItemRole.FINAL_RECHECK,
        }[phase]
        item = AdaptiveRepairItem(
            adaptive_repair_session_id=adaptive.id,
            question_id=question_id,
            order_index=adaptive.attempted_count + 1,
            role=role,
            desired_difficulty=desired_difficulty,
            selection_score=None,
            selection_reason="VERIFIED_TARGET_NEAREST_DIFFICULTY",
            difficulty_before=adaptive.current_difficulty,
        )
        self.session.add(item)
        self.session.flush()
        return item

    def _verification_exclusions(
        self, diagnosis: RootCauseDiagnosis, verification: RootCauseVerification
    ) -> set[UUID]:
        excluded = {
            item.question_id
            for target in verification.targets
            for item in target.items
        }
        source_question = self.exposure.get_diagnosis_source_question_id(diagnosis)
        if source_question is not None:
            excluded.add(source_question)
        return excluded

    def _all_exclusions(self, adaptive: AdaptiveRepairSession) -> set[UUID]:
        from app.repair.lineage import RepairLineageExposureService
        lineage_svc = RepairLineageExposureService(self.session)
        return lineage_svc.get_lineage_excluded_question_ids(
            verification_target_id=adaptive.verification_target_id,
            student_id=adaptive.student_id,
            diagnosis_id=adaptive.diagnosis_id,
            verification_id=adaptive.verification_id,
        )

    def _recent_scores(self, adaptive_session_id: UUID) -> list[float]:
        previous = list(
            self.session.scalars(
                select(QuestionAttempt.score)
                .join(AdaptiveRepairItem, AdaptiveRepairItem.attempt_id == QuestionAttempt.id)
                .where(
                    AdaptiveRepairItem.adaptive_repair_session_id == adaptive_session_id,
                    QuestionAttempt.score.is_not(None),
                )
                .order_by(AdaptiveRepairItem.order_index)
            )
        )
        # The current item already points to the flushed attempt. Avoid appending twice.
        return [float(score) for score in previous if score is not None]

    def _make_evidence(
        self,
        adaptive: AdaptiveRepairSession,
        attempt: QuestionAttempt,
        question: Question,
        occurred_at: datetime,
    ) -> AttemptEvaluatedEvidence:
        return AttemptEvaluatedEvidence(
            attempt_id=attempt.id,
            practice_session_id=adaptive.practice_session_id,
            student_id=adaptive.student_id,
            question_id=question.id,
            subject_id=adaptive.subject_id,
            is_correct=bool(attempt.is_correct),
            score=float(attempt.score),
            problem_type_ids=tuple(link.problem_type_id for link in question.problem_type_links),
            concept_ids=tuple(link.concept_id for link in question.concept_links),
            learning_outcome_ids=tuple(link.learning_outcome_id for link in question.learning_outcome_links),
            occurred_at=occurred_at,
            metadata={
                "learning_context": "ADAPTIVE_ROOT_CAUSE_REPAIR",
                "adaptive_repair_session_id": str(adaptive.id),
                "root_cause_diagnosis_id": str(adaptive.diagnosis_id),
                "verification_target_id": str(adaptive.verification_target_id),
                "suppress_root_cause_rediagnosis": True,
            },
        )

    def _complete(
        self,
        adaptive: AdaptiveRepairSession,
        outcome: AdaptiveRepairOutcome,
        completed_at: datetime,
    ) -> None:
        adaptive.status = AdaptiveRepairStatus.COMPLETED
        adaptive.outcome = outcome
        adaptive.completed_at = completed_at
        practice_session = self.session.get(PracticeSession, adaptive.practice_session_id)
        if practice_session is None:
            raise RuntimeError("Adaptive repair references a missing practice session")
        practice_session.status = PracticeSessionStatus.COMPLETED
        practice_session.completed_at = completed_at

        self._try_resolve_feedback_isolated(adaptive)

    def _try_resolve_feedback_isolated(self, adaptive: AdaptiveRepairSession) -> None:
        try:
            with self.session.begin_nested():
                from app.learning.feedback_service import LearningFeedbackService

                LearningFeedbackService(self.session).resolve_feedback(adaptive.id, commit=False)
        except Exception:
            # Failure in feedback generation must NEVER rollback repair attempt/mastery/session state
            pass

    def retry(self, current_user: User, adaptive_session_id: UUID) -> AdaptiveRepairSessionRead:
        student = self._student_for_user(current_user.id)
        previous = self._get_session(adaptive_session_id)
        self._authorize(previous, student.id)
        if previous.status != AdaptiveRepairStatus.COMPLETED:
            raise ApplicationError(
                409,
                "ADAPTIVE_REPAIR_NOT_COMPLETED",
                "Previous adaptive repair session must be completed before retrying.",
            )

        from app.learning.feedback_models import LearningFeedbackAction
        from app.learning.feedback_policy import LearningFeedbackPolicy
        from app.learning.feedback_service import LearningFeedbackService

        feedback_svc = LearningFeedbackService(self.session)
        feedback = feedback_svc.resolve_feedback(previous.id, commit=False)
        if feedback.action != LearningFeedbackAction.RETRY_REPAIR or not feedback.retry.allowed:
            raise ApplicationError(
                409,
                "REPAIR_RETRY_NOT_ALLOWED",
                "Retry is not allowed for this adaptive repair session.",
            )

        fb_policy = LearningFeedbackPolicy()
        next_cycle = previous.repair_cycle_index + 1
        if next_cycle > fb_policy.max_cycles:
            raise ApplicationError(
                409,
                "REPAIR_RETRY_NOT_ALLOWED",
                "Maximum adaptive repair retry cycles reached.",
            )

        existing_retry = self.session.scalar(
            select(AdaptiveRepairSession).where(
                AdaptiveRepairSession.verification_target_id == previous.verification_target_id,
                AdaptiveRepairSession.repair_cycle_index == next_cycle,
            )
        )
        if existing_retry is not None:
            return self._build_read(existing_retry)

        target = self.session.get(RootCauseVerificationTarget, previous.verification_target_id)
        if target is None:
            raise ApplicationError(409, "ADAPTIVE_REPAIR_TARGET_MISSING", "Verified target no longer exists.")

        retry_initial = fb_policy.retry_initial_difficulty(previous.current_difficulty)
        phase = (
            AdaptiveRepairPhase.TARGET_PRACTICE
            if retry_initial > 0.40
            else AdaptiveRepairPhase.FOUNDATION
        )

        from app.repair.lineage import RepairLineageExposureService

        lineage_svc = RepairLineageExposureService(self.session)
        excluded = lineage_svc.get_lineage_excluded_question_ids(
            verification_target_id=previous.verification_target_id,
            student_id=student.id,
            diagnosis_id=previous.diagnosis_id,
            verification_id=previous.verification_id,
        )

        recommendation = self.find_repair_question(
            student.id,
            previous.subject_id,
            target,
            desired_difficulty=retry_initial,
            excluded=excluded,
        )
        if recommendation is None:
            raise ApplicationError(
                409,
                "ADAPTIVE_REPAIR_NO_CANONICAL_QUESTION",
                "No fresh auto-evaluable canonical question is available for retry.",
            )

        from sqlalchemy.exc import IntegrityError

        try:
            with self.session.begin_nested():
                practice_session = PracticeSession(
                    student_id=student.id,
                    subject_id=previous.subject_id,
                    session_type=PracticeSessionType.REPAIR,
                    status=PracticeSessionStatus.ACTIVE,
                )
                self.session.add(practice_session)
                self.session.flush()
                if target.target_concept_id is not None:
                    self.session.add(
                        PracticeSessionConcept(
                            practice_session_id=practice_session.id,
                            concept_id=target.target_concept_id,
                        )
                    )
                if target.target_problem_type_id is not None:
                    self.session.add(
                        PracticeSessionProblemType(
                            practice_session_id=practice_session.id,
                            problem_type_id=target.target_problem_type_id,
                        )
                    )

                adaptive_retry = AdaptiveRepairSession(
                    practice_session_id=practice_session.id,
                    student_id=student.id,
                    subject_id=previous.subject_id,
                    diagnosis_id=previous.diagnosis_id,
                    verification_id=previous.verification_id,
                    verification_target_id=target.id,
                    target_type=target.target_type,
                    target_concept_id=target.target_concept_id,
                    target_problem_type_id=target.target_problem_type_id,
                    misconception_definition_id=target.misconception_definition_id,
                    target_name=previous.target_name,
                    target_code=previous.target_code,
                    repair_cycle_index=next_cycle,
                    previous_adaptive_repair_session_id=previous.id,
                    phase=phase,
                    initial_difficulty=retry_initial,
                    current_difficulty=retry_initial,
                    target_exit_difficulty=self.policy.exit_difficulty(target.target_type),
                    verification_average_score=target.average_score,
                    max_questions=self.policy.max_questions,
                )
                self.session.add(adaptive_retry)
                self.session.flush()
                self._persist_item(adaptive_retry, recommendation.question_id, phase, retry_initial)
            self.session.commit()
            return self._build_read(adaptive_retry)
        except IntegrityError:
            existing_retry = self.session.scalar(
                select(AdaptiveRepairSession).where(
                    AdaptiveRepairSession.verification_target_id == previous.verification_target_id,
                    AdaptiveRepairSession.repair_cycle_index == next_cycle,
                )
            )
            if existing_retry is not None:
                return self._build_read(existing_retry)
            raise

    def _get_session(self, adaptive_session_id: UUID) -> AdaptiveRepairSession:
        adaptive = self.session.get(AdaptiveRepairSession, adaptive_session_id)
        if adaptive is None:
            raise ApplicationError(404, "ADAPTIVE_REPAIR_NOT_FOUND", "Adaptive repair session was not found.")
        return adaptive

    @staticmethod
    def _authorize(adaptive: AdaptiveRepairSession, student_id: UUID) -> None:
        if adaptive.student_id != student_id:
            raise ApplicationError(403, "ADAPTIVE_REPAIR_ACCESS_DENIED", "Access denied to adaptive repair session.")

    def _student_for_user(self, user_id: UUID) -> StudentProfile:
        student = self.session.scalar(select(StudentProfile).where(StudentProfile.user_id == user_id))
        if student is None:
            raise ApplicationError(404, "STUDENT_PROFILE_NOT_FOUND", "Student profile was not found.")
        return student

    def _build_read(self, adaptive: AdaptiveRepairSession) -> AdaptiveRepairSessionRead:
        items = list(
            self.session.scalars(
                select(AdaptiveRepairItem)
                .options(selectinload(AdaptiveRepairItem.decision))
                .where(AdaptiveRepairItem.adaptive_repair_session_id == adaptive.id)
                .order_by(AdaptiveRepairItem.order_index)
            )
        )
        question_ids = {item.question_id for item in items}
        questions = {
            question.id: question
            for question in self.session.scalars(
                select(Question).options(selectinload(Question.options)).where(Question.id.in_(question_ids))
            )
        } if question_ids else {}
        attempt_ids = {item.attempt_id for item in items if item.attempt_id is not None}
        attempts = {
            attempt.id: attempt
            for attempt in self.session.scalars(select(QuestionAttempt).where(QuestionAttempt.id.in_(attempt_ids)))
        } if attempt_ids else {}

        current: AdaptiveRepairCurrentItemRead | None = None
        history: list[AdaptiveRepairHistoryItemRead] = []
        for item in items:
            question = questions.get(item.question_id)
            if question is None:
                continue
            if item.attempt_id is None:
                current = AdaptiveRepairCurrentItemRead(
                    id=item.id,
                    order_index=item.order_index,
                    role=item.role,
                    question_id=question.id,
                    question_content=question.content,
                    question_type=question.question_type,
                    question_difficulty=question.difficulty,
                    desired_difficulty=item.desired_difficulty,
                    options=[
                        AdaptiveRepairQuestionOptionRead(
                            id=option.id,
                            label=option.label,
                            content=option.content,
                            order_index=option.order_index,
                        )
                        for option in question.options
                    ],
                    hints_allowed=item.role == AdaptiveRepairItemRole.GUIDED,
                )
                continue
            attempt = attempts.get(item.attempt_id)
            decision = item.decision
            if attempt is None or decision is None or attempt.is_correct is None or attempt.score is None or item.difficulty_after is None:
                continue
            history.append(
                AdaptiveRepairHistoryItemRead(
                    id=item.id,
                    order_index=item.order_index,
                    role=item.role,
                    question_id=question.id,
                    question_difficulty=question.difficulty,
                    desired_difficulty=item.desired_difficulty,
                    is_correct=attempt.is_correct,
                    score=attempt.score,
                    hint_count=attempt.hint_count,
                    difficulty_before=item.difficulty_before,
                    difficulty_after=item.difficulty_after,
                    phase_before=decision.phase_before,
                    phase_after=decision.phase_after,
                    reason_code=decision.reason_code,
                    explanation=question.explanation,
                )
            )

        return AdaptiveRepairSessionRead(
            id=adaptive.id,
            practice_session_id=adaptive.practice_session_id,
            diagnosis_id=adaptive.diagnosis_id,
            verification_id=adaptive.verification_id,
            verification_target_id=adaptive.verification_target_id,
            repair_cycle_index=adaptive.repair_cycle_index,
            previous_adaptive_repair_session_id=adaptive.previous_adaptive_repair_session_id,
            target=AdaptiveRepairTargetRead(
                target_type=adaptive.target_type,
                concept_id=adaptive.target_concept_id,
                problem_type_id=adaptive.target_problem_type_id,
                misconception_definition_id=adaptive.misconception_definition_id,
                name=adaptive.target_name,
                code=adaptive.target_code,
            ),
            status=adaptive.status,
            phase=adaptive.phase,
            outcome=adaptive.outcome,
            initial_difficulty=adaptive.initial_difficulty,
            current_difficulty=adaptive.current_difficulty,
            target_exit_difficulty=adaptive.target_exit_difficulty,
            progress=AdaptiveRepairProgressRead(
                attempted_count=adaptive.attempted_count,
                correct_count=adaptive.correct_count,
                consecutive_correct=adaptive.consecutive_correct,
                consecutive_wrong=adaptive.consecutive_wrong,
                max_questions=adaptive.max_questions,
            ),
            current_item=current,
            history=history,
            started_at=adaptive.started_at,
            completed_at=adaptive.completed_at,
        )
