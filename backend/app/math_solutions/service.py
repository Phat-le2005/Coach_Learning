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
from sqlalchemy.orm import Session

from app.assignments.models import (
    Assignment, AssignmentMaterialItem, AssignmentStatus, AssignmentStudentQuestion,
    StudentAssignment, StudentAssignmentMaterialItem, StudentAssignmentStatus,
)
from app.classes.models import EnrollmentStatus, StudentEnrollment
from app.core.exceptions import ApplicationError
from app.math_solutions.models import (
    MathArtifact, SolutionAttempt, SolutionOperation, SolutionRubric,
    SolutionStep, StepRevision,
)
from app.math_solutions.schemas import SolutionStepDraft
from app.practice.models import PracticeSession, PracticeSessionStatus
from app.questions.models import Question, QuestionStatus
from app.students.models import StudentProfile
from app.teacher_materials.models import TeacherMaterial, TeacherMaterialItem


def _fail(status: int, code: str, message: str) -> ApplicationError:
    return ApplicationError(status, code, message)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


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
            now = datetime.now(timezone.utc)
            if _utc(assignment.start_at) > now or (
                assignment.due_at is not None and _utc(assignment.due_at) < now
            ):
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
                    assignment.due_at and _utc(assignment.due_at) < datetime.now(timezone.utc)
                ):
                    raise _fail(409, "ASSIGNMENT_NOT_OPEN", "Cannot submit after the assignment is closed.")
            attempt.status = "SUBMITTED"
            attempt.submitted_at = datetime.now(timezone.utc)
        return self._apply(actor_user_id, attempt_id,
            expected_attempt_revision=expected_attempt_revision, client_action_id=client_action_id,
            operation="SUBMIT", payload={}, callback=action)
