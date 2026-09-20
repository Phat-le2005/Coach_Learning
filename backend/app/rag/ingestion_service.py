from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, Topic
from app.rag.embedding_service import EmbeddingService
from app.rag.models import Document, DocumentChunk
from app.rag.normalization import chunk_text, normalize_text
from app.rag.schemas import AcademicMetadata, DocumentCreate


class DocumentIngestionService:
    """Service for ingesting, normalizing, chunking, and embedding curriculum documents."""

    def __init__(
        self,
        session: Session,
        embedding_service: EmbeddingService,
    ) -> None:
        self.session = session
        self.embedding_service = embedding_service

    def validate_academic_metadata(
        self,
        metadata: AcademicMetadata | None,
    ) -> dict[str, Any]:
        """Validate that all referenced academic nodes exist in the database with stable IDs.
        
        Rule: Prevents AI or third-party input from inventing non-canonical academic classifications.
        """
        if metadata is None:
            return {}

        validated: dict[str, Any] = {}

        if metadata.chapter_ids:
            for c_id in metadata.chapter_ids:
                if self.session.get(Chapter, c_id) is None:
                    raise ApplicationError(
                        status_code=400,
                        code="INVALID_ACADEMIC_ID",
                        message=f"Referenced Chapter ID '{c_id}' does not exist in database.",
                    )
            validated["chapter_ids"] = [str(c_id) for c_id in metadata.chapter_ids]

        if metadata.topic_ids:
            for t_id in metadata.topic_ids:
                if self.session.get(Topic, t_id) is None:
                    raise ApplicationError(
                        status_code=400,
                        code="INVALID_ACADEMIC_ID",
                        message=f"Referenced Topic ID '{t_id}' does not exist in database.",
                    )
            validated["topic_ids"] = [str(t_id) for t_id in metadata.topic_ids]

        if metadata.problem_type_ids:
            for pt_id in metadata.problem_type_ids:
                if self.session.get(ProblemType, pt_id) is None:
                    raise ApplicationError(
                        status_code=400,
                        code="INVALID_ACADEMIC_ID",
                        message=f"Referenced ProblemType ID '{pt_id}' does not exist in database.",
                    )
            validated["problem_type_ids"] = [str(pt_id) for pt_id in metadata.problem_type_ids]

        if metadata.concept_ids:
            for conc_id in metadata.concept_ids:
                if self.session.get(Concept, conc_id) is None:
                    raise ApplicationError(
                        status_code=400,
                        code="INVALID_ACADEMIC_ID",
                        message=f"Referenced Concept ID '{conc_id}' does not exist in database.",
                    )
            validated["concept_ids"] = [str(conc_id) for conc_id in metadata.concept_ids]

        if metadata.learning_outcome_ids:
            for lo_id in metadata.learning_outcome_ids:
                if self.session.get(LearningOutcome, lo_id) is None:
                    raise ApplicationError(
                        status_code=400,
                        code="INVALID_ACADEMIC_ID",
                        message=f"Referenced LearningOutcome ID '{lo_id}' does not exist in database.",
                    )
            validated["learning_outcome_ids"] = [str(lo_id) for lo_id in metadata.learning_outcome_ids]

        if metadata.grade_level is not None:
            validated["grade_level"] = metadata.grade_level

        return validated

    async def ingest_document(
        self,
        payload: DocumentCreate,
        *,
        created_by: UUID | None = None,
        chunk_size: int = 600,
        chunk_overlap: int = 100,
    ) -> Document:
        """Full pipeline: text -> normalize -> chunk -> embed -> pgvector."""
        # 1. Validate academic metadata
        meta_dict = self.validate_academic_metadata(payload.academic_metadata)

        # 2. Normalize text
        normalized_content = normalize_text(payload.content)
        if not normalized_content:
            raise ApplicationError(
                status_code=400,
                code="EMPTY_DOCUMENT_CONTENT",
                message="Document content must contain printable text after normalization.",
            )

        # 3. Chunk text
        chunks = chunk_text(
            normalized_content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        # 4. Generate embeddings
        embeddings = await self.embedding_service.embed_texts(chunks)

        # 5. Persist Document
        doc = Document(
            title=payload.title,
            subject_id=payload.subject_id,
            source_type=str(payload.source_type),
            source_reference=payload.source_reference,
            status=str(payload.status),
            created_by=created_by,
        )
        self.session.add(doc)
        self.session.flush()

        # 6. Persist DocumentChunks
        for idx, (chunk_str, emb_vector) in enumerate(zip(chunks, embeddings, strict=True)):
            chunk_record = DocumentChunk(
                document_id=doc.id,
                chunk_index=idx,
                content=chunk_str,
                embedding=emb_vector,
                metadata_=meta_dict,
            )
            self.session.add(chunk_record)

        self.session.flush()
        return doc
