from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.math_solutions.assignment_grading import require_pending_assignment_item
from app.math_solutions.grading_context import resolve_grading_context
from app.math_solutions.misconception_classifier import MisconceptionClassifier
from app.math_solutions.models import (
    EvaluationDecision,
    MathArtifact,
    SolutionAttempt,
    SolutionStep,
    StepEvaluation,
    StepRevision,
)
from app.math_solutions.rubric_evaluator import SolutionRubricEvaluator
from app.math_solutions.validator import DeterministicMathValidator


class MathEvaluatorService:
    """
    Orchestration service for the 4-Tier Step Evaluation Engine.
    Executes CAS verification, rubric mapping, and pedagogical misconception classification.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def evaluate_attempt(self, attempt_id: UUID, *, commit: bool = True) -> EvaluationDecision:
        attempt = self.session.get(SolutionAttempt, attempt_id)
        if not attempt:
            raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Solution attempt not found.")

        # Check existing decision
        existing_decision = self.session.scalar(
            select(EvaluationDecision).where(EvaluationDecision.attempt_id == attempt_id)
        )
        if existing_decision is not None:
            return existing_decision

        context = resolve_grading_context(self.session, attempt)
        if attempt.context_type == "CLASSROOM_ASSIGNMENT":
            require_pending_assignment_item(self.session, attempt)
        rubric = context.rubric
        validator = DeterministicMathValidator(target_function_latex=context.problem_content)
        if not validator.supports_polynomial_target:
            raise ApplicationError(
                409, "GRADING_TARGET_UNSUPPORTED",
                "The problem is outside the verified polynomial grading scope.",
            )
        classifier = MisconceptionClassifier(session=self.session)

        # Load active steps in order
        active_steps = self.session.scalars(
            select(SolutionStep)
            .where(SolutionStep.attempt_id == attempt_id, SolutionStep.is_deleted.is_(False))
            .order_by(SolutionStep.step_index.asc())
        ).all()
        if not active_steps:
            raise ApplicationError(409, "EMPTY_SOLUTION", "No active solution steps are available for grading.")

        step_validities_for_rubric = []
        evaluations_to_save: list[StepEvaluation] = []
        detected_misconceptions: list[str] = []
        sign_table_was_inverted = False

        for step in active_steps:
            # Get latest revision
            latest_revision = self.session.scalar(
                select(StepRevision)
                .where(StepRevision.step_id == step.id)
                .order_by(StepRevision.step_revision_number.desc())
            )
            if not latest_revision:
                raise ApplicationError(409, "STEP_REVISION_MISSING", "A solution step has no revision to grade.")

            # Check if revision has artifact
            artifact = self.session.scalar(
                select(MathArtifact).where(MathArtifact.step_revision_id == latest_revision.id)
            )
            artifact_payload = artifact.payload if artifact else None

            # 1. Tier 2: Deterministic validation
            val_result = validator.validate_step(
                step_type=step.step_type,
                content_latex=latest_revision.content_latex,
                explanation_text=latest_revision.explanation_text,
                artifact_payload=artifact_payload,
            )

            # Check if sign table was inverted
            if val_result.error_code == "SIGN_TABLE_QUADRATIC_RULE_INVERTED":
                sign_table_was_inverted = True

            # 2. Tier 4: Misconception Classification
            misconception_def_id = None
            if val_result.error_detected and val_result.error_code:
                classification = classifier.classify_error(
                    error_code=val_result.error_code,
                    step_type=step.step_type,
                    content_latex=latest_revision.content_latex,
                    explanation_text=latest_revision.explanation_text,
                    artifact_payload=artifact_payload,
                    sign_table_was_inverted=sign_table_was_inverted,
                )
                if classification:
                    detected_misconceptions.append(classification.code)
                    misconception_def_id = classification.definition_id

            # Prepare StepEvaluation record
            step_eval = StepEvaluation(
                id=uuid4(),
                step_revision_id=latest_revision.id,
                rubric_id=None,
                misconception_definition_id=misconception_def_id,
                evaluator_type="DETERMINISTIC_RULES",
                math_validity=val_result.validity.value,
                score=val_result.score,
                confidence=val_result.confidence,
                error_detected=val_result.error_detected,
                error_description=val_result.error_description,
                evidence_quote=val_result.evidence_quote,
                evaluated_at=datetime.now(timezone.utc),
            )
            evaluations_to_save.append(step_eval)

            step_validities_for_rubric.append({
                "step_index": step.step_index,
                "step_type": step.step_type,
                "validity": val_result.validity.value,
                "raw_score": val_result.score,
            })

        # An unresolved step is neither correct nor incorrect. It must not
        # produce a final score or learning evidence until it is reviewed.
        if any(item["validity"] in ("UNDETERMINED", "NEEDS_REVIEW") for item in step_validities_for_rubric):
            raise ApplicationError(
                409, "GRADING_REVIEW_REQUIRED",
                "At least one solution step requires review before a final score.",
            )

        # 3. Tier 3: Rubric Evaluation
        rubric_evaluator = SolutionRubricEvaluator(rubric=rubric)
        final_score, rubric_matches = rubric_evaluator.evaluate(step_validities_for_rubric)

        # A definitive score is only recorded when every step was verified.
        is_correct = final_score >= 0.85 and len(detected_misconceptions) == 0

        # Save all step evaluations
        for step_eval in evaluations_to_save:
            step_eval.rubric_id = rubric.id
            self.session.add(step_eval)

        # Create EvaluationDecision
        decision = EvaluationDecision(
            id=uuid4(),
            attempt_id=attempt.id,
            rubric_id=rubric.id,
            decision_source="AUTOMATED_CONSENSUS",
            final_score=final_score,
            is_correct=is_correct,
            confirmed_misconceptions=detected_misconceptions,
            learning_evidence_event_id=None,
            decided_by=None,
            decided_at=datetime.now(timezone.utc),
        )
        self.session.add(decision)

        # Update attempt status
        attempt.status = "EVALUATED"
        attempt.total_score = final_score
        attempt.is_correct = is_correct
        attempt.evaluated_at = decision.decided_at

        self.session.flush()

        # Evaluation, evidence, mastery and review schedule must be committed
        # atomically. Never persist a final decision without its evidence.
        from app.math_solutions.evidence_adapter import MathSolutionEvidenceAdapter

        if commit:
            try:
                MathSolutionEvidenceAdapter(self.session).emit_evidence_for_decision(decision.id)
                self.session.commit()
            except Exception:
                self.session.rollback()
                raise
        else:
            # The assignment submit transaction owns the commit and rollback.
            MathSolutionEvidenceAdapter(self.session).emit_evidence_for_decision(decision.id)
        return decision
