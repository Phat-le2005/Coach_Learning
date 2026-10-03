from dataclasses import dataclass, field
from datetime import datetime
import logging
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learning_evidence.models import LearningEvidenceConcept, LearningEvidenceEvent, LearningEvidenceProblemType, LearningEvidenceSourceKind
from app.mastery.evidence import DeterministicMasteryEvidencePublisher, GenericMasteryEvidence, WeightedConceptEvidence, WeightedProblemTypeEvidence
from app.mastery.strategy import MasteryCalculationStrategy
from app.practice.models import EvaluationStatus

logger = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class LearningEvidencePayload:
    student_id: UUID
    subject_id: UUID
    source_kind: LearningEvidenceSourceKind
    source_entity_id: UUID
    is_correct: bool | None
    score: float | None
    difficulty: float | None
    response_time_seconds: float | None
    hint_count: int
    evaluation_status: EvaluationStatus
    occurred_at: datetime
    concepts: tuple[WeightedConceptEvidence, ...] = ()
    problem_types: tuple[WeightedProblemTypeEvidence, ...] = ()
    classroom_id: UUID | None = None
    teaching_plan_id: UUID | None = None
    assignment_id: UUID | None = None
    metadata: dict = field(default_factory=dict)

class LearningEvidencePublisher:
    def __init__(self, strategy: MasteryCalculationStrategy | None = None) -> None:
        self.mastery = DeterministicMasteryEvidencePublisher(strategy)

    def publish(self, payload: LearningEvidencePayload, session: Session) -> LearningEvidenceEvent:
        existing = session.scalar(select(LearningEvidenceEvent).where(LearningEvidenceEvent.source_kind == payload.source_kind, LearningEvidenceEvent.source_entity_id == payload.source_entity_id))
        if existing is not None:
            self._diagnose_if_needed(existing, session)
            return existing
        row = LearningEvidenceEvent(student_id=payload.student_id, subject_id=payload.subject_id, classroom_id=payload.classroom_id, teaching_plan_id=payload.teaching_plan_id, assignment_id=payload.assignment_id, source_kind=payload.source_kind, source_entity_id=payload.source_entity_id, is_correct=payload.is_correct, score=payload.score, difficulty=payload.difficulty, response_time_seconds=payload.response_time_seconds, hint_count=payload.hint_count, evaluation_status=payload.evaluation_status, occurred_at=payload.occurred_at, event_metadata=payload.metadata)
        session.add(row); session.flush()
        session.add_all([LearningEvidenceConcept(event_id=row.id, concept_id=x.concept_id, weight=x.weight) for x in payload.concepts])
        session.add_all([LearningEvidenceProblemType(event_id=row.id, problem_type_id=x.problem_type_id, weight=x.weight, is_primary=x.is_primary) for x in payload.problem_types])
        if payload.is_correct is not None and payload.score is not None and payload.difficulty is not None:
            self.mastery.publish(GenericMasteryEvidence(student_id=payload.student_id, is_correct=payload.is_correct, score=payload.score, difficulty=payload.difficulty, response_time_seconds=payload.response_time_seconds, hint_count=payload.hint_count, occurred_at=payload.occurred_at, concepts=payload.concepts, problem_types=payload.problem_types), session)
        session.flush()
        self._diagnose_if_needed(row, session)
        return row

    @staticmethod
    def _diagnose_if_needed(event: LearningEvidenceEvent, session: Session) -> None:
        if event.event_metadata.get("suppress_root_cause_rediagnosis") is True:
            return
        if (
            event.is_correct is not False
            or event.score is None
            or event.evaluation_status
            not in (EvaluationStatus.AUTO_EVALUATED, EvaluationStatus.EVALUATED)
        ):
            return
        # A savepoint keeps answer/evidence/mastery durable in the caller's
        # transaction even if the diagnostic consumer encounters bad context.
        try:
            with session.begin_nested():
                from app.knowledge_gap.root_cause import RootCauseDiagnosticService

                RootCauseDiagnosticService(session).diagnose_event(event.id)
        except Exception:
            logger.exception(
                "Root-cause diagnosis failed without discarding evidence (event_id=%s)",
                event.id,
            )
