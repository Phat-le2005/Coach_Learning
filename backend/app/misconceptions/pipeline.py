from __future__ import annotations

import logging
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.dependencies import create_ai_provider
from app.ai.gateway import AIGateway
from app.ai.prompt_registry import PromptRegistry, default_prompt_registry
from app.ai.types import AIMessage, AIRole, AITaskType
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.concepts.graph_service import ConceptGraphService
from app.knowledge_gap.evidence_context import DiagnosticEvidenceContext
from app.misconceptions.deterministic_rules import DeterministicRuleMatcher, has_reasoning
from app.misconceptions.models import MisconceptionDefinition
from app.misconceptions.schemas import (
    MisconceptionAnalysisOutput,
    MisconceptionPipelineResult,
)
from app.misconceptions.service import MisconceptionPolicy, MisconceptionService
from app.misconceptions.taxonomy import ScopedTaxonomy, TaxonomyScoper
from app.practice.models import EvaluationStatus, QuestionAttempt
from app.questions.models import Question

logger = logging.getLogger(__name__)


class MisconceptionPipeline:
    """End-to-end pipeline for diagnosing misconceptions from wrong question attempts.

    Pipeline flow:
        wrong attempt
            ↓
        deterministic rule
            ↓ (if insufficient and response has reasoning)
        AI analysis (scoped taxonomy)
            ↓
        Pydantic validation (whitelist enforced; no invented codes)
            ↓
        map to existing MisconceptionDefinition
            ↓
        record evidence (policy-controlled StudentMisconception state).
    """

    DEFAULT_MIN_CONFIDENCE_TO_RECORD: float = 0.50

    def __init__(
        self,
        session: Session,
        *,
        gateway: AIGateway | None = None,
        misconception_service: MisconceptionService | None = None,
        prompt_registry: PromptRegistry | None = None,
        taxonomy_scoper: TaxonomyScoper | None = None,
        deterministic_matcher: DeterministicRuleMatcher | None = None,
        min_confidence_to_record: float = DEFAULT_MIN_CONFIDENCE_TO_RECORD,
    ) -> None:
        self.session = session
        if gateway is not None:
            self.gateway = gateway
        else:
            settings = Settings()
            provider = create_ai_provider(settings)
            self.gateway = AIGateway(provider=provider, settings=settings)

        self.misconception_service = (
            misconception_service or MisconceptionService(session)
        )
        self.prompt_registry = prompt_registry or default_prompt_registry
        self.taxonomy_scoper = taxonomy_scoper or TaxonomyScoper(session)
        self.deterministic_matcher = (
            deterministic_matcher or DeterministicRuleMatcher()
        )
        self.min_confidence_to_record = min_confidence_to_record

    async def run_pipeline(
        self,
        attempt: QuestionAttempt,
        *,
        student_explanation: str | None = None,
        commit: bool = True,
    ) -> MisconceptionPipelineResult:
        """Execute the pipeline on a question attempt."""
        # 1. Pipeline applies ONLY to wrong attempts
        if attempt.is_correct is True:
            return MisconceptionPipelineResult(
                detected=False,
                detection_source="NONE",
                reason="Attempt was evaluated as correct; misconception detection skipped.",
            )

        question = self.session.get(Question, attempt.question_id)
        if question is None:
            raise ApplicationError(404, "QUESTION_NOT_FOUND", "Associated question not found.")

        # 2. Scope the taxonomy strictly to Question concepts, ProblemTypes, and prerequisite concepts
        taxonomy = self.taxonomy_scoper.get_scoped_taxonomy(question)

        # 3. Deterministic rule check
        det_output = self.deterministic_matcher.evaluate(
            question, attempt.student_answer, taxonomy
        )
        if det_output is not None:
            det_output.validate_against_taxonomy(
                allowed_codes=taxonomy.allowed_codes,
                allowed_concept_ids=taxonomy.allowed_concept_ids,
                allowed_problem_type_ids=taxonomy.allowed_problem_type_ids,
                allowed_prerequisite_concept_ids=taxonomy.allowed_prerequisite_concept_ids,
            )
            if det_output.misconception_code != "UNKNOWN":
                return self._finalize_diagnosis(
                    attempt=attempt,
                    output=det_output,
                    taxonomy=taxonomy,
                    source="DETERMINISTIC",
                    commit=commit,
                )

        # 4. If deterministic matching is insufficient, check whether response contains reasoning
        full_response_text = f"{attempt.student_answer} {student_explanation or ''}".strip()
        if not has_reasoning(full_response_text):
            return MisconceptionPipelineResult(
                detected=False,
                detection_source="NONE",
                reason="Student response does not contain verifiable reasoning steps or scratchwork.",
            )

        # 5. Check if any active taxonomy exists in this scope
        if not taxonomy.definitions:
            return MisconceptionPipelineResult(
                detected=False,
                detection_source="NONE",
                reason="No active misconception definitions available in the scoped question taxonomy.",
            )

        # 6. AI Analysis with strict taxonomy whitelist context
        ai_output = await self._run_ai_analysis(
            question=question,
            student_answer=attempt.student_answer,
            student_explanation=student_explanation or "(None provided)",
            taxonomy=taxonomy,
        )

        # 7. Pydantic whitelist validation: AI cannot invent new codes or out-of-scope concepts
        ai_output.validate_against_taxonomy(
            allowed_codes=taxonomy.allowed_codes,
            allowed_concept_ids=taxonomy.allowed_concept_ids,
            allowed_problem_type_ids=taxonomy.allowed_problem_type_ids,
            allowed_prerequisite_concept_ids=taxonomy.allowed_prerequisite_concept_ids,
        )

        if ai_output.misconception_code == "UNKNOWN":
            return MisconceptionPipelineResult(
                detected=False,
                detection_source="AI",
                concept_id=ai_output.concept_id,
                problem_type_id=ai_output.problem_type_id,
                error_category=ai_output.error_category,
                first_wrong_step=ai_output.first_wrong_step,
                confidence=ai_output.confidence,
                possible_prerequisite_concept_id=ai_output.possible_prerequisite_concept_id,
                requires_prerequisite_check=ai_output.requires_prerequisite_check,
                reason="AI diagnosed error as UNKNOWN or unclassified within the supplied taxonomy.",
            )

        # 8. Map into existing MisconceptionDefinition and apply backend policy
        return self._finalize_diagnosis(
            attempt=attempt,
            output=ai_output,
            taxonomy=taxonomy,
            source="AI",
            commit=commit,
        )

    async def run_for_evidence(
        self,
        context: DiagnosticEvidenceContext,
        *,
        student_explanation: str | None = None,
        record_evidence: bool = False,
        commit: bool = True,
    ) -> MisconceptionPipelineResult:
        """Analyze common evidence while preserving the QuestionAttempt adapter.

        The default is advisory-only so reprocessing an event cannot increment a
        persistent misconception label.
        """
        event = context.evidence_event
        if (
            event.is_correct is not False
            or event.score is None
            or event.evaluation_status
            not in (EvaluationStatus.AUTO_EVALUATED, EvaluationStatus.EVALUATED)
        ):
            return MisconceptionPipelineResult(
                detected=False,
                detection_source="NONE",
                reason="Evidence is not an evaluated wrong response.",
            )
        prerequisites = set(
            ConceptGraphService(self.session).get_prerequisite_distances(
                set(context.concept_weights), context.subject_id, max_depth=3
            )
        )
        taxonomy = self.taxonomy_scoper.get_scoped_taxonomy_for_evidence(
            direct_concept_ids=set(context.concept_weights),
            direct_problem_type_ids=set(context.problem_type_weights),
            prerequisite_concept_ids=prerequisites,
        )
        output: MisconceptionAnalysisOutput | None = None
        source = "NONE"
        if context.canonical_question is not None:
            output = self.deterministic_matcher.evaluate(
                context.canonical_question,
                context.student_response or "",
                taxonomy,
            )
            source = "DETERMINISTIC"
        response_text = f"{context.student_response or ''} {student_explanation or ''}".strip()
        if (
            (output is None or output.misconception_code == "UNKNOWN")
            and has_reasoning(response_text)
            and taxonomy.definitions
        ):
            try:
                question_like = SimpleNamespace(
                    content=context.content,
                    correct_answer=context.expected_answer,
                    explanation=context.explanation,
                )
                output = await self._run_ai_analysis(
                    question=question_like,  # type: ignore[arg-type]
                    student_answer=context.student_response or "",
                    student_explanation=student_explanation or "(None provided)",
                    taxonomy=taxonomy,
                )
                source = "AI"
            except Exception:
                logger.warning(
                    "Misconception advisory failed; deterministic diagnosis remains available",
                    exc_info=True,
                )
                output = None
        if output is None:
            return MisconceptionPipelineResult(
                detected=False,
                detection_source="NONE",
                reason="No scoped misconception signal was found.",
            )
        output.validate_against_taxonomy(
            allowed_codes=taxonomy.allowed_codes,
            allowed_concept_ids=taxonomy.allowed_concept_ids,
            allowed_problem_type_ids=taxonomy.allowed_problem_type_ids,
            allowed_prerequisite_concept_ids=taxonomy.allowed_prerequisite_concept_ids,
        )
        if output.misconception_code == "UNKNOWN":
            return MisconceptionPipelineResult(
                detected=False,
                detection_source=source,  # type: ignore[arg-type]
                reason="Signal remained UNKNOWN within the scoped taxonomy.",
            )
        return self._finalize_for_student(
            student_id=context.student_id,
            output=output,
            taxonomy=taxonomy,
            source=source,
            commit=commit,
            record_evidence=record_evidence,
        )

    async def _run_ai_analysis(
        self,
        question: Question,
        student_answer: str,
        student_explanation: str,
        taxonomy: ScopedTaxonomy,
    ) -> MisconceptionAnalysisOutput:
        """Call AI to analyze the student's reasoning against the scoped taxonomy."""
        related_concept_names = [
            f"{c.name} ({c.code})" for c in taxonomy.concepts_by_id.values()
        ]
        pt_names = [
            f"{pt.name} ({pt.code})" for pt in taxonomy.problem_types_by_id.values()
        ]

        prompt_text = self.prompt_registry.get_prompt(
            "misconception_detector",
            "v1",
            variables={
                "problem_type_name": ", ".join(pt_names) or "General",
                "related_concepts": ", ".join(related_concept_names) or "General",
                "question_content": question.content,
                "correct_answer": question.correct_answer or question.explanation or "(Standard solution)",
                "student_answer": student_answer,
                "student_explanation": student_explanation,
                "allowed_taxonomy": taxonomy.format_for_prompt(),
            },
        )

        messages = [
            AIMessage(
                role=AIRole.USER,
                content=prompt_text,
            )
        ]

        response = await self.gateway.generate_structured(
            task_type=AITaskType.MISCONCEPTION_ANALYSIS,
            messages=messages,
            schema=MisconceptionAnalysisOutput,
            temperature=0.2,
            prompt_name="misconception_detector",
            prompt_version="v1",
        )
        return response.data

    def _finalize_diagnosis(
        self,
        attempt: QuestionAttempt,
        output: MisconceptionAnalysisOutput,
        taxonomy: ScopedTaxonomy,
        source: str,
        commit: bool,
    ) -> MisconceptionPipelineResult:
        """Backward-compatible QuestionAttempt adapter."""
        return self._finalize_for_student(
            student_id=attempt.student_id,
            output=output,
            taxonomy=taxonomy,
            source=source,
            commit=commit,
            record_evidence=True,
        )

    def _finalize_for_student(
        self,
        *,
        student_id: UUID,
        output: MisconceptionAnalysisOutput,
        taxonomy: ScopedTaxonomy,
        source: str,
        commit: bool,
        record_evidence: bool,
    ) -> MisconceptionPipelineResult:
        definition: MisconceptionDefinition | None = next(
            (row for row in taxonomy.definitions if row.code == output.misconception_code),
            None,
        )
        if definition is None:
            return MisconceptionPipelineResult(
                detected=False,
                detection_source=source,  # type: ignore[arg-type]
                concept_id=output.concept_id,
                problem_type_id=output.problem_type_id,
                error_category=output.error_category,
                first_wrong_step=output.first_wrong_step,
                confidence=output.confidence,
                possible_prerequisite_concept_id=output.possible_prerequisite_concept_id,
                requires_prerequisite_check=output.requires_prerequisite_check,
                reason="Diagnosed misconception code does not map to an active definition.",
            )
        if output.confidence < self.min_confidence_to_record:
            return MisconceptionPipelineResult(
                detected=True,
                detection_source=source,  # type: ignore[arg-type]
                misconception_definition_id=definition.id,
                misconception_code=definition.code,
                concept_id=output.concept_id,
                problem_type_id=output.problem_type_id,
                error_category=output.error_category,
                first_wrong_step=output.first_wrong_step,
                confidence=output.confidence,
                possible_prerequisite_concept_id=output.possible_prerequisite_concept_id,
                requires_prerequisite_check=output.requires_prerequisite_check,
                evidence_recorded=False,
                reason=(
                    f"Confidence {output.confidence:.2f} is below minimum recording "
                    f"threshold ({self.min_confidence_to_record:.2f}); evidence skipped per policy."
                ),
            )
        if not record_evidence:
            return MisconceptionPipelineResult(
                detected=True,
                detection_source=source,  # type: ignore[arg-type]
                misconception_definition_id=definition.id,
                misconception_code=definition.code,
                concept_id=output.concept_id,
                problem_type_id=output.problem_type_id,
                error_category=output.error_category,
                first_wrong_step=output.first_wrong_step,
                confidence=output.confidence,
                possible_prerequisite_concept_id=output.possible_prerequisite_concept_id,
                requires_prerequisite_check=output.requires_prerequisite_check,
                evidence_recorded=False,
                reason="Scoped misconception hypothesis returned in advisory-only mode.",
            )
        increment = round(min(1.0, max(0.05, output.confidence * 0.40)), 4)
        student_misconception = self.misconception_service.record_evidence(
            student_id=student_id,
            misconception_definition_id=definition.id,
            confidence_increment=increment,
            commit=commit,
        )
        return MisconceptionPipelineResult(
            detected=True,
            detection_source=source,  # type: ignore[arg-type]
            misconception_definition_id=definition.id,
            misconception_code=definition.code,
            concept_id=output.concept_id,
            problem_type_id=output.problem_type_id,
            error_category=output.error_category,
            first_wrong_step=output.first_wrong_step,
            confidence=output.confidence,
            possible_prerequisite_concept_id=output.possible_prerequisite_concept_id,
            requires_prerequisite_check=output.requires_prerequisite_check,
            evidence_recorded=True,
            student_misconception_status=student_misconception.status,
            occurrence_count=student_misconception.occurrence_count,
            reason="Misconception evidence successfully recorded by backend.",
        )
