from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.questions.models import Question
from app.questions.fingerprint import question_content_hash


@dataclass(frozen=True, slots=True)
class DuplicateMatch:
    existing_question_id: UUID | None = None
    duplicate_of_index: int | None = None


class QuestionDuplicateDetector(Protocol):
    """Replaceable contract for exact or future semantic duplicate detection."""

    def fingerprint(self, content: str) -> str: ...

    def detect(
        self, session: Session, candidates: Sequence[str]
    ) -> dict[int, DuplicateMatch]: ...


class ExactContentHashDuplicateDetector:
    """Detects normalized exact content matches with a SHA-256 fingerprint."""

    def fingerprint(self, content: str) -> str:
        return question_content_hash(content)

    def detect(
        self, session: Session, candidates: Sequence[str]
    ) -> dict[int, DuplicateMatch]:
        fingerprints = [self.fingerprint(content) for content in candidates]
        candidate_hashes = set(fingerprints)
        existing_by_hash: dict[str, UUID] = {}
        if candidate_hashes:
            existing = session.execute(
                select(Question.id, Question.content_hash)
                .where(Question.content_hash.in_(candidate_hashes))
                .order_by(Question.id)
            )
            for question_id, content_hash in existing:
                existing_by_hash.setdefault(content_hash, question_id)

        matches: dict[int, DuplicateMatch] = {}
        first_candidate_by_hash: dict[str, int] = {}
        for index, fingerprint in enumerate(fingerprints):
            existing_id = existing_by_hash.get(fingerprint)
            if existing_id is not None:
                matches[index] = DuplicateMatch(existing_question_id=existing_id)
                continue
            first_index = first_candidate_by_hash.get(fingerprint)
            if first_index is not None:
                matches[index] = DuplicateMatch(duplicate_of_index=first_index)
                continue
            first_candidate_by_hash[fingerprint] = index
        return matches
