import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.assignments.models import Assignment
from app.classes.models import Classroom, TeacherClassroom
from app.core.errors import ApplicationError
from app.mastery.evidence import DeterministicMasteryEvidencePublisher
from app.math_solutions.evidence_adapter import MathSolutionEvidenceAdapter, WeightedConceptEvidence, WeightedProblemTypeEvidence
from app.math_solutions.models import (
    EvaluationDecision,
    EvaluationOverride,
    SolutionAttempt,
    SolutionStep,
    StepEvaluation,
    StepRevision,
)
from app.math_solutions.teacher_grading_schemas import (
    AttemptGradingDetail,
    BatchApproveRequest,
    BatchApproveResponse,
    BatchApproveResultItem,
    GradingQueueItem,
    OverrideHistoryItem,
    PaginatedGradingQueue,
    RetrySyncResponse,
    StepDetail,
    StepEvaluationDetail,
    TeacherOverrideRequest,
    TeacherOverrideResponse,
)
from app.questions.models import Question
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile
from app.users.models import User

logger = logging.getLogger(__name__)


class TeacherGradingService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _get_teacher_classroom_ids(self, teacher_user_id: UUID) -> set[UUID]:
        classroom_ids = set(
            self.session.scalars(
                select(Classroom.id).where(Classroom.created_by == teacher_user_id)
            ).all()
        )
        teacher = self.session.scalar(
            select(TeacherProfile).where(TeacherProfile.user_id == teacher_user_id)
        )
        if teacher:
            assigned = self.session.scalars(
                select(TeacherClassroom.classroom_id).where(
                    TeacherClassroom.teacher_id == teacher.id
                )
            ).all()
            classroom_ids.update(assigned)
        return classroom_ids

    def _verify_attempt_access(self, teacher_user_id: UUID, attempt: SolutionAttempt) -> None:
        allowed_classrooms = self._get_teacher_classroom_ids(teacher_user_id)
        if attempt.assignment_id:
            assignment = self.session.get(Assignment, attempt.assignment_id)
            if assignment and assignment.classroom_id in allowed_classrooms:
                return
        raise ApplicationError(403, "FORBIDDEN", "Teacher does not have access to this student submission.")

    def list_queue(
        self,
        teacher_user_id: UUID,
        *,
        classroom_id: UUID | None = None,
        assignment_id: UUID | None = None,
        status_filter: str | None = "PENDING",
        page: int = 1,
        size: int = 20,
    ) -> PaginatedGradingQueue:
        allowed_classrooms = self._get_teacher_classroom_ids(teacher_user_id)
        if classroom_id:
            if classroom_id not in allowed_classrooms:
                raise ApplicationError(403, "FORBIDDEN", "Classroom not accessible.")
            target_classrooms = {classroom_id}
        else:
            target_classrooms = allowed_classrooms

        if not target_classrooms:
            return PaginatedGradingQueue(items=[], total=0, page=page, size=size, total_pages=0, pending_count=0)

        # Base query for attempts in assignments for allowed classrooms
        stmt = (
            select(SolutionAttempt, Assignment, Classroom, StudentProfile, User)
            .join(Assignment, SolutionAttempt.assignment_id == Assignment.id)
            .join(Classroom, Assignment.classroom_id == Classroom.id)
            .join(StudentProfile, SolutionAttempt.student_id == StudentProfile.id)
            .join(User, StudentProfile.user_id == User.id)
            .where(
                Assignment.classroom_id.in_(target_classrooms),
                SolutionAttempt.status.in_(("SUBMITTED", "EVALUATED")),
            )
        )
        if assignment_id:
            stmt = stmt.where(SolutionAttempt.assignment_id == assignment_id)

        rows = self.session.execute(stmt.order_by(SolutionAttempt.submitted_at.desc().nullslast(), SolutionAttempt.id.desc())).all()

        queue_items: list[GradingQueueItem] = []
        pending_count = 0

        for attempt, assignment, classroom, student, user in rows:
            decision = self.session.scalar(
                select(EvaluationDecision).where(EvaluationDecision.attempt_id == attempt.id)
            )
            overrides_count = (
                self.session.scalar(
                    select(func.count(EvaluationOverride.id)).where(
                        EvaluationOverride.decision_id == decision.id
                    )
                )
                or 0
                if decision
                else 0
            )

            # Check steps
            steps = self.session.scalars(
                select(SolutionStep).where(
                    SolutionStep.attempt_id == attempt.id,
                    SolutionStep.is_deleted == False,
                )
            ).all()
            step_count = len(steps)
            unverified_count = 0

            for step in steps:
                rev = self.session.scalar(
                    select(StepRevision)
                    .where(StepRevision.step_id == step.id)
                    .order_by(StepRevision.step_revision_number.desc())
                )
                if rev:
                    eval_step = self.session.scalar(
                        select(StepEvaluation)
                        .where(StepEvaluation.step_revision_id == rev.id)
                        .order_by(StepEvaluation.evaluated_at.desc())
                    )
                    if eval_step and (
                        eval_step.math_validity in ("NEEDS_REVIEW", "UNDETERMINED")
                        or (eval_step.confidence is not None and eval_step.confidence < 0.85)
                    ):
                        unverified_count += 1

            # Determine item status
            needs_teacher_review = False
            if overrides_count > 0:
                item_status = "OVERRIDDEN"
            elif decision and decision.decision_source == "TEACHER_REVIEW":
                item_status = "EVALUATED"
            elif decision and decision.decision_source == "AUTOMATED_CONSENSUS":
                if unverified_count > 0:
                    item_status = "PENDING_REVIEW"
                    needs_teacher_review = True
                else:
                    item_status = "EVALUATED"
            else:
                item_status = "PENDING_REVIEW"
                needs_teacher_review = True

            if needs_teacher_review or item_status == "PENDING_REVIEW":
                pending_count += 1

            # Filter by status_filter
            if status_filter == "PENDING" and item_status not in ("PENDING_REVIEW", "PROVISIONAL_AI") and not needs_teacher_review:
                continue
            if status_filter == "EVALUATED" and item_status not in ("EVALUATED", "OVERRIDDEN"):
                continue

            q_title = None
            if attempt.question_id:
                q = self.session.get(Question, attempt.question_id)
                q_title = (q.content[:80] + "...") if q and len(q.content) > 80 else (q.content if q else None)

            queue_items.append(
                GradingQueueItem(
                    attempt_id=attempt.id,
                    student_id=attempt.student_id,
                    student_name=user.full_name,
                    assignment_id=assignment.id,
                    assignment_title=assignment.title,
                    classroom_id=classroom.id,
                    classroom_name=classroom.name,
                    question_id=attempt.question_id,
                    question_title=q_title,
                    submitted_at=attempt.submitted_at,
                    status=item_status,
                    provisional_score=attempt.total_score,
                    final_score=decision.final_score if decision else attempt.total_score,
                    is_correct=decision.is_correct if decision else attempt.is_correct,
                    step_count=step_count,
                    unverified_steps_count=unverified_count,
                    needs_teacher_review=needs_teacher_review,
                    review_source=decision.decision_source if decision else None,
                    decision_id=decision.id if decision else None,
                )
            )

        total = len(queue_items)
        total_pages = (total + size - 1) // size if total > 0 else 0
        paged_items = queue_items[(page - 1) * size : page * size]

        return PaginatedGradingQueue(
            items=paged_items,
            total=total,
            page=page,
            size=size,
            total_pages=total_pages,
            pending_count=pending_count,
        )

    def get_attempt_detail(self, teacher_user_id: UUID, attempt_id: UUID) -> AttemptGradingDetail:
        attempt = self.session.get(SolutionAttempt, attempt_id)
        if not attempt:
            raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Solution attempt not found.")
        self._verify_attempt_access(teacher_user_id, attempt)

        student = self.session.get(StudentProfile, attempt.student_id)
        user = self.session.get(User, student.user_id) if student else None
        assignment = self.session.get(Assignment, attempt.assignment_id) if attempt.assignment_id else None
        classroom = self.session.get(Classroom, assignment.classroom_id) if assignment else None
        question = self.session.get(Question, attempt.question_id) if attempt.question_id else None

        decision = self.session.scalar(
            select(EvaluationDecision).where(EvaluationDecision.attempt_id == attempt.id)
        )
        overrides: list[OverrideHistoryItem] = []
        if decision:
            override_records = self.session.scalars(
                select(EvaluationOverride)
                .where(EvaluationOverride.decision_id == decision.id)
                .order_by(EvaluationOverride.override_version.desc())
            ).all()
            for ov in override_records:
                overrides.append(
                    OverrideHistoryItem(
                        override_id=ov.id,
                        override_version=ov.override_version,
                        previous_score=ov.previous_score,
                        new_score=ov.new_score,
                        previous_is_correct=ov.previous_is_correct,
                        new_is_correct=ov.new_is_correct,
                        reason=ov.override_reason,
                        created_at=ov.created_at,
                    )
                )

        # Steps
        steps_db = self.session.scalars(
            select(SolutionStep)
            .where(SolutionStep.attempt_id == attempt.id, SolutionStep.is_deleted == False)
            .order_by(SolutionStep.step_index)
        ).all()

        step_details: list[StepDetail] = []
        for s in steps_db:
            rev = self.session.scalar(
                select(StepRevision)
                .where(StepRevision.step_id == s.id)
                .order_by(StepRevision.step_revision_number.desc())
            )
            step_eval = None
            if rev:
                se = self.session.scalar(
                    select(StepEvaluation)
                    .where(StepEvaluation.step_revision_id == rev.id)
                    .order_by(StepEvaluation.evaluated_at.desc())
                )
                if se:
                    step_eval = StepEvaluationDetail(
                        math_validity=se.math_validity,
                        score=se.score,
                        confidence=se.confidence,
                        error_detected=se.error_detected,
                        error_description=se.error_description,
                    )
            step_details.append(
                StepDetail(
                    step_id=s.id,
                    step_index=s.step_index,
                    step_type=s.step_type,
                    content_latex=rev.content_latex if rev else s.content_latex,
                    explanation_text=rev.explanation_text if rev else s.explanation_text,
                    evaluation=step_eval,
                )
            )

        status = "PENDING_REVIEW"
        if len(overrides) > 0:
            status = "OVERRIDDEN"
        elif decision and decision.decision_source == "TEACHER_REVIEW":
            status = "EVALUATED"
        elif decision:
            status = "EVALUATED"

        return AttemptGradingDetail(
            attempt_id=attempt.id,
            student_id=attempt.student_id,
            student_name=user.full_name if user else "Học sinh",
            assignment_id=assignment.id if assignment else None,
            assignment_title=assignment.title if assignment else None,
            classroom_id=classroom.id if classroom else None,
            classroom_name=classroom.name if classroom else None,
            question_id=question.id if question else None,
            question_title=(question.content[:80] + "...") if question and len(question.content) > 80 else (question.content if question else None),
            question_latex=question.content if question else None,
            submitted_at=attempt.submitted_at,
            steps=step_details,
            status=status,
            provisional_score=attempt.total_score,
            final_score=decision.final_score if decision else attempt.total_score,
            is_correct=decision.is_correct if decision else attempt.is_correct,
            decision_source=decision.decision_source if decision else None,
            decision_id=decision.id if decision else None,
            sync_status="SYNCED",
            overrides=overrides,
        )

    def batch_approve(
        self, teacher_user_id: UUID, request: BatchApproveRequest
    ) -> BatchApproveResponse:
        results: list[BatchApproveResultItem] = []
        approved_count = 0
        failed_count = 0

        for attempt_id in request.attempt_ids:
            attempt = self.session.get(SolutionAttempt, attempt_id)
            if not attempt:
                results.append(
                    BatchApproveResultItem(attempt_id=attempt_id, status="FAILED", message="Attempt not found.")
                )
                failed_count += 1
                continue

            try:
                self._verify_attempt_access(teacher_user_id, attempt)
            except Exception as e:
                results.append(
                    BatchApproveResultItem(attempt_id=attempt_id, status="FAILED", message=str(e))
                )
                failed_count += 1
                continue

            decision = self.session.scalar(
                select(EvaluationDecision).where(EvaluationDecision.attempt_id == attempt.id)
            )
            adapter = MathSolutionEvidenceAdapter(self.session)
            now = datetime.now(timezone.utc)

            if decision is None:
                score = attempt.total_score if attempt.total_score is not None else 1.0
                is_correct = score >= 0.85
                decision = EvaluationDecision(
                    id=uuid4(),
                    attempt_id=attempt.id,
                    rubric_id=attempt.rubric_id,
                    decision_source="TEACHER_REVIEW",
                    final_score=score,
                    is_correct=is_correct,
                    confirmed_misconceptions=[],
                    learning_evidence_event_id=None,
                    decided_by=teacher_user_id,
                    decided_at=now,
                )
                self.session.add(decision)
                attempt.status = "EVALUATED"
                attempt.total_score = score
                attempt.is_correct = is_correct
                attempt.evaluated_at = now
                self.session.flush()

                adapter.emit_evidence_for_decision(decision.id)
            else:
                decision.decision_source = "TEACHER_REVIEW"
                decision.decided_by = teacher_user_id
                decision.decided_at = now
                attempt.status = "EVALUATED"
                self.session.flush()

                if decision.learning_evidence_event_id is None:
                    adapter.emit_evidence_for_decision(decision.id)
                else:
                    pt_ids, concept_ids = self._resolve_target_skills(attempt)
                    DeterministicMasteryEvidencePublisher.recalculate_student_mastery(
                        self.session, attempt.student_id, pt_ids, concept_ids
                    )

            results.append(
                BatchApproveResultItem(
                    attempt_id=attempt.id,
                    status="APPROVED",
                    score=decision.final_score,
                    message="Official teacher approval recorded and mastery synchronized.",
                )
            )
            approved_count += 1

        if hasattr(self.session, "commit"):
            self.session.commit()

        return BatchApproveResponse(
            approved_count=approved_count,
            failed_count=failed_count,
            results=results,
        )

    def override_attempt(
        self, teacher_user_id: UUID, attempt_id: UUID, request: TeacherOverrideRequest
    ) -> TeacherOverrideResponse:
        attempt = self.session.get(SolutionAttempt, attempt_id)
        if not attempt:
            raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Solution attempt not found.")
        self._verify_attempt_access(teacher_user_id, attempt)

        decision = self.session.scalar(
            select(EvaluationDecision).where(EvaluationDecision.attempt_id == attempt.id)
        )
        adapter = MathSolutionEvidenceAdapter(self.session)
        now = datetime.now(timezone.utc)

        if decision is None:
            decision = EvaluationDecision(
                id=uuid4(),
                attempt_id=attempt.id,
                rubric_id=attempt.rubric_id,
                decision_source="TEACHER_REVIEW",
                final_score=request.new_score,
                is_correct=request.new_is_correct,
                confirmed_misconceptions=[],
                learning_evidence_event_id=None,
                decided_by=teacher_user_id,
                decided_at=now,
            )
            self.session.add(decision)
            attempt.status = "EVALUATED"
            attempt.total_score = request.new_score
            attempt.is_correct = request.new_is_correct
            attempt.evaluated_at = now
            self.session.flush()

            adapter.emit_evidence_for_decision(decision.id)

            override = EvaluationOverride(
                id=uuid4(),
                decision_id=decision.id,
                teacher_id=teacher_user_id,
                override_version=1,
                previous_score=0.0,
                new_score=request.new_score,
                previous_is_correct=False,
                new_is_correct=request.new_is_correct,
                override_reason=request.reason,
                projection_status="APPLIED",
                created_at=now,
            )
            self.session.add(override)
            self.session.flush()
        else:
            override = adapter.apply_teacher_override(
                decision_id=decision.id,
                teacher_id=teacher_user_id,
                new_score=request.new_score,
                new_is_correct=request.new_is_correct,
                reason=request.reason,
            )

        if hasattr(self.session, "commit"):
            self.session.commit()

        return TeacherOverrideResponse(
            attempt_id=attempt.id,
            decision_id=decision.id,
            override_id=override.id,
            previous_score=override.previous_score,
            new_score=override.new_score,
            new_is_correct=override.new_is_correct,
            sync_status="SYNCED",
        )

    def retry_sync(self, teacher_user_id: UUID, attempt_id: UUID) -> RetrySyncResponse:
        attempt = self.session.get(SolutionAttempt, attempt_id)
        if not attempt:
            raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Solution attempt not found.")
        self._verify_attempt_access(teacher_user_id, attempt)

        pt_ids, concept_ids = self._resolve_target_skills(attempt)
        DeterministicMasteryEvidencePublisher().recalculate_student_mastery(
            self.session,
            attempt.student_id,
            problem_type_ids=pt_ids,
            concept_ids=concept_ids,
        )

        try:
            with self.session.begin_nested():
                from app.planning.study_service import StudyPlanService
                StudyPlanService(self.session).recalculate_study_plan(attempt.student_id)
        except Exception:
            logger.debug("Study plan recalculation skipped during retry-sync", exc_info=True)

        if hasattr(self.session, "commit"):
            self.session.commit()

        return RetrySyncResponse(
            attempt_id=attempt.id,
            student_id=attempt.student_id,
            sync_status="SYNCED",
            affected_skills=len(pt_ids) + len(concept_ids),
            recalculated_at=datetime.now(timezone.utc),
        )

    def _resolve_target_skills(self, attempt: SolutionAttempt) -> tuple[set[UUID], set[UUID]]:
        pt_ids: set[UUID] = set()
        concept_ids: set[UUID] = set()
        if attempt.question_id:
            q = self.session.scalar(
                select(Question)
                .options(selectinload(Question.concept_links), selectinload(Question.problem_type_links))
                .where(Question.id == attempt.question_id)
            )
            if q:
                for cl in q.concept_links:
                    concept_ids.add(cl.concept_id)
                for ptl in q.problem_type_links:
                    pt_ids.add(ptl.problem_type_id)
        return pt_ids, concept_ids
