from datetime import datetime, timedelta, timezone
import logging
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.assignments.models import (
    Assignment,
    AssignmentMaterialItem,
    AssignmentMaterialItemConcept,
    AssignmentMaterialItemProblemType,
    AssignmentStudentQuestion,
    StudentAssignmentMaterialItem,
)
from app.core.exceptions import ApplicationError
from app.learning_evidence.models import (
    LearningEvidenceConcept,
    LearningEvidenceEvent,
    LearningEvidenceProblemType,
    LearningEvidenceSourceKind,
)
from app.learning_evidence.publisher import (
    LearningEvidencePayload,
    LearningEvidencePublisher,
)
from app.mastery.evidence import (
    WeightedConceptEvidence,
    WeightedProblemTypeEvidence,
)
from app.math_solutions.models import (
    EvaluationDecision,
    EvaluationOverride,
    SolutionAttempt,
)
from app.practice.models import EvaluationStatus
from app.questions.models import Question
from app.review.models import ReviewResult, ReviewSchedule
from app.review.service import ReviewScheduleService

logger = logging.getLogger(__name__)


class MathSolutionEvidenceAdapter:
    """Adapter bridging Math Solution evaluations to the append-only LearningEvidence ledger,
    updating student mastery and spaced repetition schedules, while enforcing anti-double-counting."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.publisher = LearningEvidencePublisher()
        self.review_service = ReviewScheduleService(session)

    def emit_evidence_for_decision(self, decision_id: UUID) -> LearningEvidenceEvent:
        decision = self.session.get(EvaluationDecision, decision_id)
        if decision is None:
            raise ApplicationError(404, "DECISION_NOT_FOUND", "Evaluation decision not found.")

        # Idempotency: if already linked, return existing event
        if decision.learning_evidence_event_id is not None:
            existing = self.session.get(LearningEvidenceEvent, decision.learning_evidence_event_id)
            if existing is not None:
                return existing

        # Check by source entity ID in case of partial retry
        existing_event = self.session.scalar(
            select(LearningEvidenceEvent).where(
                LearningEvidenceEvent.source_kind == LearningEvidenceSourceKind.MATH_SOLUTION_EVALUATION,
                LearningEvidenceEvent.source_entity_id == decision.id,
            )
        )
        if existing_event is not None:
            decision.learning_evidence_event_id = existing_event.id
            self.session.flush()
            return existing_event

        attempt = self.session.get(SolutionAttempt, decision.attempt_id)
        if attempt is None:
            raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Solution attempt not found.")

        # 1. Resolve subject, classroom, teaching plan, assignment
        subject_id: UUID | None = None
        classroom_id: UUID | None = None
        teaching_plan_id: UUID | None = None
        assignment_id: UUID | None = attempt.assignment_id

        if attempt.assignment_id:
            assignment = self.session.get(Assignment, attempt.assignment_id)
            if assignment:
                subject_id = assignment.subject_id
                classroom_id = assignment.classroom_id
                teaching_plan_id = assignment.teaching_plan_id

        concepts: list[WeightedConceptEvidence] = []
        problem_types: list[WeightedProblemTypeEvidence] = []
        difficulty: float = 0.5

        if attempt.question_id:
            question = self.session.scalar(
                select(Question)
                .options(
                    selectinload(Question.concept_links),
                    selectinload(Question.problem_type_links),
                )
                .where(Question.id == attempt.question_id)
            )
            if question is None:
                raise ApplicationError(404, "QUESTION_NOT_FOUND", "Canonical question not found.")
            if subject_id is None:
                subject_id = question.subject_id
            difficulty = question.difficulty if question.difficulty is not None else 0.5

            for link in question.concept_links:
                concepts.append(WeightedConceptEvidence(link.concept_id, link.weight))

            for link in question.problem_type_links:
                problem_types.append(
                    WeightedProblemTypeEvidence(
                        link.problem_type_id,
                        link.weight if link.weight is not None else 1.0,
                        is_primary=link.is_primary,
                    )
                )
        elif attempt.assignment_material_item_id:
            snapshot = self.session.get(AssignmentMaterialItem, attempt.assignment_material_item_id)
            if snapshot:
                difficulty = snapshot.difficulty if snapshot.difficulty is not None else 0.5

            mat_concepts = list(
                self.session.scalars(
                    select(AssignmentMaterialItemConcept).where(
                        AssignmentMaterialItemConcept.assignment_material_item_id
                        == attempt.assignment_material_item_id
                    )
                )
            )
            for mc in mat_concepts:
                concepts.append(WeightedConceptEvidence(mc.concept_id, mc.weight))

            mat_pts = list(
                self.session.scalars(
                    select(AssignmentMaterialItemProblemType).where(
                        AssignmentMaterialItemProblemType.assignment_material_item_id
                        == attempt.assignment_material_item_id
                    )
                )
            )
            for i, mpt in enumerate(mat_pts):
                problem_types.append(
                    WeightedProblemTypeEvidence(
                        mpt.problem_type_id,
                        mpt.weight,
                        is_primary=(i == 0),
                    )
                )

        if subject_id is None:
            raise ApplicationError(422, "SUBJECT_UNDETERMINED", "Cannot determine subject for attempt.")

        occurred_at = decision.decided_at or datetime.now(timezone.utc)
        response_time: float | None = None
        if attempt.submitted_at and attempt.started_at:
            response_time = max(1.0, (attempt.submitted_at - attempt.started_at).total_seconds())

        # 2. Publish LearningEvidenceEvent
        payload = LearningEvidencePayload(
            student_id=attempt.student_id,
            subject_id=subject_id,
            classroom_id=classroom_id,
            teaching_plan_id=teaching_plan_id,
            assignment_id=assignment_id,
            source_kind=LearningEvidenceSourceKind.MATH_SOLUTION_EVALUATION,
            source_entity_id=decision.id,
            is_correct=decision.is_correct,
            score=decision.final_score,
            difficulty=difficulty,
            response_time_seconds=response_time,
            hint_count=0,
            evaluation_status=EvaluationStatus.EVALUATED,
            occurred_at=occurred_at,
            concepts=tuple(concepts),
            problem_types=tuple(problem_types),
            metadata={
                "confirmed_misconceptions": decision.confirmed_misconceptions,
                "decision_source": decision.decision_source,
                "attempt_id": str(attempt.id),
            },
        )

        evidence_event = self.publisher.publish(payload, self.session)
        decision.learning_evidence_event_id = evidence_event.id
        self.session.flush()

        # 3. Anti-Double-Counting synchronization with Classroom Assignment items
        if attempt.assignment_student_question_id:
            asq = self.session.get(AssignmentStudentQuestion, attempt.assignment_student_question_id)
            if asq:
                asq.score = decision.final_score
                asq.is_correct = decision.is_correct
                asq.answered_at = occurred_at
        elif attempt.student_assignment_material_item_id:
            smi = self.session.get(StudentAssignmentMaterialItem, attempt.student_assignment_material_item_id)
            if smi:
                smi.score = decision.final_score
                smi.is_correct = decision.is_correct
                smi.answered_at = occurred_at

        # 4. Spaced repetition schedule (ReviewPolicy 2.0 days)
        primary_pt = next((pt for pt in problem_types if pt.is_primary), None) or (
            problem_types[0] if problem_types else None
        )
        if primary_pt:
            schedule = self.session.scalar(
                select(ReviewSchedule).where(
                    ReviewSchedule.student_id == attempt.student_id,
                    ReviewSchedule.problem_type_id == primary_pt.problem_type_id,
                )
            )
            if schedule is None:
                schedule = self.review_service.ensure_problem_type_schedule(
                    attempt.student_id,
                    primary_pt.problem_type_id,
                    as_of=occurred_at,
                    initial_interval_days=2.0,
                )
            schedule.review_interval_days = 2.0
            schedule.next_review_at = occurred_at + timedelta(days=2.0)
            schedule.last_review_result = (
                ReviewResult.GOOD.value if decision.is_correct else ReviewResult.POOR.value
            )
            schedule.review_count += 1
            self.session.flush()

        return evidence_event

    def apply_teacher_override(
        self,
        decision_id: UUID,
        teacher_id: UUID,
        *,
        new_score: float,
        new_is_correct: bool,
        reason: str,
    ) -> EvaluationOverride:
        decision = self.session.get(EvaluationDecision, decision_id)
        if decision is None:
            raise ApplicationError(404, "DECISION_NOT_FOUND", "Evaluation decision not found.")

        current_max = (
            self.session.scalar(
                select(func.coalesce(func.max(EvaluationOverride.override_version), 0)).where(
                    EvaluationOverride.decision_id == decision.id
                )
            )
            or 0
        )

        override = EvaluationOverride(
            id=uuid4(),
            decision_id=decision.id,
            teacher_id=teacher_id,
            override_version=current_max + 1,
            previous_score=decision.final_score,
            new_score=new_score,
            previous_is_correct=decision.is_correct,
            new_is_correct=new_is_correct,
            override_reason=reason,
            projection_status="APPLIED",
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(override)

        decision.final_score = new_score
        decision.is_correct = new_is_correct
        decision.decision_source = "TEACHER_REVIEW"

        attempt = self.session.get(SolutionAttempt, decision.attempt_id)
        if attempt:
            attempt.total_score = new_score
            attempt.is_correct = new_is_correct

        self.session.flush()
        return override
