"""Deterministic policies for root-cause verification target resolution, probe selection, and outcome evaluation."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ApplicationError
from app.knowledge_gap.models import (
    RootCauseCandidate,
    RootCauseDiagnosis,
    RootCauseDiagnosisType,
    RootCauseVerificationItem,
    RootCauseVerificationOutcome,
    RootCauseVerificationTarget,
    RootCauseVerificationTargetType,
)
from app.practice.models import EvaluationStatus, QuestionAttempt
from app.questions.eligibility import standalone_question_only
from app.questions.evaluation_eligibility import is_deterministically_auto_evaluable
from app.questions.models import CognitiveLevel, Question, QuestionStatus, QuestionType


VERIFICATION_AUTO_EVALUABLE_TYPES = frozenset(
    {
        QuestionType.MULTIPLE_CHOICE,
        QuestionType.TRUE_FALSE,
        QuestionType.SHORT_ANSWER,
    }
)
VERIFICATION_COMPLETED_EVALUATION_STATUSES = frozenset(
    {EvaluationStatus.AUTO_EVALUATED, EvaluationStatus.EVALUATED}
)


def is_completed_verification_attempt(attempt: QuestionAttempt | None) -> bool:
    """Return whether an attempt is valid deterministic verification evidence."""
    return bool(
        attempt is not None
        and attempt.evaluation_status in VERIFICATION_COMPLETED_EVALUATION_STATUSES
        and attempt.is_correct is not None
        and attempt.score is not None
    )


@dataclass(frozen=True, slots=True)
class TargetResolutionSpec:
    target_type: RootCauseVerificationTargetType
    candidate_id: UUID | None
    target_concept_id: UUID | None
    target_problem_type_id: UUID | None
    misconception_definition_id: UUID | None
    priority_order: int
    desired_difficulty: float
    required_probes: int = 2


@dataclass(frozen=True, slots=True)
class CandidateQuestionScore:
    question: Question
    selection_score: float
    target_match: float
    primary_problem_type_fit: float
    isolation_score: float
    difficulty_fit: float
    cognitive_fit: float


class RootCauseVerificationPolicy:
    """Encapsulates deterministic rules for root-cause verification."""

    MIN_PROBES_PER_TARGET: int = 2
    MAX_PROBES_PER_TARGET: int = 3
    DEFAULT_PROBES_PER_TARGET: int = 2

    # Pedagogical difficulty benchmarks for verification probes
    DIFFICULTY_CONCEPT_PROBE: float = 0.35
    DIFFICULTY_PROBLEM_TYPE_PROBE: float = 0.50
    DIFFICULTY_MISCONCEPTION_PROBE: float = 0.40

    @classmethod
    def resolve_targets(cls, diagnosis: RootCauseDiagnosis) -> list[TargetResolutionSpec]:
        """Resolve verification targets from diagnosis and candidate ranking.

        Diagnoses with INSUFFICIENT_EVIDENCE cannot be verified.
        For MULTI_FACTOR_GAP, resolves top 2 candidates as independent targets.
        For other types, resolves the primary candidate (rank 1) or primary entity.
        """
        if diagnosis.diagnosis_type == RootCauseDiagnosisType.INSUFFICIENT_EVIDENCE:
            raise ApplicationError(
                422,
                "CANNOT_VERIFY_INSUFFICIENT_EVIDENCE",
                "Diagnoses with INSUFFICIENT_EVIDENCE cannot be verified.",
            )

        candidates_by_rank = sorted(diagnosis.candidates, key=lambda c: c.rank)

        if diagnosis.diagnosis_type == RootCauseDiagnosisType.MULTI_FACTOR_GAP:
            specs: list[TargetResolutionSpec] = []
            top_candidates = candidates_by_rank[:2]
            for order, cand in enumerate(top_candidates, start=1):
                if cand.candidate_type == RootCauseDiagnosisType.PROBLEM_TYPE_PROCEDURE_GAP or (
                    cand.problem_type_id is not None and cand.concept_id is None
                ):
                    specs.append(
                        TargetResolutionSpec(
                            target_type=RootCauseVerificationTargetType.PROBLEM_TYPE,
                            candidate_id=cand.id,
                            target_concept_id=None,
                            target_problem_type_id=cand.problem_type_id,
                            misconception_definition_id=None,
                            priority_order=order,
                            desired_difficulty=cls.DIFFICULTY_PROBLEM_TYPE_PROBE,
                            required_probes=cls.DEFAULT_PROBES_PER_TARGET,
                        )
                    )
                else:
                    specs.append(
                        TargetResolutionSpec(
                            target_type=RootCauseVerificationTargetType.CONCEPT,
                            candidate_id=cand.id,
                            target_concept_id=cand.concept_id,
                            target_problem_type_id=None,
                            misconception_definition_id=None,
                            priority_order=order,
                            desired_difficulty=cls.DIFFICULTY_CONCEPT_PROBE,
                            required_probes=cls.DEFAULT_PROBES_PER_TARGET,
                        )
                    )
            return specs

        primary_candidate: RootCauseCandidate | None = (
            candidates_by_rank[0] if candidates_by_rank else None
        )

        if diagnosis.diagnosis_type in {
            RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP,
            RootCauseDiagnosisType.DIRECT_CONCEPT_GAP,
        }:
            concept_id = (
                primary_candidate.concept_id
                if primary_candidate and primary_candidate.concept_id
                else diagnosis.root_concept_id
            )
            return [
                TargetResolutionSpec(
                    target_type=RootCauseVerificationTargetType.CONCEPT,
                    candidate_id=primary_candidate.id if primary_candidate else None,
                    target_concept_id=concept_id,
                    target_problem_type_id=None,
                    misconception_definition_id=None,
                    priority_order=1,
                    desired_difficulty=cls.DIFFICULTY_CONCEPT_PROBE,
                    required_probes=cls.DEFAULT_PROBES_PER_TARGET,
                )
            ]

        if diagnosis.diagnosis_type == RootCauseDiagnosisType.PROBLEM_TYPE_PROCEDURE_GAP:
            problem_type_id = (
                primary_candidate.problem_type_id
                if primary_candidate and primary_candidate.problem_type_id
                else diagnosis.target_problem_type_id
            )
            return [
                TargetResolutionSpec(
                    target_type=RootCauseVerificationTargetType.PROBLEM_TYPE,
                    candidate_id=primary_candidate.id if primary_candidate else None,
                    target_concept_id=None,
                    target_problem_type_id=problem_type_id,
                    misconception_definition_id=None,
                    priority_order=1,
                    desired_difficulty=cls.DIFFICULTY_PROBLEM_TYPE_PROBE,
                    required_probes=cls.DEFAULT_PROBES_PER_TARGET,
                )
            ]

        if diagnosis.diagnosis_type == RootCauseDiagnosisType.MISCONCEPTION_HYPOTHESIS:
            concept_id = (
                primary_candidate.concept_id
                if primary_candidate and primary_candidate.concept_id
                else diagnosis.root_concept_id
            )
            problem_type_id = (
                primary_candidate.problem_type_id
                if primary_candidate and primary_candidate.problem_type_id
                else diagnosis.target_problem_type_id
            )
            misconception_id = (
                primary_candidate.misconception_definition_id
                if primary_candidate and primary_candidate.misconception_definition_id
                else diagnosis.misconception_definition_id
            )
            return [
                TargetResolutionSpec(
                    target_type=RootCauseVerificationTargetType.MISCONCEPTION,
                    candidate_id=primary_candidate.id if primary_candidate else None,
                    target_concept_id=concept_id,
                    target_problem_type_id=problem_type_id,
                    misconception_definition_id=misconception_id,
                    priority_order=1,
                    desired_difficulty=cls.DIFFICULTY_MISCONCEPTION_PROBE,
                    required_probes=cls.DEFAULT_PROBES_PER_TARGET,
                )
            ]

        return []

    @classmethod
    def select_probe_questions(
        cls,
        session: Session,
        subject_id: UUID,
        target_spec: TargetResolutionSpec,
        excluded_question_ids: set[UUID],
    ) -> list[tuple[Question, float]]:
        """Query and score canonical questions suitable as verification probes.

        Only canonical APPROVED questions with complete taxonomy are queried.
        Questions in excluded_question_ids (recent exposures, diagnosis source,
        earlier picked probes) are strictly filtered out.
        Returns a list of (Question, selection_score) up to target_spec.required_probes.
        Does NOT duplicate questions if available count is less than required.
        """
        stmt = (
            select(Question)
            .options(
                selectinload(Question.concept_links),
                selectinload(Question.problem_type_links),
                selectinload(Question.learning_outcome_links),
                selectinload(Question.options),
            )
            .where(
                Question.subject_id == subject_id,
                Question.status == QuestionStatus.APPROVED,
                Question.question_type.in_(VERIFICATION_AUTO_EVALUABLE_TYPES),
                standalone_question_only(),
                Question.concept_links.any(),
                Question.problem_type_links.any(),
                Question.learning_outcome_links.any(),
            )
        )

        if target_spec.target_type == RootCauseVerificationTargetType.CONCEPT:
            if target_spec.target_concept_id is not None:
                stmt = stmt.where(
                    Question.concept_links.any(concept_id=target_spec.target_concept_id)
                )
        elif target_spec.target_type == RootCauseVerificationTargetType.PROBLEM_TYPE:
            if target_spec.target_problem_type_id is not None:
                stmt = stmt.where(
                    Question.problem_type_links.any(
                        problem_type_id=target_spec.target_problem_type_id
                    )
                )
        elif target_spec.target_type == RootCauseVerificationTargetType.MISCONCEPTION:
            if target_spec.target_concept_id is not None:
                stmt = stmt.where(
                    Question.concept_links.any(concept_id=target_spec.target_concept_id)
                )
            elif target_spec.target_problem_type_id is not None:
                stmt = stmt.where(
                    Question.problem_type_links.any(
                        problem_type_id=target_spec.target_problem_type_id
                    )
                )

        if excluded_question_ids:
            stmt = stmt.where(~Question.id.in_(excluded_question_ids))

        candidates = [q for q in session.scalars(stmt) if is_deterministically_auto_evaluable(q)]
        if not candidates:
            return []

        scored_candidates: list[CandidateQuestionScore] = []
        for q in candidates:
            score = cls.score_probe_question(q, target_spec)
            scored_candidates.append(score)

        # Deterministic ranking: highest selection_score, smallest difficulty delta, stable ID
        scored_candidates.sort(
            key=lambda item: (
                -item.selection_score,
                abs((item.question.difficulty or 0.5) - target_spec.desired_difficulty),
                str(item.question.id),
            )
        )

        picked = scored_candidates[: target_spec.required_probes]
        return [(item.question, item.selection_score) for item in picked]

    @classmethod
    def score_probe_question(
        cls,
        question: Question,
        target_spec: TargetResolutionSpec,
    ) -> CandidateQuestionScore:
        """Deterministic probe selection score prioritizing target isolation and difficulty fit.

        target_match: matching taxonomy link weight.
        primary_problem_type_fit: 1.0 when the target ProblemType is primary.
        isolation_score: 1.0 / len(concept_links) (fewer confounding concepts = higher isolation)
        difficulty_fit: 1.0 - abs(difficulty - target_difficulty)
        cognitive_fit: 1.0 for REMEMBER/UNDERSTAND, 0.7 for APPLY, 0.4 for ANALYZE
        """
        concept_count = len(question.concept_links) or 1
        isolation_score = round(1.0 / concept_count, 4)

        target_match = 0.0
        primary_problem_type_fit = 0.0
        if target_spec.target_type == RootCauseVerificationTargetType.CONCEPT:
            target_match = max(
                (
                    float(link.weight)
                    for link in question.concept_links
                    if link.concept_id == target_spec.target_concept_id
                ),
                default=0.0,
            )
        elif target_spec.target_type == RootCauseVerificationTargetType.PROBLEM_TYPE:
            matching_links = [
                link
                for link in question.problem_type_links
                if link.problem_type_id == target_spec.target_problem_type_id
            ]
            target_match = max(
                (
                    float(link.weight) if link.weight is not None else 1.0
                    for link in matching_links
                ),
                default=0.0,
            )
            primary_problem_type_fit = (
                1.0 if any(link.is_primary for link in matching_links) else 0.0
            )
        else:
            concept_weights = [
                float(link.weight)
                for link in question.concept_links
                if link.concept_id == target_spec.target_concept_id
            ]
            problem_type_links = [
                link
                for link in question.problem_type_links
                if link.problem_type_id == target_spec.target_problem_type_id
            ]
            problem_type_weights = [
                float(link.weight) if link.weight is not None else 1.0
                for link in problem_type_links
            ]
            target_match = max(concept_weights + problem_type_weights, default=0.0)
            primary_problem_type_fit = (
                1.0 if any(link.is_primary for link in problem_type_links) else 0.0
            )

        diff = question.difficulty if question.difficulty is not None else 0.5
        difficulty_fit = max(0.0, 1.0 - abs(diff - target_spec.desired_difficulty))

        cognitive_level = question.cognitive_level
        if cognitive_level in {CognitiveLevel.REMEMBER, CognitiveLevel.UNDERSTAND}:
            cognitive_fit = 1.0
        elif cognitive_level == CognitiveLevel.APPLY:
            cognitive_fit = 0.7
        else:
            cognitive_fit = 0.4

        selection_score = round(
            0.30 * target_match
            + 0.20 * primary_problem_type_fit
            + 0.20 * isolation_score
            + 0.20 * difficulty_fit
            + 0.10 * cognitive_fit,
            4,
        )

        return CandidateQuestionScore(
            question=question,
            selection_score=selection_score,
            target_match=round(target_match, 4),
            primary_problem_type_fit=primary_problem_type_fit,
            isolation_score=isolation_score,
            difficulty_fit=round(difficulty_fit, 4),
            cognitive_fit=round(cognitive_fit, 4),
        )

    @classmethod
    def evaluate_target_outcome(
        cls,
        items: list[RootCauseVerificationItem],
        attempts_by_id: dict[UUID, QuestionAttempt],
    ) -> tuple[RootCauseVerificationOutcome, int, int, float | None]:
        """Evaluate empirical verification outcome for a target based on student attempt evidence.

        Criteria:
        - If probe_count < 2 (even if 1 attempt failed): INCONCLUSIVE (insufficient sample).
        - If probe_count >= 2:
          - avg_score <= 0.50: SUPPORTED (gap confirmed empirically).
          - avg_score >= 0.80 and all attempts correct: NOT_SUPPORTED (gap disproved).
          - otherwise: INCONCLUSIVE.
        - If len(items) == 0: UNAVAILABLE.

        Returns (outcome, probe_count, correct_count, average_score).
        """
        if not items:
            return RootCauseVerificationOutcome.UNAVAILABLE, 0, 0, None

        attempted_items = [
            item
            for item in items
            if is_completed_verification_attempt(attempts_by_id.get(item.attempt_id))
        ]
        probe_count = len(attempted_items)

        if probe_count == 0:
            return RootCauseVerificationOutcome.PENDING, 0, 0, None

        correct_count = 0
        total_score = 0.0
        all_correct = True

        for item in attempted_items:
            attempt = attempts_by_id[item.attempt_id]
            # Guarded by is_completed_verification_attempt above.
            is_corr = attempt.is_correct is True
            score = float(attempt.score)
            if is_corr:
                correct_count += 1
            else:
                all_correct = False
            total_score += score

        average_score = round(total_score / probe_count, 4)

        if probe_count < cls.MIN_PROBES_PER_TARGET:
            return RootCauseVerificationOutcome.INCONCLUSIVE, probe_count, correct_count, average_score

        if average_score <= 0.50:
            return RootCauseVerificationOutcome.SUPPORTED, probe_count, correct_count, average_score

        if average_score >= 0.80 and all_correct:
            return RootCauseVerificationOutcome.NOT_SUPPORTED, probe_count, correct_count, average_score

        return RootCauseVerificationOutcome.INCONCLUSIVE, probe_count, correct_count, average_score

    @classmethod
    def evaluate_overall_outcome(
        cls,
        targets: list[RootCauseVerificationTarget],
    ) -> RootCauseVerificationOutcome:
        """Combine individual target outcomes into overall verification conclusion.

        - If any target is SUPPORTED -> SUPPORTED.
        - If all targets are NOT_SUPPORTED -> NOT_SUPPORTED.
        - If any target is INCONCLUSIVE -> INCONCLUSIVE.
        - If all targets UNAVAILABLE -> UNAVAILABLE.
        - Otherwise PENDING.
        """
        if not targets:
            return RootCauseVerificationOutcome.UNAVAILABLE

        outcomes = [t.outcome for t in targets]

        if any(o == RootCauseVerificationOutcome.SUPPORTED for o in outcomes):
            return RootCauseVerificationOutcome.SUPPORTED

        if all(o == RootCauseVerificationOutcome.NOT_SUPPORTED for o in outcomes):
            return RootCauseVerificationOutcome.NOT_SUPPORTED

        if any(o == RootCauseVerificationOutcome.INCONCLUSIVE for o in outcomes):
            return RootCauseVerificationOutcome.INCONCLUSIVE

        if all(o == RootCauseVerificationOutcome.UNAVAILABLE for o in outcomes):
            return RootCauseVerificationOutcome.UNAVAILABLE

        return RootCauseVerificationOutcome.PENDING
