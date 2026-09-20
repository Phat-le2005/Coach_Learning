"""EduMS RAG (Retrieval-Augmented Generation) domain.

Provides document ingestion, normalization, chunking, pgvector embedding,
semantic similarity search with academic metadata filtering, and prompt injection defense.
RAG operates strictly on curriculum and reference documents; personal student state
(mastery, scores, study plans) must be queried through relational services.
"""

from app.rag.embedding_service import EmbeddingService
from app.rag.ingestion_service import DocumentIngestionService
from app.rag.models import (
    Document,
    DocumentChunk,
    DocumentSourceType,
    DocumentStatus,
)
from app.rag.normalization import chunk_text, normalize_text
from app.rag.schemas import (
    AcademicMetadata,
    AcademicMetadataFilter,
    DocumentChunkRead,
    DocumentCreate,
    DocumentRead,
    SearchResultItem,
)
from app.rag.search_service import SemanticSearchService
from app.rag.security import (
    format_rag_context,
    sanitize_document_content,
    validate_rag_scope,
)

__all__ = [
    "AcademicMetadata",
    "AcademicMetadataFilter",
    "Document",
    "DocumentChunk",
    "DocumentChunkRead",
    "DocumentCreate",
    "DocumentIngestionService",
    "DocumentRead",
    "DocumentSourceType",
    "DocumentStatus",
    "EmbeddingService",
    "SearchResultItem",
    "SemanticSearchService",
    "chunk_text",
    "format_rag_context",
    "normalize_text",
    "sanitize_document_content",
    "validate_rag_scope",
]
