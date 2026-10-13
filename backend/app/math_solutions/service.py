"""Transactional, student-owned step-by-step solution lifecycle (STEP-CORE-01).

No OpenAPI routes and no learning-evidence publishing here. All mutations lock the
attempt, verify actor ownership, use optimistic revisions and a per-attempt action
journal. Commit/rollback boundaries belong to this service.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.assignments.models import (
    Assignment, AssignmentMaterialItem, AssignmentQuestion, AssignmentStatus,
    AssignmentStudentQuestion, AssignmentType,
    StudentAssignment, StudentAssignmentMaterialItem, StudentAssignmentStatus,
)
from app.assignments.service import AssignmentService
from app.classes.models import EnrollmentStatus, StudentEnrollment
from app.core.exceptions import ApplicationError
from app.math_solutions.models import (
    MathArtifact, SolutionAttempt, SolutionOperation, SolutionRubric,
    SolutionStep, StepRevision,
)
from app.math_solutions.schemas import (
    PaginatedSolutionAttemptsRead,
    PrepareAssignmentResponse,
    ProblemOptionRead,
    ProblemRead,
    ProblemSourceMetadataRead,
    SolutionContext,
    SolutionMode,
    SolutionSourceKind,
    SolutionStepDraft,
)
from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionStatus,
    QuestionAttempt,
)
from app.practice.service import PracticeService
from app.questions.models import Question, QuestionStatus, QuestionType
from app.students.models import StudentProfile
from app.teacher_materials.models import TeacherMaterial, TeacherMaterialItem


def _fail(status: int, code: str, message: str) -> ApplicationError:
    return ApplicationError(status, code, message)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(value: dict[str, Any]) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


class MathSolutionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _student(self, actor_user_id: UUID) -> StudentProfile:
        student = self.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == actor_user_id)
        )
        if student is None:
            raise _fail(403, "STUDENT_ROLE_REQUIRED", "A student account is required.")
        return student

    def _attempt(self, actor_user_id: UUID, attempt_id: UUID, *, lock: bool) -> SolutionAttempt:
        student = self._student(actor_user_id)
        query = select(SolutionAttempt).where(
            SolutionAttempt.id == attempt_id, SolutionAttempt.student_id == student.id
        )
        if lock:
            query = query.with_for_update()
        attempt = self.session.scalar(query)
        if attempt is None:
            raise _fail(404, "SOLUTION_ATTEMPT_NOT_FOUND", "Solution attempt not found.")
        return attempt

    def _active_steps(self, attempt_id: UUID) -> list[SolutionStep]:
        return list(self.session.scalars(
            select(SolutionStep).where(
                SolutionStep.attempt_id == attempt_id, SolutionStep.is_deleted.is_(False)
            ).order_by(SolutionStep.step_index, SolutionStep.id)
        ).all())

    def _step(self, attempt_id: UUID, step_id: UUID, *, include_deleted: bool = False) -> SolutionStep:
        step = self.session.get(SolutionStep, step_id)
        if step is None or step.attempt_id != attempt_id or (step.is_deleted and not include_deleted):
            raise _fail(404, "SOLUTION_STEP_NOT_FOUND", "Solution step not found.")
        return step

    def _latest_revision(self, step_id: UUID) -> StepRevision | None:
        return self.session.scalar(
            select(StepRevision).where(StepRevision.step_id == step_id)
            .order_by(StepRevision.step_revision_number.desc()).limit(1)
        )

    def _record_step_revision(
        self, step: SolutionStep, reason: str, artifact: dict[str, Any] | None
    ) -> StepRevision:
        latest = self._latest_revision(step.id)
        row = StepRevision(
            step_id=step.id,
            step_revision_number=1 if latest is None else latest.step_revision_number + 1,
            step_index_at_revision=step.step_index,
            content_latex=step.content_latex,
            explanation_text=step.explanation_text,
            artifact_snapshot=artifact,
            change_reason=reason,
        )
        self.session.add(row)
        self.session.flush()
        if artifact is not None:
            self.session.add(MathArtifact(
                step_revision_id=row.id,
                artifact_type=artifact["artifact_type"],
                payload=artifact["payload"],
            ))
        return row

    def _snapshot(self, attempt: SolutionAttempt) -> dict[str, Any]:
        steps = []
        for step in self._active_steps(attempt.id):
            revision = self._latest_revision(step.id)
            steps.append({
                "id": str(step.id), "step_index": step.step_index,
                "step_type": step.step_type, "content_latex": step.content_latex,
                "explanation_text": step.explanation_text,
                "step_revision_number": revision.step_revision_number if revision else 0,
                "artifact": revision.artifact_snapshot if revision else None,
            })
        return {
            "id": str(attempt.id), "status": attempt.status,
            "context_type": attempt.context_type, "source_kind": attempt.source_kind,
            "mode": attempt.mode, "attempt_revision_number": attempt.attempt_revision_number,
            "question_id": str(attempt.question_id) if attempt.question_id else None,
            "practice_session_id": str(attempt.practice_session_id) if attempt.practice_session_id else None,
            "student_assignment_id": str(attempt.student_assignment_id) if attempt.student_assignment_id else None,
            "assignment_student_question_id": str(attempt.assignment_student_question_id) if attempt.assignment_student_question_id else None,
            "student_assignment_material_item_id": str(attempt.student_assignment_material_item_id) if attempt.student_assignment_material_item_id else None,
            "steps": steps, "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
            "started_at": attempt.started_at.isoformat(),
            "updated_at": attempt.updated_at.isoformat(),
        }

    def get(self, actor_user_id: UUID, attempt_id: UUID) -> dict[str, Any]:
        return self._snapshot(self._attempt(actor_user_id, attempt_id, lock=False))

    def list_revisions(self, actor_user_id: UUID, attempt_id: UUID, step_id: UUID) -> list[dict[str, Any]]:
        attempt = self._attempt(actor_user_id, attempt_id, lock=False)
        step = self._step(attempt.id, step_id, include_deleted=True)
        return [
            {
                "id": str(row.id), "step_revision_number": row.step_revision_number,
                "step_index_at_revision": row.step_index_at_revision,
                "content_latex": row.content_latex, "explanation_text": row.explanation_text,
                "artifact": row.artifact_snapshot, "change_reason": row.change_reason,
                "created_at": row.created_at.isoformat(),
            }
            for row in self.session.scalars(
                select(StepRevision).where(StepRevision.step_id == step.id)
                .order_by(StepRevision.step_revision_number)
            ).all()
        ]

    def create(
        self, actor_user_id: UUID, *, source_kind: str, context_type: str, mode: str,
        create_idempotency_key: str,
        question_id: UUID | None = None, practice_session_id: UUID | None = None,
        student_assignment_id: UUID | None = None,
        assignment_student_question_id: UUID | None = None,
        student_assignment_material_item_id: UUID | None = None,
        rubric_id: UUID | None = None,
    ) -> dict[str, Any]:
        student = self._student(actor_user_id)
        if not create_idempotency_key or len(create_idempotency_key) > 100:
            raise _fail(422, "INVALID_IDEMPOTENCY_KEY", "A stable create key is required.")
        existing = self.session.scalar(
            select(SolutionAttempt).where(
                SolutionAttempt.student_id == student.id,
                SolutionAttempt.create_idempotency_key == create_idempotency_key,
            ).with_for_update()
        )
        if existing is not None:
            # Reuse is safe only for same requested source; reject cross-request reuse.
            if (
                existing.context_type != context_type or existing.source_kind != source_kind
                or existing.mode != mode or
                existing.question_id != question_id or
                existing.practice_session_id != practice_session_id or
                existing.student_assignment_id != student_assignment_id or
                existing.assignment_student_question_id != assignment_student_question_id or
                existing.student_assignment_material_item_id != student_assignment_material_item_id or
                existing.rubric_id != rubric_id
            ):
                raise _fail(409, "CREATE_KEY_REUSED", "This create key already belongs to another request.")
            return self._snapshot(existing)

        if mode not in ("GUIDED_LEARNING", "INDEPENDENT_SOLUTION"):
            raise _fail(422, "INVALID_SOLUTION_MODE", "Invalid solution mode.")
        if context_type not in ("SELF_PRACTICE", "CLASSROOM_ASSIGNMENT"):
            raise _fail(422, "INVALID_SOLUTION_CONTEXT", "Invalid solution context.")
        if source_kind not in ("CANONICAL", "TEACHER_MATERIAL"):
            raise _fail(422, "INVALID_SOLUTION_SOURCE", "Invalid solution source.")

        asg: StudentAssignment | None = None
        material_id: UUID | None = None
        if context_type == "SELF_PRACTICE":
            if source_kind != "CANONICAL" or question_id is None or practice_session_id is None or (
                student_assignment_id or assignment_student_question_id or student_assignment_material_item_id
            ):
                raise _fail(422, "INVALID_SOLUTION_SOURCE", "Self practice requires a canonical question and practice session.")
            practice = self.session.get(PracticeSession, practice_session_id)
            if practice is None or practice.student_id != student.id or practice.status != PracticeSessionStatus.ACTIVE:
                raise _fail(403, "PRACTICE_SESSION_NOT_ACCESSIBLE", "The practice session is not active for this student.")
        else:
            if practice_session_id is not None or student_assignment_id is None:
                raise _fail(422, "INVALID_SOLUTION_CONTEXT", "A classroom solution requires a student assignment.")
            # Lock parent to prevent two concurrent first-attempt creations for one item.
            asg = self.session.scalar(
                select(StudentAssignment).where(
                    StudentAssignment.id == student_assignment_id,
                    StudentAssignment.student_id == student.id,
                ).with_for_update()
            )
            if asg is None:
                raise _fail(403, "ASSIGNMENT_NOT_ACCESSIBLE", "No matching assigned work.")
            assignment = self.session.get(Assignment, asg.assignment_id)
            if assignment is None or assignment.status != AssignmentStatus.PUBLISHED or asg.status in (
                StudentAssignmentStatus.SUBMITTED, StudentAssignmentStatus.GRADED
            ):
                raise _fail(409, "ASSIGNMENT_NOT_OPEN", "The assignment is not available for writing.")
            now = _now()
            if assignment.start_at and _utc(assignment.start_at) > now:
                raise _fail(409, "ASSIGNMENT_NOT_OPEN", "Assignment is not open yet.")
            if assignment.due_at is not None and _utc(assignment.due_at) < now:
                raise _fail(409, "ASSIGNMENT_OUTSIDE_WINDOW", "The assignment is outside its submission window.")
            enrolled = self.session.scalar(
                select(StudentEnrollment).where(
                    StudentEnrollment.student_id == student.id,
                    StudentEnrollment.classroom_id == assignment.classroom_id,
                    StudentEnrollment.status == EnrollmentStatus.ACTIVE,
                )
            )
            if enrolled is None:
                raise _fail(403, "CLASSROOM_MEMBERSHIP_REQUIRED", "Student is not actively enrolled.")
            if source_kind == "CANONICAL":
                if question_id is None or assignment_student_question_id is None or student_assignment_material_item_id is not None:
                    raise _fail(422, "INVALID_SOLUTION_SOURCE", "Canonical assigned work requires its assigned question.")
                item = self.session.get(AssignmentStudentQuestion, assignment_student_question_id)
                if item is None or item.student_assignment_id != asg.id or item.question_id != question_id:
                    raise _fail(403, "ASSIGNMENT_QUESTION_NOT_ACCESSIBLE", "The question is not assigned to this student.")
            else:
                if question_id is not None or assignment_student_question_id is not None or student_assignment_material_item_id is None:
                    raise _fail(422, "INVALID_SOLUTION_SOURCE", "Teacher material requires its assigned snapshot item.")
                item = self.session.get(StudentAssignmentMaterialItem, student_assignment_material_item_id)
                if item is None or item.student_assignment_id != asg.id:
                    raise _fail(403, "MATERIAL_ITEM_NOT_ACCESSIBLE", "The material is not assigned to this student.")
                snapshot = self.session.get(AssignmentMaterialItem, item.assignment_material_item_id)
                if snapshot is None or snapshot.assignment_id != assignment.id:
                    raise _fail(409, "MATERIAL_SNAPSHOT_MISMATCH", "Material snapshot does not match its assignment.")
                if snapshot.teacher_material_item_id != item.teacher_material_item_id:
                    raise _fail(409, "MATERIAL_ITEM_SNAPSHOT_MISMATCH", "Assigned item and snapshot do not have the same source.")
                origin = self.session.get(TeacherMaterialItem, item.teacher_material_item_id)
                material = self.session.get(TeacherMaterial, origin.teacher_material_id) if origin is not None else None
                if (
                    material is None or material.classroom_id != assignment.classroom_id
                    or material.subject_id != assignment.subject_id
                    or (snapshot.teacher_material_id is not None and snapshot.teacher_material_id != material.id)
                ):
                    raise _fail(403, "MATERIAL_SOURCE_NOT_ACCESSIBLE", "Source document belongs to a different classroom.")
                material_id = snapshot.id

        q = self.session.get(Question, question_id) if question_id else None
        if source_kind == "CANONICAL":
            if q is None or q.status != QuestionStatus.APPROVED:
                raise _fail(422, "QUESTION_NOT_APPROVED", "The canonical question is not approved.")
            if context_type == "SELF_PRACTICE" and q.subject_id != practice.subject_id:
                raise _fail(422, "SUBJECT_MISMATCH", "Question and practice subject must match.")
            if asg is not None and q.subject_id != assignment.subject_id:
                raise _fail(422, "SUBJECT_MISMATCH", "Question and assignment subject must match.")
        if rubric_id is not None:
            rubric = self.session.get(SolutionRubric, rubric_id)
            if rubric is None or rubric.status != "APPROVED" or (
                source_kind == "CANONICAL" and (rubric.question_id != question_id or rubric.assignment_material_item_id is not None)
            ) or (
                source_kind == "TEACHER_MATERIAL" and (rubric.assignment_material_item_id != material_id or rubric.question_id is not None)
            ):
                raise _fail(422, "RUBRIC_NOT_APPROVED_FOR_SOURCE", "Rubric does not match an approved source.")

        if asg is not None:
            target = (
                (SolutionAttempt.assignment_student_question_id == assignment_student_question_id)
                if source_kind == "CANONICAL" else
                (SolutionAttempt.student_assignment_material_item_id == student_assignment_material_item_id)
            )
            previous = self.session.scalar(
                select(SolutionAttempt).where(
                    SolutionAttempt.student_assignment_id == asg.id, target
                ).order_by(SolutionAttempt.started_at.desc()).limit(1)
            )
            if previous is not None:
                # Existing classroom item is immutable: never silently switch modes or rubrics.
                if previous.mode != mode or previous.rubric_id != rubric_id:
                    raise _fail(409, "SOLUTION_CONFIGURATION_CONFLICT", "Existing assigned solution has a different mode or rubric.")
                return self._snapshot(previous)
        row = SolutionAttempt(
            student_id=student.id, source_kind=source_kind, context_type=context_type,
            question_id=question_id, assignment_material_item_id=material_id,
            student_assignment_material_item_id=student_assignment_material_item_id,
            assignment_student_question_id=assignment_student_question_id,
            practice_session_id=practice_session_id, assignment_id=asg.assignment_id if asg else None,
            student_assignment_id=asg.id if asg else None,
            rubric_id=rubric_id, mode=mode, status="DRAFT",
            create_idempotency_key=create_idempotency_key,
            attempt_revision_number=1,
        )
        try:
            self.session.add(row)
            self.session.flush()
            snapshot = self._snapshot(row)
            self.session.commit()
            return snapshot
        except Exception:
            self.session.rollback()
            raise

    def _apply(
        self, actor_user_id: UUID, attempt_id: UUID,
        *, expected_attempt_revision: int, client_action_id: UUID,
        operation: str, payload: dict[str, Any],
        callback: Callable[[SolutionAttempt], None],
    ) -> dict[str, Any]:
        try:
            attempt = self._attempt(actor_user_id, attempt_id, lock=True)
            digest = _digest({"operation": operation, "revision": expected_attempt_revision, "payload": payload})
            prior = self.session.scalar(
                select(SolutionOperation).where(
                    SolutionOperation.attempt_id == attempt.id,
                    SolutionOperation.client_action_id == client_action_id,
                )
            )
            if prior is not None:
                if prior.request_hash != digest or prior.operation_type != operation or prior.actor_user_id != actor_user_id:
                    raise _fail(409, "ACTION_KEY_REUSED", "Action key used for a different operation.")
                return prior.response_snapshot
            if attempt.status not in ("DRAFT", "IN_PROGRESS"):
                raise _fail(409, "SOLUTION_LOCKED", "Solution cannot be modified after submission.")
            if attempt.context_type == "CLASSROOM_ASSIGNMENT":
                if attempt.assignment_id is not None:
                    assignment = self.session.get(Assignment, attempt.assignment_id)
                    if assignment is not None:
                        now = _now()
                        if assignment.status != AssignmentStatus.PUBLISHED:
                            raise _fail(409, "ASSIGNMENT_NOT_OPEN", "The assignment is not open.")
                        if assignment.start_at and _utc(assignment.start_at) > now:
                            raise _fail(409, "ASSIGNMENT_NOT_OPEN", "Assignment is not open yet.")
                        if assignment.due_at is not None and _utc(assignment.due_at) < now:
                            raise _fail(409, "ASSIGNMENT_OUTSIDE_WINDOW", "The assignment is outside its submission window.")
                if attempt.student_assignment_id is not None:
                    sa = self.session.get(StudentAssignment, attempt.student_assignment_id)
                    if sa is not None and sa.status in (StudentAssignmentStatus.SUBMITTED, StudentAssignmentStatus.GRADED):
                        raise _fail(409, "ASSIGNMENT_ALREADY_SUBMITTED", "Assignment has already been submitted.")
            if attempt.attempt_revision_number != expected_attempt_revision:
                raise _fail(409, "SOLUTION_REVISION_CONFLICT", "Reload the latest solution before retrying.")
            callback(attempt)
            self.session.flush()
            attempt.attempt_revision_number += 1
            if operation != "SUBMIT":
                attempt.status = "IN_PROGRESS"
            self.session.flush()
            response = self._snapshot(attempt)
            self.session.add(SolutionOperation(
                attempt_id=attempt.id, actor_user_id=actor_user_id,
                client_action_id=client_action_id, operation_type=operation,
                request_hash=digest, result_attempt_revision=attempt.attempt_revision_number,
                response_snapshot=response,
            ))
            self.session.commit()
            return response
        except Exception:
            self.session.rollback()
            raise

    def add_step(self, actor_user_id: UUID, attempt_id: UUID, *,
                 expected_attempt_revision: int, client_action_id: UUID,
                 draft: SolutionStepDraft) -> dict[str, Any]:
        content = draft.model_dump(mode="json")
        def action(attempt: SolutionAttempt) -> None:
            active = self._active_steps(attempt.id)
            next_index = max((s.step_index for s in active), default=0) + 1
            step = SolutionStep(
                attempt_id=attempt.id, step_index=next_index,
                step_type=content["step_type"], content_latex=content["content_latex"],
                explanation_text=content["explanation_text"],
                status="ACTIVE", is_deleted=False,
            )
            self.session.add(step)
            self.session.flush()
            self._record_step_revision(step, "STUDENT_EDIT", content["artifact"])
        return self._apply(actor_user_id, attempt_id,
            expected_attempt_revision=expected_attempt_revision,
            client_action_id=client_action_id, operation="ADD_STEP", payload=content, callback=action)

    def update_step(self, actor_user_id: UUID, attempt_id: UUID, step_id: UUID, *,
                    expected_attempt_revision: int, client_action_id: UUID,
                    draft: SolutionStepDraft) -> dict[str, Any]:
        content = draft.model_dump(mode="json")
        def action(attempt: SolutionAttempt) -> None:
            step = self._step(attempt.id, step_id)
            step.step_type = content["step_type"]
            step.content_latex = content["content_latex"]
            step.explanation_text = content["explanation_text"]
            self._record_step_revision(step, "AUTOSAVE", content["artifact"])
        return self._apply(actor_user_id, attempt_id,
            expected_attempt_revision=expected_attempt_revision, client_action_id=client_action_id,
            operation="UPDATE_STEP", payload={"step_id": str(step_id), **content}, callback=action)

    def _reindex(self, attempt_id: UUID, desired: list[SolutionStep], *, reason: str) -> None:
        if not desired:
            return
        # The attempt row is locked by _apply. Reserve temporary indices beyond
        # all current indices, INCLUDING tombstones, to avoid any collision.
        highest = self.session.scalar(select(func.max(SolutionStep.step_index)).where(SolutionStep.attempt_id == attempt_id)) or 0
        temp_base = highest + len(desired) + 1
        previous = {step.id: self._latest_revision(step.id) for step in desired}
        for i, step in enumerate(desired, start=1):
            step.step_index = temp_base + i
        self.session.flush()
        for i, step in enumerate(desired, start=1):
            step.step_index = i
        self.session.flush()
        for step in desired:
            old = previous[step.id]
            self._record_step_revision(step, reason, old.artifact_snapshot if old else None)

    def reorder_steps(self, actor_user_id: UUID, attempt_id: UUID, *,
                      expected_attempt_revision: int, client_action_id: UUID,
                      step_ids: list[UUID]) -> dict[str, Any]:
        def action(attempt: SolutionAttempt) -> None:
            active = self._active_steps(attempt.id)
            if len(step_ids) != len(active) or len(set(step_ids)) != len(step_ids) or set(step_ids) != {s.id for s in active}:
                raise _fail(422, "INVALID_STEP_ORDER", "Step order must contain every active step exactly once.")
            lookup = {s.id: s for s in active}
            self._reindex(attempt.id, [lookup[sid] for sid in step_ids], reason="STUDENT_REORDER")
        return self._apply(actor_user_id, attempt_id,
            expected_attempt_revision=expected_attempt_revision, client_action_id=client_action_id,
            operation="REORDER_STEPS", payload={"step_ids": [str(x) for x in step_ids]}, callback=action)

    def delete_step(self, actor_user_id: UUID, attempt_id: UUID, step_id: UUID, *,
                    expected_attempt_revision: int, client_action_id: UUID) -> dict[str, Any]:
        def action(attempt: SolutionAttempt) -> None:
            step = self._step(attempt.id, step_id)
            artifact = self._latest_revision(step.id)
            step.is_deleted = True
            step.status = "DELETED"
            self.session.flush()
            self._record_step_revision(step, "STUDENT_DELETE", artifact.artifact_snapshot if artifact else None)
            self._reindex(attempt.id, self._active_steps(attempt.id), reason="STUDENT_REORDER")
        return self._apply(actor_user_id, attempt_id,
            expected_attempt_revision=expected_attempt_revision, client_action_id=client_action_id,
            operation="DELETE_STEP", payload={"step_id": str(step_id)}, callback=action)

    def restore_step(self, actor_user_id: UUID, attempt_id: UUID, step_id: UUID, *,
                     expected_attempt_revision: int, client_action_id: UUID) -> dict[str, Any]:
        def action(attempt: SolutionAttempt) -> None:
            step = self._step(attempt.id, step_id, include_deleted=True)
            if not step.is_deleted:
                raise _fail(409, "STEP_NOT_DELETED", "Step has not been deleted.")
            current = self._latest_revision(step.id)
            step.step_index = max((s.step_index for s in self._active_steps(attempt.id)), default=0) + 1
            step.is_deleted = False
            step.status = "ACTIVE"
            self.session.flush()
            self._record_step_revision(step, "STUDENT_RESTORE", current.artifact_snapshot if current else None)
        return self._apply(actor_user_id, attempt_id,
            expected_attempt_revision=expected_attempt_revision, client_action_id=client_action_id,
            operation="RESTORE_STEP", payload={"step_id": str(step_id)}, callback=action)

    def rollback_step(self, actor_user_id: UUID, attempt_id: UUID, step_id: UUID, *,
                      to_revision: int, expected_attempt_revision: int, client_action_id: UUID) -> dict[str, Any]:
        def action(attempt: SolutionAttempt) -> None:
            step = self._step(attempt.id, step_id)
            target = self.session.scalar(
                select(StepRevision).where(
                    StepRevision.step_id == step.id, StepRevision.step_revision_number == to_revision
                )
            )
            if target is None:
                raise _fail(404, "SOLUTION_REVISION_NOT_FOUND", "Step revision not found.")
            step.content_latex = target.content_latex
            step.explanation_text = target.explanation_text
            self._record_step_revision(step, "ROLLBACK", target.artifact_snapshot)
        return self._apply(actor_user_id, attempt_id,
            expected_attempt_revision=expected_attempt_revision, client_action_id=client_action_id,
            operation="ROLLBACK_STEP", payload={"step_id": str(step_id), "to_revision": to_revision},
            callback=action)

    def submit(self, actor_user_id: UUID, attempt_id: UUID, *,
               expected_attempt_revision: int, client_action_id: UUID) -> dict[str, Any]:
        def action(attempt: SolutionAttempt) -> None:
            if not self._active_steps(attempt.id):
                raise _fail(422, "EMPTY_SOLUTION", "Enter at least one solution step before submitting.")
            if attempt.context_type == "CLASSROOM_ASSIGNMENT":
                assignment = self.session.get(Assignment, attempt.assignment_id)
                if assignment is None or assignment.status != AssignmentStatus.PUBLISHED or (
                    assignment.due_at and _utc(assignment.due_at) < _now()
                ):
                    raise _fail(409, "ASSIGNMENT_NOT_OPEN", "Cannot submit after the assignment is closed.")
            attempt.status = "SUBMITTED"
            attempt.submitted_at = _now()
        return self._apply(actor_user_id, attempt_id,
            expected_attempt_revision=expected_attempt_revision, client_action_id=client_action_id,
            operation="SUBMIT", payload={}, callback=action)

    def list_attempts(
        self,
        actor_user_id: UUID,
        *,
        page: int = 1,
        size: int = 20,
        question_id: UUID | None = None,
        practice_session_id: UUID | None = None,
        student_assignment_id: UUID | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        student = self._student(actor_user_id)
        stmt = select(SolutionAttempt).where(SolutionAttempt.student_id == student.id)
        if question_id is not None:
            stmt = stmt.where(SolutionAttempt.question_id == question_id)
        if practice_session_id is not None:
            stmt = stmt.where(SolutionAttempt.practice_session_id == practice_session_id)
        if student_assignment_id is not None:
            stmt = stmt.where(SolutionAttempt.student_assignment_id == student_assignment_id)
        if status is not None:
            stmt = stmt.where(SolutionAttempt.status == status)

        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        stmt = stmt.order_by(SolutionAttempt.updated_at.desc(), SolutionAttempt.id.desc())
        stmt = stmt.offset((page - 1) * size).limit(size)
        attempts = list(self.session.scalars(stmt).all())
        total_pages = (total + size - 1) // size if total > 0 else 0
        return {
            "items": [self._snapshot(a) for a in attempts],
            "total": total,
            "page": page,
            "size": size,
            "total_pages": total_pages,
        }

    def get_attempt_problem(self, actor_user_id: UUID, attempt_id: UUID) -> ProblemRead:
        attempt = self._attempt(actor_user_id, attempt_id, lock=False)
        is_read_only = attempt.status in ("SUBMITTED", "EVALUATED", "ABANDONED")
        if not is_read_only and attempt.context_type == "CLASSROOM_ASSIGNMENT":
            assignment = self.session.get(Assignment, attempt.assignment_id) if attempt.assignment_id else None
            if assignment is not None:
                if assignment.status != AssignmentStatus.PUBLISHED:
                    is_read_only = True
                elif assignment.due_at and _utc(assignment.due_at) < _now():
                    is_read_only = True
            student_assignment = self.session.get(StudentAssignment, attempt.student_assignment_id) if attempt.student_assignment_id else None
            if student_assignment is not None and student_assignment.status in (
                StudentAssignmentStatus.SUBMITTED,
                StudentAssignmentStatus.GRADED,
            ):
                is_read_only = True
        elif not is_read_only and attempt.context_type == "SELF_PRACTICE":
            session_obj = self.session.get(PracticeSession, attempt.practice_session_id) if attempt.practice_session_id else None
            if session_obj is not None and session_obj.status in (
                PracticeSessionStatus.COMPLETED,
                PracticeSessionStatus.ABANDONED,
            ):
                is_read_only = True

        if attempt.source_kind == "CANONICAL":
            if attempt.question_id is None:
                raise _fail(404, "QUESTION_NOT_FOUND", "Attempt does not reference a valid question.")
            question = self.session.scalar(
                select(Question)
                .options(selectinload(Question.options))
                .where(
                    Question.id == attempt.question_id,
                    Question.status == QuestionStatus.APPROVED,
                )
            )
            if question is None:
                raise _fail(404, "QUESTION_NOT_FOUND", "Question not found or is not approved.")
            order_index = None
            if attempt.assignment_student_question_id is not None:
                asq = self.session.get(AssignmentStudentQuestion, attempt.assignment_student_question_id)
                if asq is not None:
                    order_index = asq.order_index
            options = [
                ProblemOptionRead(
                    id=opt.id,
                    label=opt.label,
                    content=opt.content,
                    order_index=opt.order_index,
                )
                for opt in sorted(question.options, key=lambda o: o.order_index)
            ]
            return ProblemRead(
                id=question.id,
                source_kind=SolutionSourceKind.CANONICAL,
                context_type=SolutionContext(attempt.context_type),
                content=question.content,
                question_type=question.question_type,
                options=options,
                order_index=order_index,
                is_read_only=is_read_only,
                question_id=question.id,
                practice_session_id=attempt.practice_session_id,
                assignment_id=attempt.assignment_id,
                student_assignment_id=attempt.student_assignment_id,
                assignment_student_question_id=attempt.assignment_student_question_id,
                student_assignment_material_item_id=None,
                source_metadata=None,
            )
        elif attempt.source_kind == "TEACHER_MATERIAL":
            if attempt.student_assignment_material_item_id is None:
                raise _fail(404, "MATERIAL_ITEM_NOT_FOUND", "Attempt does not reference a valid material item.")
            sami = self.session.scalar(
                select(StudentAssignmentMaterialItem).where(
                    StudentAssignmentMaterialItem.id == attempt.student_assignment_material_item_id,
                    StudentAssignmentMaterialItem.student_assignment_id == attempt.student_assignment_id,
                )
            )
            if sami is None:
                raise _fail(404, "MATERIAL_ITEM_NOT_FOUND", "Student assignment material item not found.")
            ami = self.session.scalar(
                select(AssignmentMaterialItem)
                .options(
                    selectinload(AssignmentMaterialItem.options),
                    selectinload(AssignmentMaterialItem.teacher_material_item),
                    selectinload(AssignmentMaterialItem.assignment),
                )
                .where(AssignmentMaterialItem.id == sami.assignment_material_item_id)
            )
            if ami is None or ami.content is None:
                raise _fail(404, "MATERIAL_ITEM_NOT_FOUND", "Assignment material snapshot not found.")
            if attempt.assignment_id is not None and ami.assignment_id != attempt.assignment_id:
                raise _fail(409, "MATERIAL_SNAPSHOT_MISMATCH", "Material snapshot does not match assignment.")
            if ami.teacher_material_item_id != sami.teacher_material_item_id:
                raise _fail(409, "MATERIAL_ITEM_SNAPSHOT_MISMATCH", "Assigned item and snapshot origin do not match.")
            tmi = ami.teacher_material_item
            tm = self.session.get(TeacherMaterial, ami.teacher_material_id) if ami.teacher_material_id else None
            title = tm.title if tm is not None else (ami.assignment.title if ami.assignment is not None else None)
            subject_id = tm.subject_id if tm is not None else (ami.assignment.subject_id if ami.assignment is not None else None)
            meta = ProblemSourceMetadataRead(
                title=title,
                subject_id=subject_id,
                grade_level=None,
                page_start=tmi.page_start if tmi is not None else None,
                page_end=tmi.page_end if tmi is not None else None,
            )
            options = [
                ProblemOptionRead(
                    id=opt.id,
                    label=opt.label,
                    content=opt.content,
                    order_index=opt.order_index,
                )
                for opt in sorted(ami.options, key=lambda o: o.order_index)
            ]
            return ProblemRead(
                id=sami.id,
                source_kind=SolutionSourceKind.TEACHER_MATERIAL,
                context_type=SolutionContext(attempt.context_type),
                content=ami.content,
                question_type=ami.question_type or QuestionType.OPEN_RESPONSE,
                options=options,
                order_index=sami.order_index,
                is_read_only=is_read_only,
                question_id=None,
                practice_session_id=None,
                assignment_id=attempt.assignment_id,
                student_assignment_id=attempt.student_assignment_id,
                assignment_student_question_id=None,
                student_assignment_material_item_id=sami.id,
                source_metadata=meta,
            )
        else:
            raise _fail(422, "INVALID_SOURCE_KIND", f"Unsupported source kind: {attempt.source_kind}")

    def get_practice_next_problem(self, actor_user_id: UUID, session_id: UUID) -> ProblemRead:
        student = self._student(actor_user_id)
        practice_session = self.session.scalar(
            select(PracticeSession).where(
                PracticeSession.id == session_id,
                PracticeSession.student_id == student.id,
            )
        )
        if practice_session is None:
            raise _fail(404, "PRACTICE_SESSION_NOT_FOUND", "Practice session not found.")
        if practice_session.status != PracticeSessionStatus.ACTIVE:
            raise _fail(409, "PRACTICE_SESSION_NOT_ACTIVE", "Practice session is not active.")

        practice_svc = PracticeService(self.session)
        stmt = practice_svc._eligible_questions(practice_session, exclude_attempted=True)
        stmt = stmt.where(
            ~Question.id.in_(
                select(SolutionAttempt.question_id).where(
                    SolutionAttempt.practice_session_id == practice_session.id,
                    SolutionAttempt.question_id.is_not(None),
                )
            )
        )
        question = self.session.scalar(stmt.limit(1))
        if question is None:
            group_stmt = practice_svc._eligible_groups(practice_session, exclude_attempted=True)
            has_groups = self.session.scalar(select(group_stmt.subquery()).limit(1)) is not None
            if has_groups:
                raise _fail(422, "QUESTION_GROUP_NOT_SUPPORTED", "Question groups are not supported in individual Math Workspace.")
            raise _fail(404, "NO_QUESTIONS_AVAILABLE", "No eligible questions available in this practice session.")

        options = [
            ProblemOptionRead(
                id=opt.id,
                label=opt.label,
                content=opt.content,
                order_index=opt.order_index,
            )
            for opt in sorted(question.options, key=lambda o: o.order_index)
        ]
        return ProblemRead(
            id=question.id,
            source_kind=SolutionSourceKind.CANONICAL,
            context_type=SolutionContext.SELF_PRACTICE,
            content=question.content,
            question_type=question.question_type,
            options=options,
            order_index=None,
            is_read_only=False,
            question_id=question.id,
            practice_session_id=practice_session.id,
            assignment_id=None,
            student_assignment_id=None,
            assignment_student_question_id=None,
            student_assignment_material_item_id=None,
            source_metadata=None,
        )

    def prepare_student_assignment(self, actor_user_id: UUID, student_assignment_id: UUID) -> PrepareAssignmentResponse:
        student = self._student(actor_user_id)
        try:
            sa = self.session.scalar(
                select(StudentAssignment)
                .where(
                    StudentAssignment.id == student_assignment_id,
                    StudentAssignment.student_id == student.id,
                )
                .with_for_update()
            )
            if sa is None:
                raise _fail(404, "STUDENT_ASSIGNMENT_NOT_FOUND", "Student assignment not found.")

            assignment = self.session.get(Assignment, sa.assignment_id)
            if assignment is None:
                raise _fail(404, "ASSIGNMENT_NOT_FOUND", "Assignment not found.")

            if assignment.status != AssignmentStatus.PUBLISHED:
                raise _fail(409, "ASSIGNMENT_NOT_PUBLISHED", "Assignment is not published.")

            enrollment = self.session.scalar(
                select(StudentEnrollment).where(
                    StudentEnrollment.classroom_id == assignment.classroom_id,
                    StudentEnrollment.student_id == student.id,
                    StudentEnrollment.status == EnrollmentStatus.ACTIVE,
                )
            )
            if enrollment is None:
                raise _fail(403, "NOT_ENROLLED_IN_CLASSROOM", "Student is not enrolled in this classroom.")

            now = _now()
            if assignment.start_at and _utc(assignment.start_at) > now:
                raise _fail(409, "ASSIGNMENT_NOT_OPEN", "Assignment is not open yet.")

            if assignment.due_at is not None and _utc(assignment.due_at) < now:
                raise _fail(409, "ASSIGNMENT_OUTSIDE_WINDOW", "The assignment is outside its submission window.")

            if sa.status in (StudentAssignmentStatus.SUBMITTED, StudentAssignmentStatus.GRADED):
                raise _fail(409, "ASSIGNMENT_ALREADY_SUBMITTED", "Assignment is already submitted.")

            existing_qs = self.session.scalars(
                select(AssignmentStudentQuestion)
                .where(AssignmentStudentQuestion.student_assignment_id == sa.id)
                .order_by(AssignmentStudentQuestion.order_index)
            ).all()
            existing_mis = self.session.scalars(
                select(StudentAssignmentMaterialItem)
                .where(StudentAssignmentMaterialItem.student_assignment_id == sa.id)
                .order_by(StudentAssignmentMaterialItem.order_index)
            ).all()

            if not existing_qs and not existing_mis:
                if assignment.assignment_type == AssignmentType.SAME_SET:
                    assign_qs = list(self.session.scalars(
                        select(AssignmentQuestion)
                        .where(AssignmentQuestion.assignment_id == assignment.id)
                        .order_by(AssignmentQuestion.order_index)
                    ).all())
                    for idx, aq in enumerate(assign_qs):
                        self.session.add(
                            AssignmentStudentQuestion(
                                student_assignment_id=sa.id,
                                question_id=aq.question_id,
                                order_index=idx,
                            )
                        )
                    assign_items = list(self.session.scalars(
                        select(AssignmentMaterialItem)
                        .where(AssignmentMaterialItem.assignment_id == assignment.id)
                        .order_by(AssignmentMaterialItem.order_index)
                    ).all())
                    for link in assign_items:
                        self.session.add(
                            StudentAssignmentMaterialItem(
                                student_assignment_id=sa.id,
                                teacher_material_item_id=link.teacher_material_item_id,
                                assignment_material_item_id=link.id,
                                order_index=len(assign_qs) + link.order_index,
                                evaluation_status=EvaluationStatus.NEEDS_EVALUATION,
                            )
                        )
                elif assignment.assignment_type == AssignmentType.ADAPTIVE_SET:
                    adaptive_qs = AssignmentService(self.session)._select_adaptive_questions_for_student(
                        student.id, assignment
                    )
                    for idx, q in enumerate(adaptive_qs):
                        self.session.add(
                            AssignmentStudentQuestion(
                                student_assignment_id=sa.id,
                                question_id=q.id,
                                order_index=idx,
                            )
                        )
                if sa.status == StudentAssignmentStatus.NOT_STARTED:
                    sa.status = StudentAssignmentStatus.IN_PROGRESS
                    sa.started_at = _now()
                self.session.flush()

            problems = self._load_student_assignment_problems(student, sa, assignment)
            self.session.commit()
            self.session.refresh(sa)
            return PrepareAssignmentResponse(
                student_assignment_id=sa.id,
                status=sa.status.value if hasattr(sa.status, "value") else str(sa.status),
                item_count=len(problems),
                problems=problems,
            )
        except Exception:
            self.session.rollback()
            raise

    def get_student_assignment_problems(self, actor_user_id: UUID, student_assignment_id: UUID) -> list[ProblemRead]:
        student = self._student(actor_user_id)
        sa = self.session.scalar(
            select(StudentAssignment).where(
                StudentAssignment.id == student_assignment_id,
                StudentAssignment.student_id == student.id,
            )
        )
        if sa is None:
            raise _fail(404, "STUDENT_ASSIGNMENT_NOT_FOUND", "Student assignment not found.")

        assignment = self.session.get(Assignment, sa.assignment_id)
        if assignment is None:
            raise _fail(404, "ASSIGNMENT_NOT_FOUND", "Assignment not found.")

        if assignment.status != AssignmentStatus.PUBLISHED:
            raise _fail(409, "ASSIGNMENT_NOT_PUBLISHED", "Assignment is not published.")

        enrollment = self.session.scalar(
            select(StudentEnrollment).where(
                StudentEnrollment.classroom_id == assignment.classroom_id,
                StudentEnrollment.student_id == student.id,
                StudentEnrollment.status == EnrollmentStatus.ACTIVE,
            )
        )
        if enrollment is None:
            raise _fail(403, "NOT_ENROLLED_IN_CLASSROOM", "Student is not enrolled in this classroom.")

        has_qs = self.session.scalar(
            select(AssignmentStudentQuestion.id).where(
                AssignmentStudentQuestion.student_assignment_id == sa.id
            ).limit(1)
        )
        has_mis = self.session.scalar(
            select(StudentAssignmentMaterialItem.id).where(
                StudentAssignmentMaterialItem.student_assignment_id == sa.id
            ).limit(1)
        )
        if not has_qs and not has_mis:
            raise _fail(409, "ASSIGNMENT_NOT_PREPARED", "Assignment problems have not been prepared yet. Call POST prepare first.")

        return self._load_student_assignment_problems(student, sa, assignment)

    def _load_student_assignment_problems(
        self, student: StudentProfile, sa: StudentAssignment, assignment: Assignment
    ) -> list[ProblemRead]:
        is_read_only = (
            sa.status in (StudentAssignmentStatus.SUBMITTED, StudentAssignmentStatus.GRADED)
            or (assignment.due_at and _utc(assignment.due_at) < _now())
            or assignment.status != AssignmentStatus.PUBLISHED
        )
        sqs = list(self.session.scalars(
            select(AssignmentStudentQuestion)
            .options(
                selectinload(AssignmentStudentQuestion.question).selectinload(Question.options)
            )
            .where(AssignmentStudentQuestion.student_assignment_id == sa.id)
            .order_by(AssignmentStudentQuestion.order_index)
        ).all())

        problems: list[ProblemRead] = []
        for sq in sqs:
            q = sq.question
            if q is None or q.status != QuestionStatus.APPROVED:
                raise _fail(409, "CANONICAL_QUESTION_INVALID", "Assigned question is not approved or no longer available.")
            if q.subject_id != assignment.subject_id:
                raise _fail(422, "SUBJECT_MISMATCH", "Question and assignment subject must match.")
            options = [
                ProblemOptionRead(
                    id=opt.id,
                    label=opt.label,
                    content=opt.content,
                    order_index=opt.order_index,
                )
                for opt in sorted(q.options, key=lambda o: o.order_index)
            ]
            problems.append(
                ProblemRead(
                    id=q.id,
                    source_kind=SolutionSourceKind.CANONICAL,
                    context_type=SolutionContext.CLASSROOM_ASSIGNMENT,
                    content=q.content,
                    question_type=q.question_type,
                    options=options,
                    order_index=sq.order_index,
                    is_read_only=is_read_only,
                    question_id=q.id,
                    practice_session_id=None,
                    assignment_id=assignment.id,
                    student_assignment_id=sa.id,
                    assignment_student_question_id=sq.id,
                    student_assignment_material_item_id=None,
                    source_metadata=None,
                )
            )

        smis = list(self.session.scalars(
            select(StudentAssignmentMaterialItem)
            .options(
                selectinload(StudentAssignmentMaterialItem.assignment_material_item)
                .selectinload(AssignmentMaterialItem.options),
                selectinload(StudentAssignmentMaterialItem.assignment_material_item)
                .selectinload(AssignmentMaterialItem.teacher_material_item),
            )
            .where(StudentAssignmentMaterialItem.student_assignment_id == sa.id)
            .order_by(StudentAssignmentMaterialItem.order_index)
        ).all())

        for smi in smis:
            if smi.student_assignment_id != sa.id:
                raise _fail(403, "MATERIAL_ITEM_NOT_ACCESSIBLE", "Material item is not assigned to this student assignment.")
            ami = smi.assignment_material_item
            if ami is None:
                raise _fail(409, "MATERIAL_SNAPSHOT_INVALID", "Assignment material snapshot not found.")
            if ami.assignment_id != assignment.id:
                raise _fail(409, "MATERIAL_SNAPSHOT_MISMATCH", "Material snapshot does not match its assignment.")
            if ami.teacher_material_item_id != smi.teacher_material_item_id:
                raise _fail(409, "MATERIAL_ITEM_SNAPSHOT_MISMATCH", "Assigned item and snapshot do not have the same source.")
            origin = self.session.get(TeacherMaterialItem, smi.teacher_material_item_id)
            if origin is None:
                raise _fail(409, "MATERIAL_SNAPSHOT_INVALID", "Origin material item not found.")
            material = self.session.get(TeacherMaterial, origin.teacher_material_id) if origin is not None else None
            if (
                material is None or material.classroom_id != assignment.classroom_id
                or material.subject_id != assignment.subject_id
                or (ami.teacher_material_id is not None and ami.teacher_material_id != material.id)
            ):
                raise _fail(403, "MATERIAL_SOURCE_NOT_ACCESSIBLE", "Source document belongs to a different classroom.")
            if not ami.content:
                raise _fail(409, "MATERIAL_SNAPSHOT_INVALID", "Assignment material snapshot content is empty.")
            tmi = ami.teacher_material_item or origin
            tm = material
            title = tm.title if tm is not None else assignment.title
            subject_id = tm.subject_id if tm is not None else assignment.subject_id
            meta = ProblemSourceMetadataRead(
                title=title,
                subject_id=subject_id,
                grade_level=None,
                page_start=tmi.page_start if tmi is not None else None,
                page_end=tmi.page_end if tmi is not None else None,
            )
            options = [
                ProblemOptionRead(
                    id=opt.id,
                    label=opt.label,
                    content=opt.content,
                    order_index=opt.order_index,
                )
                for opt in sorted(ami.options, key=lambda o: o.order_index)
            ]
            problems.append(
                ProblemRead(
                    id=smi.id,
                    source_kind=SolutionSourceKind.TEACHER_MATERIAL,
                    context_type=SolutionContext.CLASSROOM_ASSIGNMENT,
                    content=ami.content,
                    question_type=ami.question_type or QuestionType.OPEN_RESPONSE,
                    options=options,
                    order_index=smi.order_index,
                    is_read_only=is_read_only,
                    question_id=None,
                    practice_session_id=None,
                    assignment_id=assignment.id,
                    student_assignment_id=sa.id,
                    assignment_student_question_id=None,
                    student_assignment_material_item_id=smi.id,
                    source_metadata=meta,
                )
            )

        problems.sort(key=lambda p: (p.order_index is None, p.order_index or 0))
        return problems

