from uuid import UUID
from sqlalchemy.orm import Session
from app.core.exceptions import ApplicationError
from app.math_ink.service import MathInkService
from app.math_ocr.adapter import MathOCRAdapter
from app.math_ocr.schemas import OCRRecognizeRequest, OCRRecognizeResponse
from app.math_solutions.models import SolutionAttempt
from app.students.models import StudentProfile


def _fail(status_code: int, code: str, message: str) -> ApplicationError:
    return ApplicationError(status_code, code, message)


class MathOCRService:
    def __init__(self, session: Session, adapter: MathOCRAdapter) -> None:
        self.session = session
        self.adapter = adapter

    def recognize_page_ink(
        self,
        actor_user_id: UUID,
        attempt_id: UUID,
        req: OCRRecognizeRequest,
    ) -> OCRRecognizeResponse:
        student = self.session.query(StudentProfile).filter_by(user_id=actor_user_id).first()
        if not student:
            raise _fail(403, "NOT_A_STUDENT", "User does not have an active student profile.")

        attempt = self.session.get(SolutionAttempt, attempt_id)
        if not attempt:
            raise _fail(404, "ATTEMPT_NOT_FOUND", "Solution attempt not found.")

        if attempt.student_id != student.id:
            raise _fail(404, "ATTEMPT_NOT_FOUND", "Solution attempt not found.")

        # Load page strokes from MathInkService
        ink_service = MathInkService(self.session)
        page_read = ink_service.get_page(actor_user_id, attempt_id, req.page_index)

        strokes = page_read.strokes
        if req.stroke_ids is not None:
            id_set = set(req.stroke_ids)
            strokes = [s for s in strokes if s.id in id_set]

        if not strokes:
            raise _fail(
                422,
                "NO_STROKES_FOR_OCR",
                "Không tìm thấy nét vẽ nào trên trang này để thực hiện nhận diện.",
            )

        return self.adapter.recognize(strokes, hint_topic=req.hint_topic)
