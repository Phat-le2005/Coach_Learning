import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.concepts.schemas import ConceptCreate, ConceptPatch
from app.core.exceptions import ApplicationError
from app.subjects.service import SubjectService

logger = logging.getLogger(__name__)


class ConceptService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, concept_id: UUID) -> Concept:
        concept = self.session.get(Concept, concept_id)
        if concept is None:
            raise ApplicationError(404, "CONCEPT_NOT_FOUND", "Concept was not found.")
        return concept

    def create(self, data: ConceptCreate) -> Concept:
        SubjectService(self.session).get(data.subject_id)
        self._ensure_unique_code(data.subject_id, data.code)
        concept = Concept(**data.model_dump())
        self.session.add(concept)
        return self._save(concept, data.subject_id, data.code)

    def update(self, concept_id: UUID, data: ConceptPatch) -> Concept:
        # Serialize updates to a concept so concurrent patches preserve untouched fields.
        concept = self.session.scalar(select(Concept).where(Concept.id == concept_id).with_for_update().execution_options(populate_existing=True))
        if concept is None:
            raise ApplicationError(404, "CONCEPT_NOT_FOUND", "Concept was not found.")
        updates = data.model_dump(exclude_unset=True)
        if not updates:
            return concept
        subject_id = data.subject_id if data.subject_id is not None else concept.subject_id
        code = data.code if data.code is not None else concept.code
        SubjectService(self.session).get(subject_id)
        self._ensure_unique_code(subject_id, code, excluding=concept.id)
        for field, value in updates.items():
            setattr(concept, field, value)
        return self._save(concept, subject_id, code)

    def _ensure_unique_code(self, subject_id: UUID, code: str, *, excluding: UUID | None = None) -> None:
        query = select(Concept.id).where(Concept.subject_id == subject_id, Concept.code == code)
        if excluding is not None:
            query = query.where(Concept.id != excluding)
        if self.session.scalar(query) is not None:
            raise ApplicationError(409, "CONCEPT_CODE_EXISTS", "Concept code already exists in this subject.")

    def _save(self, concept: Concept, subject_id: UUID, code: str) -> Concept:
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            SubjectService(self.session).get(subject_id)
            self._ensure_unique_code(subject_id, code, excluding=concept.id)
            raise
        self.session.refresh(concept)
        logger.info("Concept saved (concept_id=%s)", concept.id)
        return concept
