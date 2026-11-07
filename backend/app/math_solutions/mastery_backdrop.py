"""Step-grounded mastery backdrop, pedagogical error classification, and study plan regeneration.

Bridges step-by-step AI/hybrid solution reviews (both Teacher PDF material items
and Canonical system questions) to StudentProblemTypeMastery, StudentConceptMastery,
MisconceptionService, RootCauseDiagnosticService, and StudyPlanService without violating
EvaluationDecision boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import logging
import re
from uuid import UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.assignments.models import (
    Assignment,
    AssignmentMaterialItem,
    AssignmentMaterialItemConcept,
    AssignmentMaterialItemProblemType,
    AssignmentStudentQuestion,
    StudentAssignment,
    StudentAssignmentMaterialItem,
)
from app.concepts.models import Concept
from app.curriculum.models import Chapter, ProblemType, ProblemTypeConcept, Topic
from app.learning_evidence.models import (
    LearningEvidenceConcept,
    LearningEvidenceEvent,
    LearningEvidenceProblemType,
    LearningEvidenceSourceKind,
)
from app.mastery.evidence import (
    DeterministicMasteryEvidencePublisher,
    GenericMasteryEvidence,
    WeightedConceptEvidence,
    WeightedProblemTypeEvidence,
)
from app.math_solutions.answer_grounded_ai import AIStepGrade, AnswerGroundedReview
from app.math_solutions.models import EvaluationDecision, SolutionAttempt, SolutionRubric, SolutionStep
from app.misconceptions.models import (
    MisconceptionCategory,
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.misconceptions.service import MisconceptionService
from app.planning.study_service import StudyPlanService
from app.practice.models import EvaluationStatus, PracticeSession
from app.questions.models import Question

logger = logging.getLogger(__name__)

_STEP_TYPE_WEIGHTS: dict[str, float] = {
    "ASSUMPTION": 1.0,
    "DERIVATIVE_CALCULATION": 1.25,
    "ROOT_FINDING": 1.2,
    "SIGN_TABLE": 1.25,
    "VARIATION_TABLE": 1.25,
    "CONCLUSION": 1.15,
    "CUSTOM": 1.0,
}

# Maps step types and feedback keywords to canonical concept codes for accurate
# per-step misconception and concept-gap attribution.
_STEP_CONCEPT_KEYWORDS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("ASSUMPTION", "tập xác định", "txđ", "điều kiện", "domain"),
        ("FUNCTION_DOMAIN", "FUNCTION"),
    ),
    (
        ("DERIVATIVE_CALCULATION", "đạo hàm", "y'", "f'(x)", "derivative"),
        ("FIRST_DERIVATIVE", "DERIVATIVE"),
    ),
    (
        ("ROOT_FINDING", "nghiệm", "phương trình", "y' = 0", "y'=0"),
        ("EQUATION_SOLVING", "INEQUALITY_SOLVING", "FIRST_DERIVATIVE"),
    ),
    (
        ("SIGN_TABLE", "VARIATION_TABLE", "bảng biến thiên", "bảng xét dấu", "xét dấu"),
        ("VARIATION_TABLE", "DERIVATIVE_SIGN", "INEQUALITY_SOLVING"),
    ),
    (
        ("CONCLUSION", "đồng biến", "nghịch biến", "cực trị", "cực đại", "cực tiểu", "đồ thị"),
        ("MONOTONICITY_CRITERION", "FUNCTION_GRAPH", "DERIVATIVE_SIGN"),
    ),
    (
        ("ASYMPTOTE", "tiệm cận", "tiệm cận đứng", "tiệm cận ngang", "tiệm cận xiên", "lim", "giới hạn"),
        ("ASYMPTOTE", "VERTICAL_ASYMPTOTE", "HORIZONTAL_ASYMPTOTE", "FUNCTION_LIMIT"),
    ),
    (
        ("EXTREMUM", "OPTIMIZATION", "gtln", "gtnn", "giá trị lớn nhất", "giá trị nhỏ nhất", "max", "min"),
        ("EXTREMUM", "FUNCTION_EXTREMUM", "OPTIMIZATION"),
    ),
    (
        ("INTEGRAL", "ANTIDERIVATIVE", "nguyên hàm", "tích phân", "\\int", "vi phân"),
        ("ANTIDERIVATIVE", "DEFINITE_INTEGRAL", "INTEGRAL_TECHNIQUE"),
    ),
    (
        ("COORDINATE", "OXYZ", "vectơ", "pháp tuyến", "chỉ phương", "mặt phẳng", "mặt cầu", "đường thẳng", "toạ độ"),
        ("VECTORS_3D", "PLANE_EQUATION", "LINE_EQUATION", "SPHERE_EQUATION"),
    ),
    (
        ("PROBABILITY", "STATISTICS", "xác suất", "biến cố", "tổ hợp", "chỉnh hợp", "kỳ vọng"),
        ("PROBABILITY", "RANDOM_VARIABLE", "COMBINATORICS"),
    ),
)


class ErrorPedagogicalCategory(StrEnum):
    """Pedagogical classification of math step errors."""
    VALID = "VALID"
    ARITHMETIC_SLIP = "ARITHMETIC_SLIP"     # Calculation slip / chép nhầm số
    CONSEQUENTIAL = "CONSEQUENTIAL"         # Sai kéo theo (bảo lưu điểm phương pháp)
    CONCEPTUAL = "CONCEPTUAL"               # Sai bản chất / hiểu sai định lý
    NEEDS_REVIEW = "NEEDS_REVIEW"           # Cần giáo viên hoặc kiểm tra thêm


@dataclass(frozen=True, slots=True)
class StepClassificationResult:
    step_index: int
    step_type: str
    verdict: str
    category: ErrorPedagogicalCategory
    score: float
    feedback: str
    misconception_code: str | None = None


def classify_step_error(
    step: SolutionStep,
    grade: AIStepGrade,
    invalid_prior_step_indices: set[int],
) -> StepClassificationResult:
    """Pedagogically classify a student's step evaluation.
    
    Distinguishes Careless Slips (partial credit), Consequential method errors (75% credit),
    and true Conceptual Misconceptions (0 credit) following Vietnamese National Exam standards.
    """
    step_type = step.step_type or "CUSTOM"
    verdict = grade.verdict

    if verdict == "VALID":
        # Low confidence (< 0.80) cannot be treated as verified without human audit
        if grade.confidence is not None and grade.confidence < 0.80:
            return StepClassificationResult(
                step_index=grade.step_index,
                step_type=step_type,
                verdict="NEEDS_REVIEW",
                category=ErrorPedagogicalCategory.NEEDS_REVIEW,
                score=0.0,
                feedback=f"[Chưa đủ độ tin cậy để xác minh bước giải] {grade.feedback}",
            )
        return StepClassificationResult(
            step_index=grade.step_index,
            step_type=step_type,
            verdict="VALID",
            category=ErrorPedagogicalCategory.VALID,
            score=1.0,
            feedback=grade.feedback,
        )

    if verdict in ("NEEDS_REVIEW", "UNDETERMINED"):
        return StepClassificationResult(
            step_index=grade.step_index,
            step_type=step_type,
            verdict="NEEDS_REVIEW",
            category=ErrorPedagogicalCategory.NEEDS_REVIEW,
            score=0.0,
            feedback=grade.feedback,
        )

    # Verdict is INVALID: Classify into ARITHMETIC_SLIP vs CONSEQUENTIAL vs CONCEPTUAL
    feedback_lower = (grade.feedback or "").lower()
    student_quote_lower = (grade.student_quote or "").lower()
    combined_signal = f"{feedback_lower} {student_quote_lower}"

    # PRIMARY SOURCE OF TRUTH: Structured error_nature returned directly by AI
    nature = getattr(grade, "error_nature", None)
    if nature == "CONSEQUENTIAL":
        return StepClassificationResult(
            step_index=grade.step_index,
            step_type=step_type,
            verdict="INVALID",
            category=ErrorPedagogicalCategory.CONSEQUENTIAL,
            score=0.75,  # 75% method credit for correct analytical procedure
            feedback=f"[Bảo lưu điểm phương pháp 75%] {grade.feedback}",
        )
    if nature == "ARITHMETIC_SLIP":
        misc_code = (
            "DERIVATIVE_ARITHMETIC_SLIP"
            if ("đạo hàm" in combined_signal or step_type in {"FIRST_DERIVATIVE", "DERIVATIVE_CALCULATION", "ROOT_FINDING"})
            else None
        )
        return StepClassificationResult(
            step_index=grade.step_index,
            step_type=step_type,
            verdict="INVALID",
            category=ErrorPedagogicalCategory.ARITHMETIC_SLIP,
            score=0.50,  # 50% partial credit for correct algebraic/analytic setup
            feedback=f"[Lỗi sơ suất số học] {grade.feedback}",
            misconception_code=misc_code,
        )
    if nature == "CONCEPTUAL":
        misc_code: str | None = None
        if "dấu" in combined_signal or "biến thiên" in combined_signal or step_type in {"SIGN_TABLE", "VARIATION_TABLE"}:
            misc_code = "DERIVATIVE_SIGN_DIRECTION"
        elif "cực trị" in combined_signal or "cực đại" in combined_signal or "cực tiểu" in combined_signal or step_type == "LOCAL_EXTREMA":
            misc_code = "DERIVATIVE_ZERO_ALWAYS_EXTREMUM"
        return StepClassificationResult(
            step_index=grade.step_index,
            step_type=step_type,
            verdict="INVALID",
            category=ErrorPedagogicalCategory.CONCEPTUAL,
            score=0.0,
            feedback=grade.feedback,
            misconception_code=misc_code,
        )

    # SECONDARY RESILIENT FALLBACK: If error_nature was omitted (mock, legacy, or fallback)
    # 1. Consequential Error: Step is VARIATION_TABLE or CONCLUSION, a prior step had a slip,
    # and student maintained correct mathematical procedures on their derived values.
    is_downstream_step = step_type in {"SIGN_TABLE", "VARIATION_TABLE", "CONCLUSION"}
    explicit_consequential = any(
        kw in combined_signal
        for kw in ("kéo theo", "hệ quả", "phương pháp đúng", "consequential", "theo nghiệm ở trên")
    )
    if is_downstream_step and (invalid_prior_step_indices or explicit_consequential):
        # Unless feedback explicitly points to a fundamental conceptual rule violation:
        conceptual_violations = (
            "áp dụng sai quy tắc", "sai định lý", "trong cùng ngoài khác",
            "không đổi dấu", "quên tập xác định"
        )
        if not any(cv in feedback_lower for cv in conceptual_violations):
            return StepClassificationResult(
                step_index=grade.step_index,
                step_type=step_type,
                verdict="INVALID",
                category=ErrorPedagogicalCategory.CONSEQUENTIAL,
                score=0.75,  # 75% method credit for correct analytical procedure
                feedback=f"[Bảo lưu điểm phương pháp 75%] {grade.feedback}",
            )

    # 2. Arithmetic Slip / Careless Error: Correct formula/method, but calculated numbers incorrectly
    slip_keywords = (
        "tính nhầm", "nhầm dấu", "tính toán", "số học", "bấm máy",
        "chép nhầm", "arithmetic", "calculation", "slip", "transcription",
        "nhầm số", "sai giá trị", "nhầm lẫn số"
    )
    if any(kw in combined_signal for kw in slip_keywords):
        return StepClassificationResult(
            step_index=grade.step_index,
            step_type=step_type,
            verdict="INVALID",
            category=ErrorPedagogicalCategory.ARITHMETIC_SLIP,
            score=0.50,  # 50% partial credit for correct algebraic/analytic setup
            feedback=f"[Lỗi sơ suất số học] {grade.feedback}",
            misconception_code="DERIVATIVE_ARITHMETIC_SLIP"
            if "đạo hàm" in combined_signal
            else None,
        )

    # 3. Conceptual Misconception: True fundamental misconception or rule breach
    misc_code: str | None = None
    if "dấu" in combined_signal or "biến thiên" in combined_signal:
        misc_code = "DERIVATIVE_SIGN_DIRECTION"
    elif "cực trị" in combined_signal or "cực đại" in combined_signal or "cực tiểu" in combined_signal:
        misc_code = "DERIVATIVE_ZERO_ALWAYS_EXTREMUM"

    return StepClassificationResult(
        step_index=grade.step_index,
        step_type=step_type,
        verdict="INVALID",
        category=ErrorPedagogicalCategory.CONCEPTUAL,
        score=0.0,
        feedback=grade.feedback,
        misconception_code=misc_code,
    )


def compute_step_grounded_score(
    steps: list[SolutionStep],
    review: AnswerGroundedReview,
    rubric: SolutionRubric | None = None,
) -> tuple[float, bool, list[str], list[StepClassificationResult]]:
    """Compute weighted score [0, 1] with consequential/slip credit and pedagogical audit.
    
    If a rubric is provided, step weights are extracted directly from rubric criteria.
    Unverified steps (NEEDS_REVIEW) receive 0 score and strictly disqualify is_correct.
    """
    if not review.step_grades:
        return 0.0, False, [], []

    # Extract criterion weights from rubric if available
    rubric_weights: dict[str, float] = {}
    if rubric and rubric.criteria:
        crit_list = (
            rubric.criteria
            if isinstance(rubric.criteria, list)
            else rubric.criteria.get("criteria", [])
        )
        for crit in crit_list:
            st = crit.get("step_type")
            w = crit.get("weight")
            if st and w is not None:
                try:
                    rubric_weights[st] = float(w)
                except (ValueError, TypeError):
                    pass

    step_by_index = {step.step_index: step for step in steps}
    weighted_sum = 0.0
    total_weight = 0.0
    all_valid = True
    failed_summaries: list[str] = []
    classifications: list[StepClassificationResult] = []
    invalid_prior_indices: set[int] = set()

    # Process step by step in sequential order
    sorted_grades = sorted(review.step_grades, key=lambda g: g.step_index)
    for grade in sorted_grades:
        step = step_by_index.get(
            grade.step_index,
            SolutionStep(step_index=grade.step_index, step_type="CUSTOM"),
        )
        step_type = step.step_type or "CUSTOM"
        weight = rubric_weights.get(step_type) or _STEP_TYPE_WEIGHTS.get(step_type, 1.0)
        total_weight += weight

        classification = classify_step_error(step, grade, invalid_prior_indices)
        classifications.append(classification)

        if classification.verdict != "VALID":
            all_valid = False
            invalid_prior_indices.add(grade.step_index)
            failed_summaries.append(f"{step_type} ({classification.category.value}): {classification.feedback}")

        weighted_sum += weight * classification.score

    final_score = round(min(1.0, max(0.0, weighted_sum / max(total_weight, 1e-6))), 4)
    has_needs_review = any(
        c.verdict == "NEEDS_REVIEW" or c.category == ErrorPedagogicalCategory.NEEDS_REVIEW
        for c in classifications
    )
    has_conceptual_error = any(
        c.category == ErrorPedagogicalCategory.CONCEPTUAL for c in classifications
    )
    # A solution is considered passably correct ONLY if verified (no needs_review, not needs_teacher_review)
    # and either all steps valid OR final_score >= 0.85 with no conceptual errors.
    is_correct = (
        not review.needs_teacher_review
        and not has_needs_review
        and (all_valid or (final_score >= 0.85 and not has_conceptual_error))
    )
    return final_score, is_correct, failed_summaries, classifications


class MasteryBackdropService:
    """Applies step-grounded evaluation results to Student Mastery & Adaptive Study Plan."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.mastery_publisher = DeterministicMasteryEvidencePublisher()

    def record_answer_grounded_review(
        self,
        attempt: SolutionAttempt,
        review: AnswerGroundedReview,
        *,
        content_sha256: str,
    ) -> None:
        if not isinstance(self.session, Session):
            return

        # 1. Anti-double-counting: Check if an official EvaluationDecision already exists
        existing_decision = self.session.scalar(
            select(EvaluationDecision).where(EvaluationDecision.attempt_id == attempt.id)
        )
        if existing_decision is not None:
            logger.info(
                "Skipping backdrop for attempt %s: official EvaluationDecision %s already exists",
                attempt.id,
                existing_decision.id,
            )
            return

        # 2. Gating: Only verified reviews (not needing teacher review) may alter mastery
        if review.needs_teacher_review:
            logger.info(
                "Skipping backdrop for attempt %s: review flagged needs_teacher_review",
                attempt.id,
            )
            return

        # Deterministic idempotency key per (attempt.id, content_sha256)
        evidence_source_id = uuid5(attempt.id, f"step-backdrop:{content_sha256}")
        existing = self.session.scalar(
            select(LearningEvidenceEvent).where(
                LearningEvidenceEvent.source_kind
                == LearningEvidenceSourceKind.MATH_SOLUTION_EVALUATION,
                LearningEvidenceEvent.source_entity_id == evidence_source_id,
            )
        )
        if existing is not None:
            return

        active_steps = list(
            self.session.scalars(
                select(SolutionStep)
                .where(
                    SolutionStep.attempt_id == attempt.id,
                    SolutionStep.is_deleted.is_(False),
                )
                .order_by(SolutionStep.step_index.asc())
            ).all()
        )

        rubric = (
            self.session.get(SolutionRubric, attempt.rubric_id)
            if attempt.rubric_id
            else None
        )
        score, is_correct, failed_summaries, classifications = compute_step_grounded_score(
            active_steps, review, rubric=rubric
        )

        # 3. Granular Gating: Only skip if the majority of steps are unverified
        needs_review_count = sum(
            1 for c in classifications if c.category == ErrorPedagogicalCategory.NEEDS_REVIEW
        )
        if classifications and (needs_review_count / len(classifications) > 0.50):
            logger.info(
                "Skipping backdrop for attempt %s: majority of steps unverified (%s/%s)",
                attempt.id,
                needs_review_count,
                len(classifications),
            )
            return

        subject_id, classroom_id, teaching_plan_id, difficulty, problem_types, concepts = (
            self._resolve_curriculum_mappings(attempt)
        )
        if subject_id is None or (not problem_types and not concepts):
            return

        occurred_at = datetime.now(timezone.utc)
        response_time: float | None = None
        if attempt.submitted_at and attempt.started_at:
            s_at = (
                attempt.submitted_at
                if attempt.submitted_at.tzinfo
                else attempt.submitted_at.replace(tzinfo=timezone.utc)
            )
            st_at = (
                attempt.started_at
                if attempt.started_at.tzinfo
                else attempt.started_at.replace(tzinfo=timezone.utc)
            )
            response_time = max(1.0, (s_at - st_at).total_seconds())

        # Persist append-only LearningEvidenceEvent
        event = LearningEvidenceEvent(
            student_id=attempt.student_id,
            subject_id=subject_id,
            classroom_id=classroom_id,
            teaching_plan_id=teaching_plan_id,
            assignment_id=attempt.assignment_id,
            source_kind=LearningEvidenceSourceKind.MATH_SOLUTION_EVALUATION,
            source_entity_id=evidence_source_id,
            is_correct=is_correct,
            score=score,
            difficulty=difficulty,
            response_time_seconds=response_time,
            hint_count=0,
            evaluation_status=EvaluationStatus.EVALUATED,
            occurred_at=occurred_at,
            event_metadata={
                "attempt_id": str(attempt.id),
                "content_sha256": content_sha256,
                "review_source": "ANSWER_GROUNDED_AI",
                "failed_step_summaries": failed_summaries,
                "error_classifications": [
                    {
                        "step_index": c.step_index,
                        "step_type": c.step_type,
                        "category": c.category.value,
                        "score": c.score,
                        "misconception_code": c.misconception_code,
                    }
                    for c in classifications
                    if c.category != ErrorPedagogicalCategory.VALID
                ],
            },
        )
        self.session.add(event)
        self.session.flush()

        self.session.add_all(
            [
                LearningEvidenceConcept(
                    event_id=event.id,
                    concept_id=c.concept_id,
                    weight=c.weight,
                )
                for c in concepts
            ]
        )
        self.session.add_all(
            [
                LearningEvidenceProblemType(
                    event_id=event.id,
                    problem_type_id=pt.problem_type_id,
                    weight=pt.weight,
                    is_primary=pt.is_primary,
                )
                for pt in problem_types
            ]
        )

        # 1. Record evidence in MisconceptionService and check persistent gap confirmation
        self._record_misconceptions_and_track_lifecycle(
            attempt.student_id, classifications, occurred_at
        )

        # 2. Partition concepts into healthy vs confirmed-penalized concepts
        attributed_concepts, penalized_concepts = self._partition_concepts_by_confirmed_gaps(
            attempt.student_id, concepts, active_steps, classifications, event.id
        )

        # 3. Attribute step-specific performance to mapped concepts vs overarching problem types
        concept_ids = [c.concept_id for c in attributed_concepts]
        concept_rows = list(
            self.session.scalars(select(Concept).where(Concept.id.in_(concept_ids)))
        ) if concept_ids else []
        code_by_id = {c.id: c.code for c in concept_rows}

        step_class_by_type = {c.step_type: c for c in classifications}
        concept_specific_evidences: list[tuple[WeightedConceptEvidence, float, bool]] = []
        unmapped_concepts: list[WeightedConceptEvidence] = []

        for c in attributed_concepts:
            concept_code = code_by_id.get(c.concept_id)
            matched_step_class: StepClassificationResult | None = None
            if concept_code:
                for triggers, concept_codes in _STEP_CONCEPT_KEYWORDS:
                    if concept_code in concept_codes:
                        for trig in triggers:
                            if trig in step_class_by_type:
                                matched_step_class = step_class_by_type[trig]
                                break
                    if matched_step_class is not None:
                        break

            if matched_step_class is not None:
                c_score = matched_step_class.score
                c_correct = matched_step_class.category == ErrorPedagogicalCategory.VALID
                concept_specific_evidences.append((c, c_score, c_correct))
            else:
                unmapped_concepts.append(c)

        # Publish ProblemTypes + overarching Concepts with the attempt score
        if problem_types or unmapped_concepts:
            self.mastery_publisher.publish(
                GenericMasteryEvidence(
                    student_id=attempt.student_id,
                    is_correct=is_correct,
                    score=score,
                    difficulty=difficulty,
                    response_time_seconds=response_time,
                    hint_count=0,
                    occurred_at=occurred_at,
                    concepts=tuple(unmapped_concepts),
                    problem_types=tuple(problem_types),
                ),
                self.session,
            )

        # Publish step-specific concepts with their exact rubric/step credit
        for c, c_score, c_correct in concept_specific_evidences:
            self.mastery_publisher.publish(
                GenericMasteryEvidence(
                    student_id=attempt.student_id,
                    is_correct=c_correct,
                    score=c_score,
                    difficulty=difficulty,
                    response_time_seconds=response_time,
                    hint_count=0,
                    occurred_at=occurred_at,
                    concepts=(c,),
                    problem_types=(),
                ),
                self.session,
            )

        # 4. Only if a concept has a CONFIRMED repeated misconception gap across attempts,
        # apply the targeted 0.0 penalty so RootCause and StudyPlan trigger the repair task.
        if penalized_concepts:
            self.mastery_publisher.publish(
                GenericMasteryEvidence(
                    student_id=attempt.student_id,
                    is_correct=False,
                    score=0.0,
                    difficulty=max(0.3, difficulty - 0.15),
                    response_time_seconds=response_time,
                    hint_count=0,
                    occurred_at=occurred_at,
                    concepts=tuple(penalized_concepts),
                    problem_types=(),
                ),
                self.session,
            )

        attempt.total_score = score
        attempt.is_correct = is_correct
        attempt.evaluated_at = occurred_at
        self.session.flush()

        # Sync classroom assignment item and score if this attempt belongs to a classroom assignment
        if attempt.context_type == "CLASSROOM_ASSIGNMENT":
            if attempt.student_assignment_material_item_id:
                smi = self.session.get(StudentAssignmentMaterialItem, attempt.student_assignment_material_item_id)
                if smi:
                    smi.score = score
                    smi.is_correct = is_correct
                    smi.evaluation_status = EvaluationStatus.EVALUATED
                    smi.evaluation_details = {"evaluation": "ai_step_review", "attempt_id": str(attempt.id)}
                    smi.graded_at = occurred_at
                    if smi.answered_at is None:
                        smi.answered_at = occurred_at
            elif attempt.assignment_student_question_id:
                asq = self.session.get(AssignmentStudentQuestion, attempt.assignment_student_question_id)
                if asq:
                    asq.score = score
                    asq.is_correct = is_correct
                    if asq.answered_at is None:
                        asq.answered_at = occurred_at

            if attempt.student_assignment_id:
                student_assignment = self.session.get(StudentAssignment, attempt.student_assignment_id)
                if student_assignment:
                    from app.assignments.scoring import recalculate_student_assignment_score
                    recalculate_student_assignment_score(student_assignment, finalize=False)
            self.session.flush()

        # 5. Trigger Root-Cause Diagnosis when errors occurred
        if not is_correct:
            try:
                with self.session.begin_nested():
                    from app.knowledge_gap.root_cause import RootCauseDiagnosticService

                    RootCauseDiagnosticService(self.session).diagnose_event(event.id)
            except Exception:
                logger.debug("Root-cause diagnosis skipped for event %s", event.id, exc_info=True)

        # 6. Complete matching today's study plan tasks for this attempt
        try:
            with self.session.begin_nested():
                pt_ids = [pt.problem_type_id for pt in problem_types]
                c_ids = [c.concept_id for c in concepts]
                StudyPlanService(self.session).complete_matching_tasks(
                    attempt.student_id,
                    problem_type_ids=pt_ids,
                    concept_ids=c_ids,
                    subject_id=subject_id,
                    as_of=occurred_at.date(),
                )
        except Exception:
            logger.debug("Study task completion skipped for attempt %s", attempt.id, exc_info=True)

        # 7. Regenerate Student Adaptive Study Plan from updated Mastery & TeachingPlan
        try:
            with self.session.begin_nested():
                StudyPlanService(self.session).recalculate_study_plan(
                    attempt.student_id, as_of=occurred_at.date()
                )
        except Exception:
            logger.debug("Study plan recalculation skipped for student %s", attempt.student_id, exc_info=True)

    def _record_misconceptions_and_track_lifecycle(
        self,
        student_id: UUID,
        classifications: list[StepClassificationResult],
        occurred_at: datetime,
    ) -> None:
        """Update student misconceptions using the codebase's deterministic MisconceptionService."""
        misc_service = MisconceptionService(self.session)
        for c in classifications:
            if not c.misconception_code:
                continue
            definition = self.session.scalar(
                select(MisconceptionDefinition).where(
                    MisconceptionDefinition.code == c.misconception_code,
                    MisconceptionDefinition.is_active.is_(True),
                )
            )
            if definition is None:
                continue

            try:
                with self.session.begin_nested():
                    misc_service.record_evidence(
                        student_id=student_id,
                        misconception_definition_id=definition.id,
                        confidence_increment=0.5,
                        detected_at=occurred_at,
                        commit=False,
                    )
            except Exception:
                logger.debug("Misconception recording skipped for %s", c.misconception_code, exc_info=True)

    def _partition_concepts_by_confirmed_gaps(
        self,
        student_id: UUID,
        concepts: list[WeightedConceptEvidence],
        steps: list[SolutionStep],
        classifications: list[StepClassificationResult],
        current_event_id: UUID,
    ) -> tuple[list[WeightedConceptEvidence], list[WeightedConceptEvidence]]:
        """Identify which concepts have CONFIRMED repeated gaps vs first-time slips.
        
        A single error NEVER penalizes a concept with 0.0. Only repeated, confirmed
        misconceptions (minimum_occurrences >= 2) trigger a zero-penalty.
        """
        conceptual_errors = [
            c for c in classifications if c.category == ErrorPedagogicalCategory.CONCEPTUAL
        ]
        if not conceptual_errors or not concepts:
            return concepts, []

        step_type_by_index = {s.step_index: s.step_type for s in steps}
        flagged_codes: set[str] = set()

        for err in conceptual_errors:
            step_type = step_type_by_index.get(err.step_index, "CUSTOM")
            combined_signal = f"{step_type} {err.feedback}".lower()
            for triggers, concept_codes in _STEP_CONCEPT_KEYWORDS:
                if any(t.lower() in combined_signal for t in triggers):
                    flagged_codes.update(concept_codes)

        if not flagged_codes:
            return concepts, []

        concept_ids = [c.concept_id for c in concepts]
        concept_rows = list(
            self.session.scalars(select(Concept).where(Concept.id.in_(concept_ids)))
        )
        code_by_id = {c.id: c.code for c in concept_rows}

        normal: list[WeightedConceptEvidence] = []
        penalized: list[WeightedConceptEvidence] = []

        for c in concepts:
            concept_code = code_by_id.get(c.concept_id)
            if concept_code not in flagged_codes:
                normal.append(c)
                continue

            # Check if this concept gap is CONFIRMED across multiple attempts:
            # 1. Either StudentMisconception is in CONFIRMED status
            # 2. Or student has prior recorded failure events on this concept
            confirmed_misc = self.session.scalar(
                select(StudentMisconception)
                .join(
                    MisconceptionDefinition,
                    MisconceptionDefinition.id == StudentMisconception.misconception_definition_id,
                )
                .where(
                    StudentMisconception.student_id == student_id,
                    MisconceptionDefinition.concept_id == c.concept_id,
                    StudentMisconception.status == StudentMisconceptionStatus.CONFIRMED,
                )
                .limit(1)
            )

            prior_event_failures = self.session.scalar(
                select(func.count(LearningEvidenceEvent.id))
                .join(
                    LearningEvidenceConcept,
                    LearningEvidenceConcept.event_id == LearningEvidenceEvent.id,
                )
                .where(
                    LearningEvidenceEvent.student_id == student_id,
                    LearningEvidenceConcept.concept_id == c.concept_id,
                    LearningEvidenceEvent.is_correct.is_(False),
                    LearningEvidenceEvent.score < 0.50,
                    LearningEvidenceEvent.id != current_event_id,
                )
            ) or 0

            is_confirmed_gap = (confirmed_misc is not None) or (prior_event_failures >= 1)

            if is_confirmed_gap:
                # Student has repeated failures on this concept: penalize with 0.0 to trigger repair
                penalized.append(c)
            else:
                # FIRST-TIME MISTAKE / TRANSIENT SLIP:
                # Do NOT penalize with 0.0! Keep in normal so it receives the attempt score gently.
                normal.append(c)

        return normal, penalized

    def _resolve_curriculum_mappings(
        self, attempt: SolutionAttempt
    ) -> tuple[
        UUID | None,
        UUID | None,
        UUID | None,
        float,
        list[WeightedProblemTypeEvidence],
        list[WeightedConceptEvidence],
    ]:
        subject_id: UUID | None = None
        classroom_id: UUID | None = None
        teaching_plan_id: UUID | None = None
        difficulty = 0.55
        problem_types: list[WeightedProblemTypeEvidence] = []
        concepts: list[WeightedConceptEvidence] = []

        if attempt.assignment_id:
            assignment = self.session.get(Assignment, attempt.assignment_id)
            if assignment:
                subject_id = assignment.subject_id
                classroom_id = assignment.classroom_id
                teaching_plan_id = assignment.teaching_plan_id

        if attempt.practice_session_id and subject_id is None:
            ps = self.session.get(PracticeSession, attempt.practice_session_id)
            if ps:
                subject_id = ps.subject_id

        if attempt.question_id:
            question = self.session.scalar(
                select(Question)
                .options(
                    selectinload(Question.concept_links),
                    selectinload(Question.problem_type_links),
                )
                .where(Question.id == attempt.question_id)
            )
            if question:
                if subject_id is None:
                    subject_id = question.subject_id
                if question.difficulty is not None:
                    difficulty = question.difficulty
                for link in question.problem_type_links:
                    problem_types.append(
                        WeightedProblemTypeEvidence(
                            link.problem_type_id,
                            link.weight if link.weight is not None else 1.0,
                            is_primary=link.is_primary,
                        )
                    )
                for link in question.concept_links:
                    concepts.append(WeightedConceptEvidence(link.concept_id, link.weight))

        return subject_id, classroom_id, teaching_plan_id, difficulty, problem_types, concepts
