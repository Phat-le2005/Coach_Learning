"""Knowledge Gap Diagnosis domain module."""

from app.knowledge_gap.schemas import (
    AIGapDiagnosisOutput,
    KnowledgeGapResult,
    KnowledgeGapType,
)
from app.knowledge_gap.service import KnowledgeGapService

__all__ = [
    "AIGapDiagnosisOutput",
    "KnowledgeGapResult",
    "KnowledgeGapService",
    "KnowledgeGapType",
]
