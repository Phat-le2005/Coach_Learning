from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.dependencies import create_ai_provider
from app.ai.gateway import AIGateway
from app.ai.prompt_registry import PromptRegistry, default_prompt_registry
from app.ai.types import AIMessage, AIRole, AITaskType
from app.concepts.models import Concept
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.curriculum.models import LearningOutcome, ProblemType
from app.mastery.evidence import MasteryAttemptEvidencePublisher
from app.practice.evidence import AttemptEvaluatedEvidence, AttemptEvidencePublisher
from app.practice.models import EvaluationStatus, PracticeSession, QuestionAttempt
from app.practice.open_response_schemas import OpenResponseEvaluationOutput
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionLearningOutcome,
    QuestionProblemType,
    QuestionType,
)

logger = logging.getLogger(__name__)


class AIOpenResponseEvaluationService:
    """Service to evaluate student open-ended responses using AI, with strict academic

    guardrails, Pydantic validation, and deterministic Mastery Engine delegation.
    """

    DEFAULT_CONFIDENCE_THRESHOLD: float = 0.70

    def __init__(
        self,
        session: Session,
        gateway: AIGateway | None = None,
        evidence_publisher: AttemptEvidencePublisher | None = None,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self.session = session
        if gateway is not None:
            self.gateway = gateway
        else:
            settings = Settings()
            provider = create_ai_provider(settings)
            self.gateway = AIGateway(provider=provider, settings=settings)
        self.evidence_publisher = (
            evidence_publisher
            if evidence_publisher is not None
            else MasteryAttemptEvidencePublisher()
        )
        self.prompt_registry = prompt_registry or default_prompt_registry

    async def evaluate_attempt(
        self,
        attempt_id: UUID,
        *,
        rubric: str | None = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        commit: bool = True,
    ) -> QuestionAttempt:
        """Evaluate a single open response attempt using AI.

        Enforces:
        - Only attempts with status `NEEDS_EVALUATION` are processed.
        - MCQ and TRUE_FALSE questions are strictly blocked from AI evaluation.
        - Academic whitelist verification (concepts, problem types, learning outcomes).
        - If confidence < confidence_threshold, flags as `NEEDS_TEACHER_REVIEW` without updating mastery.
        - If confidence >= confidence_threshold, flags as `EVALUATED` and triggers Mastery Engine.
        - AI never directly modifies mastery tables.
        """
        attempt = self.session.get(QuestionAttempt, attempt_id)
        if attempt is None:
            raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Question attempt not found.")

        # 1. State validation: Only NEEDS_EVALUATION is permitted
        if attempt.evaluation_status != EvaluationStatus.NEEDS_EVALUATION:
            raise ApplicationError(
                400,
                "INVALID_EVALUATION_STATUS",
                f"Only attempts with status NEEDS_EVALUATION can be evaluated. Current status: {attempt.evaluation_status.value}",
            )

        question = self.session.get(Question, attempt.question_id)
        if question is None:
            raise ApplicationError(404, "QUESTION_NOT_FOUND", "Associated question not found.")

        # 2. Format validation: MCQ/TRUE_FALSE are strictly prohibited
        if question.question_type in {
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.TRUE_FALSE,
        }:
            raise ApplicationError(
                400,
                "OBJECTIVE_QUESTION_AI_BLOCKED",
                f"AI evaluation is not permitted for {question.question_type.value} questions.",
            )

        if question.question_type != QuestionType.OPEN_RESPONSE:
            raise ApplicationError(
                400,
                "UNSUPPORTED_QUESTION_TYPE",
                f"Only OPEN_RESPONSE questions can be evaluated. Found: {question.question_type.value}",
            )

        # 3. Retrieve curriculum metadata and construct strict whitelists
        concepts = self.session.scalars(
            select(Concept)
            .join(QuestionConcept, QuestionConcept.concept_id == Concept.id)
            .where(QuestionConcept.question_id == question.id)
        ).all()
        allowed_concept_codes = {c.code for c in concepts}
        concepts_text = (
            "\n".join(f"- {c.code}: {c.name}" for c in concepts)
            if concepts
            else "(No concepts mapped to this question)"
        )

        problem_types = self.session.scalars(
            select(ProblemType)
            .join(
                QuestionProblemType,
                QuestionProblemType.problem_type_id == ProblemType.id,
            )
            .where(QuestionProblemType.question_id == question.id)
        ).all()
        allowed_problem_type_codes = {pt.code for pt in problem_types}
        pt_text = (
            "\n".join(f"- {pt.code}: {pt.name}" for pt in problem_types)
            if problem_types
            else "(No problem types mapped to this question)"
        )

        learning_outcomes = self.session.scalars(
            select(LearningOutcome)
            .join(
                QuestionLearningOutcome,
                QuestionLearningOutcome.learning_outcome_id == LearningOutcome.id,
            )
            .where(QuestionLearningOutcome.question_id == question.id)
        ).all()
        allowed_lo_codes = {lo.code for lo in learning_outcomes}
        lo_text = (
            "\n".join(f"- {lo.code}: {lo.description}" for lo in learning_outcomes)
            if learning_outcomes
            else "(No learning outcomes mapped to this question)"
        )

        # 4. Prepare context for AI Prompt
        solution_guide = (
            question.correct_answer
            or question.explanation
            or "(No official reference solution guide provided)"
        )
        rubric_criteria = (
            rubric
            or "(No specific rubric provided; evaluate based on accuracy, complete reasoning, and clear steps)"
        )

        prompt_text = self.prompt_registry.get_prompt(
            name="open_response_evaluator",
            version="v1",
            variables={
                "question_content": question.content,
                "solution_guide": solution_guide,
                "rubric_criteria": rubric_criteria,
                "max_score": "1.0",
                "student_response": attempt.student_answer,
                "allowed_problem_types": pt_text,
                "allowed_concepts": concepts_text,
                "allowed_learning_outcomes": lo_text,
            },
        )

        # 5. Call AI Gateway for structured output
        response = await self.gateway.generate_structured(
            task_type=AITaskType.OPEN_RESPONSE_EVALUATION,
            schema=OpenResponseEvaluationOutput,
            messages=[AIMessage(role=AIRole.USER, content=prompt_text)],
            prompt_name="open_response_evaluator",
            prompt_version="v1",
            user_id=attempt.student_id,
        )
        output: OpenResponseEvaluationOutput = response.data

        # 6. Strict Whitelist Validation (AI cannot invent new codes)
        output.validate_against_whitelist(
            allowed_concept_codes=allowed_concept_codes,
            allowed_learning_outcome_codes=allowed_lo_codes,
        )

        # 7. Update attempt fields and details
        attempt.score = output.score
        attempt.is_correct = output.is_correct
        attempt.evaluation_details = output.model_dump()

        # 8. Confidence Branching
        if output.confidence < confidence_threshold:
            logger.info(
                "Open response evaluation confidence below threshold (attempt_id=%s, confidence=%.2f < threshold=%.2f)",
                attempt.id,
                output.confidence,
                confidence_threshold,
            )
            attempt.evaluation_status = EvaluationStatus.NEEDS_TEACHER_REVIEW
            # Do NOT invoke mastery engine when teacher review is required
        else:
            logger.info(
                "Open response evaluation confident (attempt_id=%s, confidence=%.2f >= threshold=%.2f)",
                attempt.id,
                output.confidence,
                confidence_threshold,
            )
            attempt.evaluation_status = EvaluationStatus.EVALUATED

            # 9. Transfer to Mastery Engine deterministically
            practice_session = self.session.get(
                PracticeSession, attempt.practice_session_id
            )
            if practice_session is not None:
                evidence = AttemptEvaluatedEvidence(
                    attempt_id=attempt.id,
                    practice_session_id=attempt.practice_session_id,
                    student_id=attempt.student_id,
                    question_id=question.id,
                    subject_id=practice_session.subject_id,
                    is_correct=output.is_correct,
                    score=output.score,
                    problem_type_ids=tuple(sorted(pt.id for pt in problem_types)),
                    concept_ids=tuple(sorted(c.id for c in concepts)),
                    learning_outcome_ids=tuple(sorted(lo.id for lo in learning_outcomes)),
                    occurred_at=attempt.created_at,
                )
                self.evidence_publisher.publish(evidence, self.session)

        if commit:
            self.session.commit()
            self.session.refresh(attempt)
        else:
            self.session.flush()

        return attempt
