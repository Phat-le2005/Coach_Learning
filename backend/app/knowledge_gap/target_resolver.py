"""Resolver for verified learning targets and canonical repair question recommendations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import ProblemType
from app.knowledge_gap.models import (
    RootCauseDiagnosis,
    RootCauseDiagnosisType,
    RootCauseVerification,
    RootCauseVerificationOutcome,
    RootCauseVerificationStatus,
    RootCauseVerificationTarget,
    RootCauseVerificationTargetType,
)
from app.knowledge_gap.schemas import (
    NextDiagnosticActionType,
    RootCauseNextActionRead,
    VerifiedTargetRead,
)
from app.questions.exposure import QuestionExposureService
from app.recommendations.question_service import QuestionRecommendationService
from app.students.models import StudentProfile


class VerifiedLearningTargetService:
    """Connects empirical verification results to canonical repair question recommendations."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.recommendation_service = QuestionRecommendationService(session)
        self.exposure_service = QuestionExposureService(session)

    def resolve_next_action(
        self,
        student_id: UUID,
        diagnosis_id: UUID,
    ) -> RootCauseNextActionRead:
        """Determine next recommended pedagogical action from diagnostic verification state.

        Actions:
        - COLLECT_MORE_EVIDENCE: if diagnosis is INSUFFICIENT_EVIDENCE, or verification disproved
          (NOT_SUPPORTED) or inconclusive (INCONCLUSIVE).
        - VERIFY_ROOT_CAUSE: if verification has not yet been started or is in progress.
        - NO_CANONICAL_QUESTION: if probe questions or repair questions cannot be found in APPROVED bank.
        - PRACTICE_REPAIR: if at least one root cause target was SUPPORTED and a canonical repair
          question is retrieved from the approved question bank.
        """
        student = self.session.get(StudentProfile, student_id)
        if student is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile not found.")

        diagnosis = self.session.scalar(
            select(RootCauseDiagnosis)
            .options(
                selectinload(RootCauseDiagnosis.candidates),
                selectinload(RootCauseDiagnosis.verifications)
                .selectinload(RootCauseVerification.targets)
                .selectinload(RootCauseVerificationTarget.items),
            )
            .where(RootCauseDiagnosis.id == diagnosis_id)
        )
        if diagnosis is None:
            raise ApplicationError(404, "DIAGNOSIS_NOT_FOUND", "Diagnosis not found.")
        if diagnosis.student_id != student_id:
            raise ApplicationError(403, "DIAGNOSIS_ACCESS_DENIED", "Access denied to diagnosis.")

        # 1. Non-verifiable hypothesis
        if diagnosis.diagnosis_type == RootCauseDiagnosisType.INSUFFICIENT_EVIDENCE:
            return RootCauseNextActionRead(
                diagnosis_id=diagnosis_id,
                action=NextDiagnosticActionType.COLLECT_MORE_EVIDENCE,
                reason="Diagnosis has insufficient evidence to establish a verifiable root cause hypothesis.",
            )

        # 2. Check verification session
        verifications = sorted(
            diagnosis.verifications, key=lambda v: v.created_at, reverse=True
        )
        if not verifications:
            return RootCauseNextActionRead(
                diagnosis_id=diagnosis_id,
                action=NextDiagnosticActionType.VERIFY_ROOT_CAUSE,
                reason="Root cause hypothesis has not been empirically verified yet.",
            )

        latest_verification = verifications[0]

        if latest_verification.status == RootCauseVerificationStatus.UNAVAILABLE:
            return RootCauseNextActionRead(
                diagnosis_id=diagnosis_id,
                action=NextDiagnosticActionType.NO_CANONICAL_QUESTION,
                reason="No canonical questions available in question bank to verify this hypothesis.",
            )

        if latest_verification.status in {
            RootCauseVerificationStatus.PENDING,
            RootCauseVerificationStatus.ACTIVE,
        }:
            return RootCauseNextActionRead(
                diagnosis_id=diagnosis_id,
                action=NextDiagnosticActionType.VERIFY_ROOT_CAUSE,
                reason="Root cause verification is currently in progress.",
            )

        # 3. Verification is COMPLETED: inspect targets
        supported_targets = [
            t
            for t in sorted(latest_verification.targets, key=lambda t: t.priority_order)
            if t.outcome == RootCauseVerificationOutcome.SUPPORTED
        ]

        if supported_targets:
            primary_target = supported_targets[0]
            target_name, target_code = self._resolve_target_name_and_code(primary_target)

            verified_read = VerifiedTargetRead(
                target_type=primary_target.target_type,
                target_concept_id=primary_target.target_concept_id,
                target_problem_type_id=primary_target.target_problem_type_id,
                target_name=target_name,
                target_code=target_code,
                outcome=primary_target.outcome,
            )

            # Build exclusion set: all probes used in this session + diagnosis source question
            excluded_qids: set[UUID] = {
                item.question_id
                for target in latest_verification.targets
                for item in target.items
            }
            diag_source_qid = self.exposure_service.get_diagnosis_source_question_id(diagnosis)
            if diag_source_qid is not None:
                excluded_qids.add(diag_source_qid)

            recommended = self.recommendation_service.recommend_for_verified_root_cause(
                student_id=student_id,
                subject_id=diagnosis.subject_id,
                target_concept_id=primary_target.target_concept_id,
                target_problem_type_id=primary_target.target_problem_type_id,
                exclude_question_ids=excluded_qids,
            )

            if recommended is not None:
                return RootCauseNextActionRead(
                    diagnosis_id=diagnosis_id,
                    action=NextDiagnosticActionType.PRACTICE_REPAIR,
                    reason="Root cause target has been empirically verified. Proceed with targeted repair practice.",
                    verified_target=verified_read,
                    recommended_question=recommended,
                )

            return RootCauseNextActionRead(
                diagnosis_id=diagnosis_id,
                action=NextDiagnosticActionType.NO_CANONICAL_QUESTION,
                reason="Root cause target verified, but no canonical repair question available in question bank.",
                verified_target=verified_read,
            )

        # If all targets were NOT_SUPPORTED
        if all(
            t.outcome == RootCauseVerificationOutcome.NOT_SUPPORTED
            for t in latest_verification.targets
        ):
            return RootCauseNextActionRead(
                diagnosis_id=diagnosis_id,
                action=NextDiagnosticActionType.COLLECT_MORE_EVIDENCE,
                reason="Root cause hypothesis was disproved by verification probes. Resume standard learning progression.",
            )

        # Otherwise at least one target was INCONCLUSIVE
        return RootCauseNextActionRead(
            diagnosis_id=diagnosis_id,
            action=NextDiagnosticActionType.COLLECT_MORE_EVIDENCE,
            reason="Verification probes yielded inconclusive results. More practice evidence is needed.",
        )

    def _resolve_target_name_and_code(
        self, target: RootCauseVerificationTarget
    ) -> tuple[str | None, str | None]:
        if target.target_concept_id is not None:
            c = self.session.get(Concept, target.target_concept_id)
            if c:
                return c.name, c.code
        if target.target_problem_type_id is not None:
            pt = self.session.get(ProblemType, target.target_problem_type_id)
            if pt:
                return pt.name, pt.code
        return None, None
