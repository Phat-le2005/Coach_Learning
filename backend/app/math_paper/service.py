"""Store private scans without treating OCR or the image as a graded solution step."""

from io import BytesIO
from hashlib import sha256
from uuid import UUID, uuid4
import warnings

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ApplicationError
from app.math_paper.models import MathPaperAttachment
from app.math_solutions.service import MathSolutionService
from app.question_acquisition.storage import LocalQuestionAcquisitionStorage

MAX_PAPER_BYTES = 10 * 1024 * 1024
MAX_PAPER_FILES = 10


def validate_paper(data: bytes, declared_type: str | None) -> tuple[str, str]:
    if not data or len(data) > MAX_PAPER_BYTES:
        raise ApplicationError(422, "PAPER_SIZE_INVALID", "Paper file must be 1 byte to 10 MB.")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime, extension = "image/png", "png"
    elif data.startswith(b"\xff\xd8\xff"):
        mime, extension = "image/jpeg", "jpg"
    elif data.startswith(b"%PDF-"):
        mime, extension = "application/pdf", "pdf"
    else:
        raise ApplicationError(422, "PAPER_TYPE_INVALID", "Upload a PNG, JPEG or PDF scan.")
    if declared_type and declared_type != "application/octet-stream" and declared_type != mime:
        raise ApplicationError(422, "PAPER_TYPE_INVALID", "File type does not match its contents.")
    try:
        if mime == "application/pdf":
            reader = PdfReader(BytesIO(data), strict=False)
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 30:
                raise ValueError("PDF must have 1 to 30 unencrypted pages")
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    if image.format not in {"PNG", "JPEG"} or not 200 <= image.width <= 8000 or not 200 <= image.height <= 8000 or image.width * image.height > 40_000_000:
                        raise ValueError("Image dimensions are outside the allowed range")
                    image.verify()
    except (ValueError, UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, OSError, PdfReadError, KeyError, TypeError) as exc:
        # Validation never exposes internal parser errors to students.
        raise ApplicationError(422, "PAPER_FILE_INVALID", "Paper file is damaged or exceeds page/dimension limits.") from exc
    return mime, extension


def safe_filename(name: str, extension: str) -> str:
    base = name.replace("\\", "/").split("/")[-1]
    base = "".join(char for char in base if char.isprintable() and char not in {'"', "<", ">", ":", "|", "?", "*"}).strip(" .")
    return (base[:250] or f"paper.{extension}")


class MathPaperService:
    def __init__(self, session: Session, storage: LocalQuestionAcquisitionStorage | None = None) -> None:
        self.session = session
        self.storage = storage or LocalQuestionAcquisitionStorage(get_settings().math_paper_storage_dir)

    def _attempt(self, actor_user_id: UUID, attempt_id: UUID, *, editable: bool = False) -> None:
        solution = MathSolutionService(self.session)
        snapshot = solution.get(actor_user_id, attempt_id)
        if editable and (snapshot["status"] not in {"DRAFT", "IN_PROGRESS"}
                         or solution.get_attempt_problem(actor_user_id, attempt_id).is_read_only):
            raise ApplicationError(409, "PAPER_ATTEMPT_CLOSED", "This attempt no longer accepts paper uploads.")

    @staticmethod
    def to_read(row: MathPaperAttachment) -> dict:
        return {"id": row.id, "file_name": row.file_name, "content_type": row.content_type,
                "size_bytes": row.size_bytes, "sha256": row.sha256, "created_at": row.created_at}

    def list(self, actor_user_id: UUID, attempt_id: UUID) -> list[dict]:
        self._attempt(actor_user_id, attempt_id)
        rows = self.session.scalars(select(MathPaperAttachment).where(
            MathPaperAttachment.attempt_id == attempt_id,
        ).order_by(MathPaperAttachment.created_at, MathPaperAttachment.id)).all()
        return [self.to_read(row) for row in rows]

    def add(self, actor_user_id: UUID, attempt_id: UUID, data: bytes,
            declared_type: str | None, file_name: str) -> dict:
        self._attempt(actor_user_id, attempt_id, editable=True)
        mime, extension = validate_paper(data, declared_type)
        digest = sha256(data).hexdigest()
        existing = self.session.scalar(select(MathPaperAttachment).where(
            MathPaperAttachment.attempt_id == attempt_id, MathPaperAttachment.sha256 == digest,
        ))
        if existing:
            return self.to_read(existing)
        count = self.session.scalar(select(func.count()).select_from(MathPaperAttachment).where(
            MathPaperAttachment.attempt_id == attempt_id,
        )) or 0
        if count >= MAX_PAPER_FILES:
            raise ApplicationError(422, "PAPER_LIMIT_REACHED", "An attempt supports up to 10 paper files.")
        row_id = uuid4()
        key = f"{attempt_id}/{row_id}.{extension}"
        self.storage.save(key, data)
        try:
            row = MathPaperAttachment(id=row_id, attempt_id=attempt_id,
                file_name=safe_filename(file_name, extension), content_type=mime,
                sha256=digest, size_bytes=len(data), storage_key=key)
            self.session.add(row)
            self.session.commit()
            return self.to_read(row)
        except Exception:
            self.session.rollback()
            self.storage.delete(key)
            raise

    def read(self, actor_user_id: UUID, attempt_id: UUID, paper_id: UUID) -> tuple[dict, bytes]:
        self._attempt(actor_user_id, attempt_id)
        row = self.session.scalar(select(MathPaperAttachment).where(
            MathPaperAttachment.id == paper_id, MathPaperAttachment.attempt_id == attempt_id,
        ))
        if row is None:
            raise ApplicationError(404, "PAPER_NOT_FOUND", "Paper file was not found.")
        if not self.storage.exists(row.storage_key):
            raise ApplicationError(503, "PAPER_STORAGE_UNAVAILABLE", "Paper file is temporarily unavailable.")
        data = self.storage.read(row.storage_key)
        if sha256(data).hexdigest() != row.sha256:
            raise ApplicationError(503, "PAPER_INTEGRITY_ERROR", "Paper file failed integrity verification.")
        return self.to_read(row), data

    def delete(self, actor_user_id: UUID, attempt_id: UUID, paper_id: UUID) -> None:
        self._attempt(actor_user_id, attempt_id, editable=True)
        row = self.session.scalar(select(MathPaperAttachment).where(
            MathPaperAttachment.id == paper_id, MathPaperAttachment.attempt_id == attempt_id,
        ))
        if row is None:
            raise ApplicationError(404, "PAPER_NOT_FOUND", "Paper file was not found.")
        key = row.storage_key
        self.session.delete(row)
        self.session.commit()
        self.storage.delete(key)
