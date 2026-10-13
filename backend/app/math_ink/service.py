"""Student-owned per-page ink persistence, separate from assessed solution steps."""
from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID
import json
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignments.models import Assignment, AssignmentStatus, StudentAssignment, StudentAssignmentStatus
from app.core.exceptions import ApplicationError
from app.math_ink.codec import encode_strokes, decode_strokes
from app.math_ink.models import MathInkDocument, MathInkOperation, MathInkPage
from app.math_ink.schemas import InkDocumentRead, InkPageRead, InkPageSummary, InkPageWrite, InkSaveRead
from app.math_solutions.service import MathSolutionService, _utc


class MathInkService:
    def __init__(self, session: Session):
        self.session = session

    def _attempt(self, actor_user_id: UUID, attempt_id: UUID, *, lock: bool = False):
        return MathSolutionService(self.session)._attempt(actor_user_id, attempt_id, lock=lock)

    def _editable(self, attempt) -> None:
        if attempt.status not in ("DRAFT", "IN_PROGRESS"):
            raise ApplicationError(409, "INK_LOCKED", "This solution is read only.")
        if attempt.context_type != "CLASSROOM_ASSIGNMENT":
            return
        assignment = self.session.get(Assignment, attempt.assignment_id) if attempt.assignment_id else None
        student_assignment = self.session.get(StudentAssignment, attempt.student_assignment_id) if attempt.student_assignment_id else None
        now = datetime.now(timezone.utc)
        if assignment is None or assignment.status != AssignmentStatus.PUBLISHED:
            raise ApplicationError(409, "ASSIGNMENT_NOT_OPEN", "This assignment is not open.")
        if assignment.start_at and _utc(assignment.start_at) > now:
            raise ApplicationError(409, "ASSIGNMENT_NOT_OPEN", "This assignment is not open yet.")
        if assignment.due_at and _utc(assignment.due_at) < now:
            raise ApplicationError(409, "ASSIGNMENT_OUTSIDE_WINDOW", "This assignment has expired.")
        if student_assignment is None or student_assignment.status in (StudentAssignmentStatus.SUBMITTED, StudentAssignmentStatus.GRADED):
            raise ApplicationError(409, "ASSIGNMENT_ALREADY_SUBMITTED", "This assignment is read only.")

    def get_document(self, actor_user_id: UUID, attempt_id: UUID) -> InkDocumentRead:
        self._attempt(actor_user_id, attempt_id)
        doc = self.session.scalar(select(MathInkDocument).where(MathInkDocument.attempt_id == attempt_id))
        if doc is None:
            return InkDocumentRead(document_revision=0, pages=[])
        rows = self.session.scalars(select(MathInkPage).where(MathInkPage.document_id == doc.id).order_by(MathInkPage.page_index)).all()
        return InkDocumentRead(document_revision=doc.revision, pages=[
            InkPageSummary(page_index=p.page_index, stroke_count=p.stroke_count, point_count=p.point_count, sha256=p.sha256) for p in rows
        ])

    def get_page(self, actor_user_id: UUID, attempt_id: UUID, page_index: int) -> InkPageRead:
        self._attempt(actor_user_id, attempt_id)
        doc = self.session.scalar(select(MathInkDocument).where(MathInkDocument.attempt_id == attempt_id))
        if doc is None:
            return InkPageRead(document_revision=0, page_index=page_index, strokes=[])
        page = self.session.scalar(select(MathInkPage).where(MathInkPage.document_id == doc.id, MathInkPage.page_index == page_index))
        return InkPageRead(document_revision=doc.revision, page_index=page_index, strokes=decode_strokes(page.compressed_strokes) if page else [])

    def save_page(self, actor_user_id: UUID, attempt_id: UUID, page_index: int, payload: InkPageWrite) -> InkSaveRead:
        compressed, content_hash, point_count = encode_strokes(payload.strokes)
        request_hash = sha256(json.dumps({
            "page": page_index, "revision": payload.expected_document_revision, "hash": content_hash,
        }, sort_keys=True).encode()).hexdigest()
        try:
            attempt = self._attempt(actor_user_id, attempt_id, lock=True)
            doc = self.session.scalar(select(MathInkDocument).where(MathInkDocument.attempt_id == attempt_id).with_for_update())
            if doc:
                prior = self.session.scalar(select(MathInkOperation).where(
                    MathInkOperation.document_id == doc.id,
                    MathInkOperation.client_action_id == payload.client_action_id,
                ))
                if prior:
                    if prior.actor_user_id != actor_user_id or prior.request_hash != request_hash:
                        raise ApplicationError(409, "INK_ACTION_REUSED", "Action ID already belongs to another update.")
                    return InkSaveRead(document_revision=prior.result_revision, page_index=prior.page_index, sha256=content_hash)
            self._editable(attempt)
            current = doc.revision if doc else 0
            if current != payload.expected_document_revision:
                raise ApplicationError(409, "INK_REVISION_CONFLICT", "Reload ink document before saving again.")
            if doc is None:
                doc = MathInkDocument(attempt_id=attempt_id, revision=1)
                self.session.add(doc)
                self.session.flush()
            else:
                doc.revision += 1
            page = self.session.scalar(select(MathInkPage).where(MathInkPage.document_id == doc.id, MathInkPage.page_index == page_index))
            if page is None:
                page = MathInkPage(document_id=doc.id, page_index=page_index)
                self.session.add(page)
            page.compressed_strokes = compressed
            page.sha256 = content_hash
            page.stroke_count = len(payload.strokes)
            page.point_count = point_count
            self.session.add(MathInkOperation(
                document_id=doc.id, actor_user_id=actor_user_id, client_action_id=payload.client_action_id,
                request_hash=request_hash, page_index=page_index, result_revision=doc.revision,
            ))
            result = InkSaveRead(document_revision=doc.revision, page_index=page_index, sha256=content_hash)
            self.session.commit()
            return result
        except Exception:
            self.session.rollback()
            raise
