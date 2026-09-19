from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.questions.models import Question


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

    _whitespace = re.compile(r"\s+")

    def fingerprint(self, content: str) -> str:
        normalized = unicodedata.normalize("NFKC", content)
        normalized = self._whitespace.sub(" ", normalized).strip().casefold()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def detect(
        self, session: Session, candidates: Sequence[str]
    ) -> dict[int, DuplicateMatch]:
        existing_by_hash: dict[str, UUID] = {}
        for question_id, content in session.execute(select(Question.id, Question.content)):
            existing_by_hash.setdefault(self.fingerprint(content), question_id)

        matches: dict[int, DuplicateMatch] = {}
        first_candidate_by_hash: dict[str, int] = {}
        for index, content in enumerate(candidates):
            fingerprint = self.fingerprint(content)
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
