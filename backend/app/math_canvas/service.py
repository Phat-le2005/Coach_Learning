import hashlib
import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.classes.models import EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.core.exceptions import ApplicationError
from app.math_canvas.models import MathCanvasExplanation, MathCanvasSnapshot
from app.math_canvas.schemas import GraphSpec, SnapshotCreate, SnapshotRead, ExplanationRead, classify_expression
from app.math_ink.service import MathInkService
from app.math_solutions.models import SolutionAttempt
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile
from app.users.models import User


def fingerprint(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def spec_hash(spec: GraphSpec) -> str:
    settings = spec.settings.model_dump(mode="json")
    if settings.get("scene") is None:
        settings.pop("scene", None)
    if settings.get("lab") is None:
        settings.pop("lab", None)
    # Preserve existing explanation hashes for legacy/default display settings.
    if settings["view_mode"] == "AUTO":
        settings.pop("view_mode")
    if settings["slice_y"] == 0:
        settings.pop("slice_y")
    return fingerprint({"expression": spec.expression, "settings": settings})


class MathCanvasService:
    def __init__(self, session: Session):
        self.session = session

    def owned_attempt(self, user_id: UUID, attempt_id: UUID, *, lock=False) -> SolutionAttempt:
        statement = select(SolutionAttempt).join(StudentProfile, StudentProfile.id == SolutionAttempt.student_id).where(
            SolutionAttempt.id == attempt_id, StudentProfile.user_id == user_id)
        if lock:
            statement = statement.with_for_update()
        attempt = self.session.scalar(statement)
        if attempt is None:
            raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Không tìm thấy bài làm của bạn.")
        return attempt

    def read(self, row: MathCanvasSnapshot) -> SnapshotRead:
        profile = self.session.get(StudentProfile, row.student_id)
        user = self.session.get(User, profile.user_id)
        explanation = self.session.get(MathCanvasExplanation, row.explanation_id) if row.explanation_id else None
        return SnapshotRead(id=row.id, attempt_id=row.attempt_id, student_id=row.student_id, student_name=user.full_name,
            expression=row.expression, dimension=row.dimension, settings=row.settings, camera=row.camera,
            page_index=row.page_index, source_latex=row.source_latex, source_strokes=row.source_strokes,
            source_ink_revision=row.source_ink_revision, note=row.note,
            explanation=ExplanationRead.model_validate(explanation) if explanation else None, created_at=row.created_at)

    def save(self, user_id: UUID, attempt_id: UUID, data: SnapshotCreate) -> SnapshotRead:
        attempt = self.owned_attempt(user_id, attempt_id, lock=True)
        request_data = data.model_dump(mode="json")
        if request_data["settings"].get("scene") is None:
            request_data["settings"].pop("scene", None)
        if request_data["settings"].get("lab") is None:
            request_data["settings"].pop("lab", None)
        digest = fingerprint(request_data)
        existing = self.session.scalar(select(MathCanvasSnapshot).where(MathCanvasSnapshot.attempt_id == attempt_id,
            MathCanvasSnapshot.client_action_id == data.client_action_id))
        if existing:
            if existing.request_hash != digest:
                raise ApplicationError(409, "CANVAS_ACTION_REUSED", "Mã lưu đã được dùng cho nội dung khác.")
            return self.read(existing)
        count = self.session.scalar(select(func.count()).select_from(MathCanvasSnapshot).where(MathCanvasSnapshot.attempt_id == attempt_id))
        if count >= 50:
            raise ApplicationError(409, "CANVAS_SNAPSHOT_LIMIT", "Bài học đã đạt giới hạn 50 bản trực quan hóa.")
        if data.explanation_id:
            explanation = self.session.get(MathCanvasExplanation, data.explanation_id)
            if not explanation or explanation.attempt_id != attempt_id or explanation.spec_hash != spec_hash(data):
                raise ApplicationError(409, "CANVAS_EXPLANATION_STALE", "Hãy tạo giải thích cho bộ tham số hiện tại trước khi lưu.")
        page = MathInkService(self.session).get_page(user_id, attempt_id, data.page_index)
        ids = set(data.stroke_ids)
        selected = [stroke for stroke in page.strokes if stroke.id in ids and stroke.tool == "PEN"]
        if len(selected) != len(ids):
            raise ApplicationError(409, "CANVAS_SELECTION_STALE", "Nét đã chọn đã thay đổi. Hãy khoanh và lưu lại.")
        row = MathCanvasSnapshot(attempt_id=attempt_id, student_id=attempt.student_id, client_action_id=data.client_action_id,
            request_hash=digest, expression=data.expression, dimension=data.settings.lab.dimension if data.settings.lab is not None else classify_expression(data.expression)[0],
            settings=data.settings.model_dump(mode="json"), camera=data.camera.model_dump(mode="json"), page_index=data.page_index,
            source_latex=data.source_latex, source_strokes=[s.model_dump(mode="json") for s in selected],
            source_ink_revision=page.document_revision, note=data.note, explanation_id=data.explanation_id)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return self.read(row)

    def list_student(self, user_id: UUID, attempt_id: UUID) -> list[SnapshotRead]:
        self.owned_attempt(user_id, attempt_id)
        rows = self.session.scalars(select(MathCanvasSnapshot).where(MathCanvasSnapshot.attempt_id == attempt_id)
            .order_by(MathCanvasSnapshot.created_at.desc(), MathCanvasSnapshot.id).limit(50)).all()
        return [self.read(row) for row in rows]

    def list_teacher(self, teacher_user_id: UUID, *, offset: int = 0) -> list[SnapshotRead]:
        # Authorization is reevaluated on every read, including after enrollment revocation.
        accessible = select(StudentEnrollment.student_id).join(TeacherClassroom,
            TeacherClassroom.classroom_id == StudentEnrollment.classroom_id).join(TeacherProfile,
            TeacherProfile.id == TeacherClassroom.teacher_id).where(TeacherProfile.user_id == teacher_user_id,
            StudentEnrollment.status == EnrollmentStatus.ACTIVE)
        rows = self.session.scalars(select(MathCanvasSnapshot).where(MathCanvasSnapshot.student_id.in_(accessible))
            .order_by(MathCanvasSnapshot.created_at.desc(), MathCanvasSnapshot.id).offset(offset).limit(20)).all()
        return [self.read(row) for row in rows]
