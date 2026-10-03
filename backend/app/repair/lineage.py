from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.knowledge_gap.models import RootCauseDiagnosis, RootCauseVerification, RootCauseVerificationTarget
from app.questions.exposure import QuestionExposureService
from app.repair.models import AdaptiveRepairItem, AdaptiveRepairSession


class RepairLineageExposureService:
    """Track repair session history, lineage, and question exposure across repair cycles."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.exposure = QuestionExposureService(session)

    def get_repair_lineage(self, verification_target_id: UUID) -> list[AdaptiveRepairSession]:
        """Fetch all adaptive repair sessions for a verified target, ordered by cycle index."""
        return list(
            self.session.scalars(
                select(AdaptiveRepairSession)
                .where(AdaptiveRepairSession.verification_target_id == verification_target_id)
                .order_by(AdaptiveRepairSession.repair_cycle_index.asc())
            )
        )

    def get_lineage_excluded_question_ids(
        self,
        *,
        verification_target_id: UUID,
        student_id: UUID,
        diagnosis_id: UUID | None = None,
        verification_id: UUID | None = None,
    ) -> set[UUID]:
        """Collect all questions previously exposed across the entire repair target lineage.

        Includes:
        - All questions used in any repair session in this verification target lineage (cycle 1, cycle 2, etc.)
        - All verification probe questions for this verification
        - The diagnosis source question (if any)
        - Recent general exposures for the student (up to limit 20)
        """
        excluded: set[UUID] = set()

        # 1. Questions from all sessions in this target lineage
        sessions = self.get_repair_lineage(verification_target_id)
        if sessions:
            session_ids = [s.id for s in sessions]
            repair_qids = self.session.scalars(
                select(AdaptiveRepairItem.question_id).where(
                    AdaptiveRepairItem.adaptive_repair_session_id.in_(session_ids)
                )
            ).all()
            excluded.update(repair_qids)

        # 2. Verification probes
        if verification_id is not None:
            verification = self.session.scalar(
                select(RootCauseVerification)
                .options(selectinload(RootCauseVerification.targets).selectinload(RootCauseVerificationTarget.items))
                .where(RootCauseVerification.id == verification_id)
            )
            if verification is not None:
                for target in verification.targets:
                    for item in target.items:
                        excluded.add(item.question_id)

        # 3. Diagnosis source question
        if diagnosis_id is not None:
            diagnosis = self.session.get(RootCauseDiagnosis, diagnosis_id)
            if diagnosis is not None:
                source_q = self.exposure.get_diagnosis_source_question_id(diagnosis)
                if source_q is not None:
                    excluded.add(source_q)

        # 4. Recent student exposures
        recent_qids = self.exposure.get_recent_exposed_question_ids(student_id)
        excluded.update(recent_qids)

        return excluded
