import logging
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ContextTrimmer:
    """Utility service for prompt token budgeting and context trimming.
    
    Guarantees:
    - Enforces strict upper bounds on text length and chunk counts.
    - Prevents prompt bloat and runaway token consumption.
    - Trims text without cutting off mid-word when possible.
    """

    @staticmethod
    def trim_text(text: str, max_chars: int = 1000, ellipsis: str = "...") -> str:
        """Trim string to max_chars safely."""
        if not text:
            return ""
        stripped = text.strip()
        if len(stripped) <= max_chars:
            return stripped

        target_len = max(0, max_chars - len(ellipsis))
        # Find whitespace near cutoff to avoid splitting words
        space_idx = stripped.rfind(" ", 0, target_len)
        if space_idx > target_len // 2:
            return stripped[:space_idx].rstrip() + ellipsis
        return stripped[:target_len].rstrip() + ellipsis

    @classmethod
    def trim_session_summary(cls, summary: str, max_chars: int = 500) -> str:
        """Trim tutor session summary text to a concise representation."""
        return cls.trim_text(summary, max_chars=max_chars)

    @classmethod
    def trim_rag_chunks(
        cls,
        chunks: list[str],
        *,
        top_k: int = 3,
        max_chars_per_chunk: int = 500,
    ) -> list[str]:
        """Enforce top-k ceiling on RAG chunks and trim each chunk."""
        if not chunks:
            return []
        bounded = chunks[:top_k]
        return [cls.trim_text(chunk, max_chars=max_chars_per_chunk) for chunk in bounded]

    @staticmethod
    def trim_items(items: list[T], max_items: int = 4) -> list[T]:
        """Limit array of items (memories, concepts, attempts) to max_items."""
        if not items:
            return []
        return items[:max_items]
