import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.curriculum.models import CurriculumVersion
from app.subjects.models import Subject
from app.subjects.schemas import SubjectCreate

logger = logging.getLogger(__name__)


class SubjectService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, subject_id: UUID) -> Subject:
        subject = self.session.get(Subject, subject_id)
        if subject is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject was not found.")
        return subject

    def list_subjects(self, *, offset: int = 0, limit: int = 100) -> list[Subject]:
        if offset < 0 or not 1 <= limit <= 200:
            raise ApplicationError(422, "INVALID_PAGINATION", "Invalid pagination parameters.")
        return list(self.session.scalars(select(Subject).order_by(Subject.code, Subject.id).offset(offset).limit(limit)))

    def create(self, data: SubjectCreate) -> Subject:
        if self.session.get(CurriculumVersion, data.curriculum_version_id) is None:
            raise ApplicationError(
                404, "CURRICULUM_VERSION_NOT_FOUND", "Curriculum version was not found."
            )
        if self._code_exists(data.curriculum_version_id, data.code):
            raise self._duplicate_code()
        subject = Subject(**data.model_dump())
        self.session.add(subject)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            if self._code_exists(data.curriculum_version_id, data.code):
                raise self._duplicate_code() from None
            raise
        self.session.refresh(subject)
        logger.info("Subject created (subject_id=%s)", subject.id)
        return subject

    def _code_exists(self, curriculum_version_id: UUID, code: str) -> bool:
        return self.session.scalar(
            select(Subject.id).where(
                Subject.curriculum_version_id == curriculum_version_id,
                Subject.code == code,
            )
        ) is not None

    @staticmethod
    def _duplicate_code() -> ApplicationError:
        return ApplicationError(409, "SUBJECT_CODE_EXISTS", "Subject code already exists.")
