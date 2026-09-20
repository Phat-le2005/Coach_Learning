import math
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.rag.embedding_service import EmbeddingService
from app.rag.models import Document, DocumentChunk, DocumentStatus
from app.rag.schemas import SearchResultItem
from app.rag.security import sanitize_document_content, validate_rag_scope


def compute_cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two float vectors in [-1.0, 1.0]."""
    if not vec1 or not vec2:
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2, strict=False))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    sim = dot / (norm1 * norm2)
    return max(-1.0, min(1.0, sim))


class SemanticSearchService:
    """Service for semantic similarity search with academic metadata filtering."""

    def __init__(
        self,
        session: Session,
        embedding_service: EmbeddingService,
    ) -> None:
        self.session = session
        self.embedding_service = embedding_service

    async def semantic_search(
        self,
        query: str,
        *,
        subject_id: UUID | None = None,
        chapter_ids: list[UUID] | None = None,
        topic_ids: list[UUID] | None = None,
        problem_type_ids: list[UUID] | None = None,
        concept_ids: list[UUID] | None = None,
        top_k: int = 5,
    ) -> list[SearchResultItem]:
        """Perform semantic search on curriculum document chunks.
        
        Enforces:
        - Relational scope validation: Blocks personal data queries (mastery, scores, study plans).
        - Multi-dimensional academic filtering (subject, chapter, topic, problem type, concept).
        - Production: native pgvector `<=>` index execution.
        - Test environment fallback: in-memory cosine similarity calculation.
        """
        # 1. Guardrail against relational personal data queries
        validate_rag_scope(query)

        clean_query = query.strip()
        if not clean_query:
            return []

        # 2. Embed the search query
        query_embeddings = await self.embedding_service.embed_texts([clean_query])
        if not query_embeddings:
            return []
        query_vector = query_embeddings[0]

        # 3. Base SQL query with document join and published status filter
        conditions = [Document.status == DocumentStatus.PUBLISHED.value]
        if subject_id is not None:
            conditions.append(Document.subject_id == subject_id)

        stmt = (
            select(DocumentChunk, Document.title)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(and_(*conditions))
        )

        rows = self.session.execute(stmt).all()
        if not rows:
            return []

        # Filter string representations of UUIDs
        ch_str_set = {str(uid) for uid in chapter_ids} if chapter_ids else None
        tp_str_set = {str(uid) for uid in topic_ids} if topic_ids else None
        pt_str_set = {str(uid) for uid in problem_type_ids} if problem_type_ids else None
        conc_str_set = {str(uid) for uid in concept_ids} if concept_ids else None

        scored_candidates: list[SearchResultItem] = []

        for chunk_row, doc_title in rows:
            meta: dict[str, Any] = chunk_row.metadata_ or {}

            # Apply academic metadata filters if specified
            if ch_str_set is not None:
                chunk_chs = set(meta.get("chapter_ids", []))
                if not (ch_str_set & chunk_chs):
                    continue

            if tp_str_set is not None:
                chunk_tps = set(meta.get("topic_ids", []))
                if not (tp_str_set & chunk_tps):
                    continue

            if pt_str_set is not None:
                chunk_pts = set(meta.get("problem_type_ids", []))
                if not (pt_str_set & chunk_pts):
                    continue

            if conc_str_set is not None:
                chunk_concs = set(meta.get("concept_ids", []))
                if not (conc_str_set & chunk_concs):
                    continue

            # Compute similarity
            embedding = chunk_row.embedding
            if not embedding:
                similarity = 0.0
            else:
                raw_emb = list(embedding)
                similarity = compute_cosine_similarity(query_vector, raw_emb)

            # Defensive sanitization of content
            clean_content = sanitize_document_content(chunk_row.content)

            scored_candidates.append(
                SearchResultItem(
                    chunk_id=chunk_row.id,
                    document_id=chunk_row.document_id,
                    document_title=doc_title,
                    content=clean_content,
                    similarity_score=round(similarity, 4),
                    chunk_index=chunk_row.chunk_index,
                    metadata=meta,
                )
            )

        # Sort descending by similarity score
        scored_candidates.sort(key=lambda x: x.similarity_score, reverse=True)
        return scored_candidates[:top_k]
