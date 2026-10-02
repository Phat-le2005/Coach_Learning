"""Deterministic, evidence-driven root-cause diagnosis.

This module consumes the append-only learning evidence stream. It never writes
mastery, taxonomy, attempts, or persistent misconception labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Protocol
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.classes.access import TeacherStudentAccessService
from app.concepts.graph_service import ConceptGraphService
from app.core.exceptions import ApplicationError
from app.knowledge_gap.evidence_context import (
    DiagnosticEvidenceContext,
    LearningEvidenceContextResolver,
)
from app.knowledge_gap.models import (
    RootCauseCandidate,
    RootCauseDiagnosis,
    RootCauseDiagnosisStatus,
    RootCauseDiagnosisType,
)
from app.knowledge_gap.schemas import (
    RootCauseCandidateRead,
    RootCauseDiagnosisRead,
    RootCauseSourceEventRead,
)
from app.learning_evidence.models import LearningEvidenceEvent
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.misconceptions.models import (
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.misconceptions.deterministic_rules import has_reasoning
from app.misconceptions.taxonomy import TaxonomyScoper
from app.practice.models import EvaluationStatus
from app.students.models import StudentProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AdvisorySignal:
    """Optional, non-authoritative signal returned by an AI adapter."""

    misconception_code: str | None = None
    concept_id: UUID | None = None
    problem_type_id: UUID | None = None
    observations: tuple[str, ...] = ()


class RootCauseAdvisor(Protocol):
    def advise(
        self,
        context: DiagnosticEvidenceContext,
        *,
        allowed_concept_ids: set[UUID],
        allowed_problem_type_ids: set[UUID],
        allowed_misconception_codes: set[str],
    ) -> AdvisorySignal | None: ...


@dataclass(slots=True)
class EvidenceCounts:
    wrong: int = 0
    correct: int = 0

    @property
    def total(self) -> int:
        return self.wrong + self.correct


@dataclass(slots=True)
class RankedCandidate:
    candidate_type: RootCauseDiagnosisType
    concept_id: UUID | None = None
    problem_type_id: UUID | None = None
    misconception_definition_id: UUID | None = None
    graph_distance: int | None = None
    score: float = 0.0
    confidence: float = 0.0
    mastery_deficit_signal: float = 0.0
    recent_error_signal: float = 0.0
    structural_signal: float = 0.0
    misconception_signal: float = 0.0
    evidence_volume_signal: float = 0.0
    supporting_event_count: int = 0
    conflicting_event_count: int = 0
    mastery_confidence: float = 0.0
    mastery_known: bool = False
    reason_codes: list[str] = field(default_factory=list)

    @property
    def stable_key(self) -> tuple[str, str, str, str]:
        return (
            self.candidate_type.value,
            str(self.concept_id or ""),
            str(self.problem_type_id or ""),
            str(self.misconception_definition_id or ""),
        )


@dataclass(frozen=True, slots=True)
class RootCauseDecision:
    diagnosis_type: RootCauseDiagnosisType
    status: RootCauseDiagnosisStatus
    confidence: float
    reason_code: str
    root_concept_id: UUID | None
    misconception_definition_id: UUID | None
    supporting_evidence_count: int


class RootCauseScoringPolicy:
    """Single home for diagnostic ranking and confidence constants."""

    HISTORY_LIMIT = 20
    MAX_PREREQUISITE_DEPTH = 3
    EVIDENCE_VOLUME_TARGET = 4
    AMBIGUITY_MARGIN = 0.10
    MEANINGFUL_SCORE = 0.28
    STRONG_STATUS_CONFIDENCE = 0.70
    STRONG_MASTERY = 0.65

    MASTERY_WEIGHT = 0.35
    ERROR_WEIGHT = 0.30
    STRUCTURAL_WEIGHT = 0.15
    MISCONCEPTION_WEIGHT = 0.15
    VOLUME_WEIGHT = 0.05

    @classmethod
    def evidence_volume(cls, count: int) -> float:
        return min(1.0, count / cls.EVIDENCE_VOLUME_TARGET)

    @classmethod
    def score_candidate(cls, candidate: RankedCandidate) -> float:
        candidate.score = round(
            min(
                1.0,
                cls.MASTERY_WEIGHT * candidate.mastery_deficit_signal
                + cls.ERROR_WEIGHT * candidate.recent_error_signal
                + cls.STRUCTURAL_WEIGHT * candidate.structural_signal
                + cls.MISCONCEPTION_WEIGHT * candidate.misconception_signal
                + cls.VOLUME_WEIGHT * candidate.evidence_volume_signal,
            ),
            6,
        )
        return candidate.score

    @classmethod
    def candidate_confidence(cls, candidate: RankedCandidate) -> float:
        consistency = (
            candidate.supporting_event_count
            / max(1, candidate.supporting_event_count + candidate.conflicting_event_count)
        )
        candidate.confidence = round(
            min(
                1.0,
                0.45 * candidate.score
                + 0.20 * candidate.evidence_volume_signal
                + 0.20 * candidate.mastery_confidence
                + 0.15 * consistency,
            ),
            6,
        )
        return candidate.confidence

    @classmethod
    def diagnosis_confidence(
        cls, candidates: list[RankedCandidate], *, force_low: bool = False
    ) -> float:
        if not candidates:
            return 0.0
        first = candidates[0]
        second_score = candidates[1].score if len(candidates) > 1 else 0.0
        margin = max(0.0, first.score - second_score)
        consistency = first.supporting_event_count / max(
            1, first.supporting_event_count + first.conflicting_event_count
        )
        result = min(
            1.0,
            0.40 * first.score
            + 0.20 * min(1.0, margin / 0.25)
            + 0.20 * first.evidence_volume_signal
            + 0.10 * first.mastery_confidence
            + 0.10 * consistency,
        )
        if force_low:
            result = min(result, 0.35)
        return round(result, 6)


class RootCauseDiagnosticService:
    """Materializes one auditable diagnosis for an evaluated wrong event."""

    def __init__(
        self,
        session: Session,
        *,
        advisor: RootCauseAdvisor | None = None,
        policy: type[RootCauseScoringPolicy] = RootCauseScoringPolicy,
    ) -> None:
        self.session = session
        self.advisor = advisor
        self.policy = policy
        self.contexts = LearningEvidenceContextResolver(session)
        self.graph = ConceptGraphService(session)

    def diagnose_event(
        self, event_id: UUID, *, commit: bool = False
    ) -> RootCauseDiagnosis | None:
        event = self.session.scalar(
            select(LearningEvidenceEvent)
            .where(LearningEvidenceEvent.id == event_id)
            .with_for_update()
        )
        if event is None:
            raise ApplicationError(
                404, "LEARNING_EVIDENCE_NOT_FOUND", "Learning evidence was not found."
            )
        existing = self._existing(event_id)
        if existing is not None:
            return existing
        if not self._is_diagnostic_trigger(event):
            return None

        context = self.contexts.resolve(event_id)
        prereq_distances = self.graph.get_prerequisite_distances(
            set(context.concept_weights),
            context.subject_id,
            max_depth=self.policy.MAX_PREREQUISITE_DEPTH,
        )
        history = self._history(context)
        concept_counts, pt_counts = self._historical_counts(history)
        concept_ids = set(context.concept_weights) | set(prereq_distances)
        problem_type_ids = set(context.problem_type_weights)
        concept_mastery = self._concept_masteries(context.student_id, concept_ids)
        pt_mastery = self._problem_type_masteries(context.student_id, problem_type_ids)
        misconceptions = self._misconceptions(
            context.student_id, concept_ids, problem_type_ids
        )

        candidates = self._build_candidates(
            context,
            prereq_distances,
            concept_counts,
            pt_counts,
            concept_mastery,
            pt_mastery,
            misconceptions,
        )
        self._apply_advisory(context, candidates)
        candidates.sort(key=lambda item: (-item.score, item.stable_key))
        for candidate in candidates:
            self.policy.candidate_confidence(candidate)
        decision = self._decide(candidates)

        diagnosis = RootCauseDiagnosis(
            learning_evidence_event_id=event.id,
            student_id=event.student_id,
            subject_id=event.subject_id,
            classroom_id=event.classroom_id,
            assignment_id=event.assignment_id,
            target_problem_type_id=context.primary_problem_type_id,
            diagnosis_type=decision.diagnosis_type,
            status=decision.status,
            root_concept_id=decision.root_concept_id,
            misconception_definition_id=decision.misconception_definition_id,
            confidence=decision.confidence,
            supporting_evidence_count=decision.supporting_evidence_count,
            reason_code=decision.reason_code,
            diagnosis_metadata={
                "history_window": self.policy.HISTORY_LIMIT,
                "prerequisite_max_depth": self.policy.MAX_PREREQUISITE_DEPTH,
                "source_kind": context.source_kind.value,
                "source_entity_id": str(context.source_entity_id),
                "snapshot_id": (
                    str(context.assignment_material_snapshot_id)
                    if context.assignment_material_snapshot_id
                    else None
                ),
                "candidate_count": len(candidates),
            },
        )
        diagnosis.candidates = [
            RootCauseCandidate(
                rank=rank,
                candidate_type=item.candidate_type,
                concept_id=item.concept_id,
                problem_type_id=item.problem_type_id,
                misconception_definition_id=item.misconception_definition_id,
                graph_distance=item.graph_distance,
                score=item.score,
                confidence=item.confidence,
                mastery_deficit_signal=item.mastery_deficit_signal,
                recent_error_signal=item.recent_error_signal,
                structural_signal=item.structural_signal,
                misconception_signal=item.misconception_signal,
                evidence_volume_signal=item.evidence_volume_signal,
                supporting_event_count=item.supporting_event_count,
                conflicting_event_count=item.conflicting_event_count,
                reason_codes=item.reason_codes,
            )
            for rank, item in enumerate(candidates, start=1)
        ]
        try:
            with self.session.begin_nested():
                self.session.add(diagnosis)
                self.session.flush()
        except IntegrityError:
            self.session.expire_all()
            existing = self._existing(event_id)
            if existing is not None:
                return existing
            raise
        if commit:
            self.session.commit()
            self.session.refresh(diagnosis)
        return diagnosis

    def recent_for_student_user(
        self, user_id: UUID, *, limit: int = 20
    ) -> list[RootCauseDiagnosis]:
        student = self.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        if student is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Student profile was not found.")
        return self._recent(student.id, limit)

    def get_for_student_user(
        self, user_id: UUID, diagnosis_id: UUID
    ) -> RootCauseDiagnosis:
        student = self.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        if student is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Student profile was not found.")
        return self._get_owned(diagnosis_id, student.id)

    def recent_for_teacher(
        self, teacher_user_id: UUID, student_id: UUID, *, limit: int = 20
    ) -> list[RootCauseDiagnosis]:
        TeacherStudentAccessService(self.session).require_active_relationship(
            teacher_user_id, student_id, denied_code="DIAGNOSTIC_ACCESS_DENIED"
        )
        return self._recent(student_id, limit)

    def to_read_models(
        self, diagnoses: list[RootCauseDiagnosis]
    ) -> list[RootCauseDiagnosisRead]:
        event_ids = {row.learning_evidence_event_id for row in diagnoses}
        events = {
            row.id: row
            for row in self.session.scalars(
                select(LearningEvidenceEvent).where(
                    LearningEvidenceEvent.id.in_(event_ids)
                )
            )
        } if event_ids else {}
        return [self._to_read(row, events[row.learning_evidence_event_id]) for row in diagnoses]

    def to_read_model(self, diagnosis: RootCauseDiagnosis) -> RootCauseDiagnosisRead:
        event = self.session.get(
            LearningEvidenceEvent, diagnosis.learning_evidence_event_id
        )
        if event is None:
            raise ApplicationError(409, "DIAGNOSTIC_EVIDENCE_MISSING", "Diagnostic evidence is missing.")
        return self._to_read(diagnosis, event)

    @staticmethod
    def _to_read(
        diagnosis: RootCauseDiagnosis, event: LearningEvidenceEvent
    ) -> RootCauseDiagnosisRead:
        messages = {
            "PREREQUISITE_LOW_MASTERY_REPEATED_ERRORS": "Evidence hiện tại cho thấy một kiến thức tiên quyết có khả năng là nguyên nhân; cần kiểm tra thêm.",
            "DIRECT_CONCEPT_REPEATED_ERRORS": "Evidence hiện tại cho thấy concept trực tiếp có khả năng còn yếu; cần kiểm tra thêm.",
            "PROBLEM_TYPE_FAILURE_WITH_STRONG_COMPONENTS": "Học sinh có thể đang gặp khó khăn ở quy trình tổng hợp của dạng bài dù các thành phần tương đối ổn định.",
            "PERSISTENT_MISCONCEPTION_SIGNAL": "Có tín hiệu misconception lặp lại trong đúng phạm vi kiến thức; đây vẫn là một giả thuyết.",
            "AMBIGUOUS_MULTIPLE_CAUSES": "Nhiều nguyên nhân có mức hỗ trợ gần nhau; chưa nên chọn một nguyên nhân duy nhất.",
            "INSUFFICIENT_HISTORY": "Chưa đủ evidence để kết luận nguyên nhân; cần thêm lần kiểm tra phù hợp.",
        }
        return RootCauseDiagnosisRead(
            id=diagnosis.id,
            learning_evidence_event_id=diagnosis.learning_evidence_event_id,
            student_id=diagnosis.student_id,
            subject_id=diagnosis.subject_id,
            classroom_id=diagnosis.classroom_id,
            assignment_id=diagnosis.assignment_id,
            target_problem_type_id=diagnosis.target_problem_type_id,
            diagnosis_type=diagnosis.diagnosis_type,
            status=diagnosis.status,
            root_concept_id=diagnosis.root_concept_id,
            misconception_definition_id=diagnosis.misconception_definition_id,
            confidence=diagnosis.confidence,
            supporting_evidence_count=diagnosis.supporting_evidence_count,
            reason_code=diagnosis.reason_code,
            explanation=messages.get(
                diagnosis.reason_code,
                "Evidence hiện tại tạo một giả thuyết cần được kiểm tra thêm.",
            ),
            source_event=RootCauseSourceEventRead(
                id=event.id,
                source_kind=event.source_kind,
                source_entity_id=event.source_entity_id,
                occurred_at=event.occurred_at,
            ),
            candidates=[RootCauseCandidateRead.model_validate(row) for row in diagnosis.candidates],
            created_at=diagnosis.created_at,
        )

    @staticmethod
    def _is_diagnostic_trigger(event: LearningEvidenceEvent) -> bool:
        return (
            event.is_correct is False
            and event.score is not None
            and event.evaluation_status
            in (EvaluationStatus.AUTO_EVALUATED, EvaluationStatus.EVALUATED)
        )

    def _existing(self, event_id: UUID) -> RootCauseDiagnosis | None:
        return self.session.scalar(
            select(RootCauseDiagnosis)
            .options(selectinload(RootCauseDiagnosis.candidates))
            .where(RootCauseDiagnosis.learning_evidence_event_id == event_id)
        )

    def _history(
        self, context: DiagnosticEvidenceContext
    ) -> list[LearningEvidenceEvent]:
        return list(
            self.session.scalars(
                select(LearningEvidenceEvent)
                .options(
                    selectinload(LearningEvidenceEvent.concepts),
                    selectinload(LearningEvidenceEvent.problem_types),
                )
                .where(
                    LearningEvidenceEvent.student_id == context.student_id,
                    LearningEvidenceEvent.subject_id == context.subject_id,
                    LearningEvidenceEvent.score.is_not(None),
                    LearningEvidenceEvent.is_correct.is_not(None),
                    LearningEvidenceEvent.evaluation_status.in_(
                        [EvaluationStatus.AUTO_EVALUATED, EvaluationStatus.EVALUATED]
                    ),
                )
                .order_by(
                    LearningEvidenceEvent.occurred_at.desc(),
                    LearningEvidenceEvent.id.desc(),
                )
                .limit(self.policy.HISTORY_LIMIT)
            ).unique()
        )

    @staticmethod
    def _historical_counts(
        events: list[LearningEvidenceEvent],
    ) -> tuple[dict[UUID, EvidenceCounts], dict[UUID, EvidenceCounts]]:
        concept_counts: dict[UUID, EvidenceCounts] = {}
        pt_counts: dict[UUID, EvidenceCounts] = {}
        for event in events:
            for link in event.concepts:
                counts = concept_counts.setdefault(link.concept_id, EvidenceCounts())
                if event.is_correct:
                    counts.correct += 1
                else:
                    counts.wrong += 1
            for link in event.problem_types:
                counts = pt_counts.setdefault(link.problem_type_id, EvidenceCounts())
                if event.is_correct:
                    counts.correct += 1
                else:
                    counts.wrong += 1
        return concept_counts, pt_counts

    def _concept_masteries(
        self, student_id: UUID, concept_ids: set[UUID]
    ) -> dict[UUID, StudentConceptMastery]:
        if not concept_ids:
            return {}
        rows = self.session.scalars(
            select(StudentConceptMastery).where(
                StudentConceptMastery.student_id == student_id,
                StudentConceptMastery.concept_id.in_(concept_ids),
            )
        )
        return {row.concept_id: row for row in rows}

    def _problem_type_masteries(
        self, student_id: UUID, problem_type_ids: set[UUID]
    ) -> dict[UUID, StudentProblemTypeMastery]:
        if not problem_type_ids:
            return {}
        rows = self.session.scalars(
            select(StudentProblemTypeMastery).where(
                StudentProblemTypeMastery.student_id == student_id,
                StudentProblemTypeMastery.problem_type_id.in_(problem_type_ids),
            )
        )
        return {row.problem_type_id: row for row in rows}

    def _misconceptions(
        self,
        student_id: UUID,
        concept_ids: set[UUID],
        problem_type_ids: set[UUID],
    ) -> list[tuple[StudentMisconception, MisconceptionDefinition]]:
        if not concept_ids and not problem_type_ids:
            return []
        conditions = []
        if concept_ids:
            conditions.append(MisconceptionDefinition.concept_id.in_(concept_ids))
        if problem_type_ids:
            conditions.append(
                MisconceptionDefinition.problem_type_id.in_(problem_type_ids)
            )
        return list(
            self.session.execute(
                select(StudentMisconception, MisconceptionDefinition)
                .join(
                    MisconceptionDefinition,
                    StudentMisconception.misconception_definition_id
                    == MisconceptionDefinition.id,
                )
                .where(
                    StudentMisconception.student_id == student_id,
                    StudentMisconception.status.in_(
                        [
                            StudentMisconceptionStatus.SUSPECTED,
                            StudentMisconceptionStatus.CONFIRMED,
                        ]
                    ),
                    MisconceptionDefinition.is_active.is_(True),
                    or_(*conditions),
                )
                .order_by(MisconceptionDefinition.code)
            ).all()
        )

    def _build_candidates(
        self,
        context: DiagnosticEvidenceContext,
        prereq_distances: dict[UUID, int],
        concept_counts: dict[UUID, EvidenceCounts],
        pt_counts: dict[UUID, EvidenceCounts],
        concept_masteries: dict[UUID, StudentConceptMastery],
        pt_masteries: dict[UUID, StudentProblemTypeMastery],
        misconceptions: list[tuple[StudentMisconception, MisconceptionDefinition]],
    ) -> list[RankedCandidate]:
        result: list[RankedCandidate] = []
        misconception_by_concept: dict[UUID, float] = {}
        for student_row, definition in misconceptions:
            misconception_by_concept[definition.concept_id] = max(
                misconception_by_concept.get(definition.concept_id, 0.0),
                student_row.confidence
                * min(1.0, student_row.occurrence_count / 3),
            )

        for concept_id in sorted(context.concept_weights, key=str):
            result.append(
                self._concept_candidate(
                    concept_id=concept_id,
                    candidate_type=RootCauseDiagnosisType.DIRECT_CONCEPT_GAP,
                    distance=0,
                    mapping_weight=context.concept_weights[concept_id],
                    counts=concept_counts.get(concept_id, EvidenceCounts()),
                    mastery=concept_masteries.get(concept_id),
                    misconception_signal=misconception_by_concept.get(concept_id, 0.0),
                )
            )
        max_direct_weight = max(context.concept_weights.values(), default=1.0)
        for concept_id, distance in prereq_distances.items():
            result.append(
                self._concept_candidate(
                    concept_id=concept_id,
                    candidate_type=RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP,
                    distance=distance,
                    mapping_weight=max_direct_weight,
                    counts=concept_counts.get(concept_id, EvidenceCounts()),
                    mastery=concept_masteries.get(concept_id),
                    misconception_signal=misconception_by_concept.get(concept_id, 0.0),
                )
            )
        for pt_id in sorted(context.problem_type_weights, key=str):
            counts = pt_counts.get(pt_id, EvidenceCounts())
            mastery = pt_masteries.get(pt_id)
            volume = self.policy.evidence_volume(counts.total)
            strong_components = self._components_are_strong(
                concept_masteries, set(context.concept_weights) | set(prereq_distances)
            )
            candidate = RankedCandidate(
                candidate_type=RootCauseDiagnosisType.PROBLEM_TYPE_PROCEDURE_GAP,
                problem_type_id=pt_id,
                mastery_deficit_signal=self._mastery_deficit(mastery),
                recent_error_signal=(counts.wrong / counts.total * volume)
                if counts.total
                else 0.0,
                structural_signal=(
                    context.problem_type_weights[pt_id] if strong_components else 0.15
                ),
                evidence_volume_signal=volume,
                supporting_event_count=counts.wrong,
                conflicting_event_count=counts.correct,
                mastery_confidence=mastery.confidence if mastery else 0.0,
                mastery_known=mastery is not None and mastery.attempt_count >= 2,
                reason_codes=[
                    "REPEATED_PROBLEM_TYPE_ERRORS"
                    if counts.wrong >= 2
                    else "PROBLEM_TYPE_ERROR_OBSERVED",
                    "COMPONENTS_RELATIVELY_STRONG"
                    if strong_components
                    else "COMPONENT_STRENGTH_UNCERTAIN",
                ],
            )
            self.policy.score_candidate(candidate)
            result.append(candidate)

        for student_row, definition in misconceptions:
            volume = self.policy.evidence_volume(student_row.occurrence_count)
            candidate = RankedCandidate(
                candidate_type=RootCauseDiagnosisType.MISCONCEPTION_HYPOTHESIS,
                concept_id=definition.concept_id,
                problem_type_id=definition.problem_type_id,
                misconception_definition_id=definition.id,
                recent_error_signal=student_row.confidence * volume,
                structural_signal=0.5,
                misconception_signal=student_row.confidence * volume,
                evidence_volume_signal=volume,
                supporting_event_count=student_row.occurrence_count,
                conflicting_event_count=0,
                mastery_confidence=0.0,
                mastery_known=student_row.occurrence_count >= 2,
                reason_codes=["PERSISTENT_MISCONCEPTION_SIGNAL"],
            )
            self.policy.score_candidate(candidate)
            result.append(candidate)
        return result

    def _concept_candidate(
        self,
        *,
        concept_id: UUID,
        candidate_type: RootCauseDiagnosisType,
        distance: int,
        mapping_weight: float,
        counts: EvidenceCounts,
        mastery: StudentConceptMastery | None,
        misconception_signal: float,
    ) -> RankedCandidate:
        volume = self.policy.evidence_volume(counts.total)
        structural = min(1.0, mapping_weight) / (1 + distance)
        recent_error = counts.wrong / counts.total * volume if counts.total else 0.0
        reason = (
            "DIRECT_CONCEPT_REPEATED_ERRORS"
            if distance == 0 and counts.wrong >= 2
            else "PREREQUISITE_LOW_MASTERY_REPEATED_ERRORS"
            if distance > 0 and counts.wrong >= 2 and mastery is not None
            else "DIRECT_CONCEPT_OBSERVED"
            if distance == 0
            else "PREREQUISITE_RELATION_ONLY"
        )
        candidate = RankedCandidate(
            candidate_type=candidate_type,
            concept_id=concept_id,
            graph_distance=distance,
            mastery_deficit_signal=self._mastery_deficit(mastery),
            recent_error_signal=recent_error,
            structural_signal=structural,
            misconception_signal=misconception_signal,
            evidence_volume_signal=volume,
            supporting_event_count=counts.wrong,
            conflicting_event_count=counts.correct,
            mastery_confidence=mastery.confidence if mastery else 0.0,
            mastery_known=mastery is not None and mastery.attempt_count >= 2,
            reason_codes=[reason],
        )
        self.policy.score_candidate(candidate)
        return candidate

    @staticmethod
    def _mastery_deficit(
        mastery: StudentConceptMastery | StudentProblemTypeMastery | None,
    ) -> float:
        if mastery is None or mastery.attempt_count <= 0:
            return 0.0
        return max(0.0, min(1.0, (1.0 - mastery.mastery_score) * mastery.confidence))

    def _components_are_strong(
        self,
        masteries: dict[UUID, StudentConceptMastery],
        component_ids: set[UUID],
    ) -> bool:
        if not component_ids:
            return False
        rows = [masteries.get(component_id) for component_id in component_ids]
        return all(
            row is not None
            and row.attempt_count > 0
            and row.mastery_score >= self.policy.STRONG_MASTERY
            and row.confidence >= 0.5
            for row in rows
        )

    def _apply_advisory(
        self,
        context: DiagnosticEvidenceContext,
        candidates: list[RankedCandidate],
    ) -> None:
        if self.advisor is None or not has_reasoning(context.student_response):
            return
        ordered = sorted(candidates, key=lambda item: (-item.score, item.stable_key))
        if ordered:
            margin = ordered[0].score - (ordered[1].score if len(ordered) > 1 else 0.0)
            if ordered[0].score >= 0.55 and margin >= self.policy.AMBIGUITY_MARGIN:
                return
        allowed_concepts = {item.concept_id for item in candidates if item.concept_id}
        allowed_problem_types = {
            item.problem_type_id for item in candidates if item.problem_type_id
        }
        prerequisite_ids = {
            item.concept_id
            for item in candidates
            if item.concept_id
            and item.candidate_type == RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP
        }
        taxonomy = TaxonomyScoper(self.session).get_scoped_taxonomy_for_evidence(
            direct_concept_ids=set(context.concept_weights),
            direct_problem_type_ids=set(context.problem_type_weights),
            prerequisite_concept_ids=prerequisite_ids,
        )
        definitions = {definition.code: definition for definition in taxonomy.definitions}
        if not definitions:
            return
        try:
            advisory = self.advisor.advise(
                context,
                allowed_concept_ids=allowed_concepts,
                allowed_problem_type_ids=allowed_problem_types,
                allowed_misconception_codes=set(definitions),
            )
        except Exception:
            logger.warning("Root-cause advisory failed; using deterministic result", exc_info=True)
            return
        if advisory is None:
            return
        if advisory.concept_id and advisory.concept_id not in allowed_concepts:
            return
        if (
            advisory.problem_type_id
            and advisory.problem_type_id not in allowed_problem_types
        ):
            return
        if (
            advisory.misconception_code
            and advisory.misconception_code not in definitions
        ):
            return
        # Advisory is deliberately small and cannot create a candidate or set final
        # confidence. It can add one bounded misconception signal to an existing row.
        if advisory.misconception_code:
            definition_id = definitions[advisory.misconception_code].id
            for candidate in candidates:
                if candidate.misconception_definition_id == definition_id:
                    candidate.misconception_signal = min(
                        1.0, candidate.misconception_signal + 0.05
                    )
                    candidate.reason_codes.append("SCOPED_ADVISORY_SUPPORT")
                    self.policy.score_candidate(candidate)
                    break

    def _decide(self, candidates: list[RankedCandidate]) -> RootCauseDecision:
        candidates.sort(key=lambda item: (-item.score, item.stable_key))
        if not candidates:
            return self._insufficient(None, 0.0)
        top = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None
        substantive = (
            top.mastery_known
            or top.supporting_event_count >= 2
            or (
                top.candidate_type == RootCauseDiagnosisType.MISCONCEPTION_HYPOTHESIS
                and top.supporting_event_count >= 2
            )
        )
        single_observation = (
            top.supporting_event_count <= 1
            and not top.mastery_known
            and all(item.supporting_event_count <= 1 for item in candidates)
        )
        confidence = self.policy.diagnosis_confidence(
            candidates, force_low=single_observation
        )
        if not substantive or top.score < self.policy.MEANINGFUL_SCORE:
            return self._insufficient(top, confidence)

        if (
            second is not None
            and second.score >= self.policy.MEANINGFUL_SCORE
            and second.supporting_event_count >= 2
            and top.supporting_event_count >= 2
            and top.score - second.score < self.policy.AMBIGUITY_MARGIN
        ):
            return RootCauseDecision(
                diagnosis_type=RootCauseDiagnosisType.MULTI_FACTOR_GAP,
                status=RootCauseDiagnosisStatus.HYPOTHESIS,
                confidence=confidence,
                reason_code="AMBIGUOUS_MULTIPLE_CAUSES",
                root_concept_id=None,
                misconception_definition_id=None,
                supporting_evidence_count=max(
                    top.supporting_event_count, second.supporting_event_count
                ),
            )

        # A prerequisite relation alone is not evidence that the prerequisite is weak.
        if (
            top.candidate_type == RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP
            and not (top.mastery_known or top.supporting_event_count >= 2)
        ):
            return self._insufficient(top, confidence)
        status = (
            RootCauseDiagnosisStatus.STRONG_HYPOTHESIS
            if confidence >= self.policy.STRONG_STATUS_CONFIDENCE
            and top.supporting_event_count >= 3
            else RootCauseDiagnosisStatus.HYPOTHESIS
        )
        reason_codes = {
            RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP: "PREREQUISITE_LOW_MASTERY_REPEATED_ERRORS",
            RootCauseDiagnosisType.DIRECT_CONCEPT_GAP: "DIRECT_CONCEPT_REPEATED_ERRORS",
            RootCauseDiagnosisType.PROBLEM_TYPE_PROCEDURE_GAP: "PROBLEM_TYPE_FAILURE_WITH_STRONG_COMPONENTS",
            RootCauseDiagnosisType.MISCONCEPTION_HYPOTHESIS: "PERSISTENT_MISCONCEPTION_SIGNAL",
        }
        return RootCauseDecision(
            diagnosis_type=top.candidate_type,
            status=status,
            confidence=confidence,
            reason_code=reason_codes.get(top.candidate_type, top.reason_codes[0]),
            root_concept_id=top.concept_id,
            misconception_definition_id=top.misconception_definition_id,
            supporting_evidence_count=top.supporting_event_count,
        )

    @staticmethod
    def _insufficient(
        top: RankedCandidate | None, confidence: float
    ) -> RootCauseDecision:
        return RootCauseDecision(
            diagnosis_type=RootCauseDiagnosisType.INSUFFICIENT_EVIDENCE,
            status=RootCauseDiagnosisStatus.INSUFFICIENT_EVIDENCE,
            confidence=min(confidence, 0.35),
            reason_code="INSUFFICIENT_HISTORY",
            root_concept_id=None,
            misconception_definition_id=None,
            supporting_evidence_count=top.supporting_event_count if top else 0,
        )

    def _recent(self, student_id: UUID, limit: int) -> list[RootCauseDiagnosis]:
        safe_limit = max(1, min(limit, 100))
        return list(
            self.session.scalars(
                select(RootCauseDiagnosis)
                .options(selectinload(RootCauseDiagnosis.candidates))
                .where(RootCauseDiagnosis.student_id == student_id)
                .order_by(
                    RootCauseDiagnosis.created_at.desc(), RootCauseDiagnosis.id.desc()
                )
                .limit(safe_limit)
            ).unique()
        )

    def _get_owned(
        self, diagnosis_id: UUID, student_id: UUID
    ) -> RootCauseDiagnosis:
        diagnosis = self.session.scalar(
            select(RootCauseDiagnosis)
            .options(selectinload(RootCauseDiagnosis.candidates))
            .where(
                RootCauseDiagnosis.id == diagnosis_id,
                RootCauseDiagnosis.student_id == student_id,
            )
        )
        if diagnosis is None:
            raise ApplicationError(
                404, "ROOT_CAUSE_DIAGNOSIS_NOT_FOUND", "Diagnosis was not found."
            )
        return diagnosis
