from abc import ABC, abstractmethod
from dataclasses import dataclass


def _bounded(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 6)


@dataclass(frozen=True, slots=True)
class MasteryState:
    mastery_score: float = 0.0
    confidence: float = 0.0
    attempt_count: int = 0
    correct_count: int = 0


@dataclass(frozen=True, slots=True)
class QuestionEvidence:
    difficulty: float


@dataclass(frozen=True, slots=True)
class MappingEvidence:
    weight: float


@dataclass(frozen=True, slots=True)
class AttemptEvidence:
    is_correct: bool
    score: float
    hint_count: int
    response_time_seconds: float | None = None


class MasteryCalculationStrategy(ABC):
    @abstractmethod
    def calculate_from_attempt(
        self,
        previous_state: MasteryState,
        question: QuestionEvidence,
        mapping: MappingEvidence,
        attempt: AttemptEvidence,
    ) -> MasteryState:
        """Return the next state from one mapped attempt."""


class DeterministicMasteryCalculationStrategy(MasteryCalculationStrategy):
    """Bounded V1 update rule that can later be replaced by BKT, IRT, or Elo."""

    BASE_MASTERY_RATE = 0.22
    BASE_CONFIDENCE_GAIN = 0.13
    MIN_HINT_FACTOR = 0.55

    def calculate_from_attempt(
        self,
        previous_state: MasteryState,
        question: QuestionEvidence,
        mapping: MappingEvidence,
        attempt: AttemptEvidence,
    ) -> MasteryState:
        difficulty = min(1.0, max(0.0, question.difficulty))
        weight = min(1.0, max(0.0, mapping.weight))
        score = min(1.0, max(0.0, attempt.score))
        hint_factor = max(self.MIN_HINT_FACTOR, 1.0 / (1.0 + 0.2 * attempt.hint_count))

        if attempt.is_correct:
            difficulty_factor = 0.8 + 0.4 * difficulty
        else:
            # An error on an easy item is stronger evidence than an error on a hard item.
            difficulty_factor = 1.1 - 0.3 * difficulty
        mastery_rate = min(
            0.3,
            self.BASE_MASTERY_RATE * weight * difficulty_factor * hint_factor,
        )
        mastery_score = previous_state.mastery_score + mastery_rate * (
            score - previous_state.mastery_score
        )

        confidence_gain = (
            self.BASE_CONFIDENCE_GAIN
            * (0.5 + 0.5 * weight)
            * hint_factor
            * (0.9 + 0.1 * difficulty)
        )
        confidence = previous_state.confidence + confidence_gain * (
            1.0 - previous_state.confidence
        )

        return MasteryState(
            mastery_score=_bounded(mastery_score),
            confidence=_bounded(confidence),
            attempt_count=previous_state.attempt_count + 1,
            correct_count=previous_state.correct_count + int(attempt.is_correct),
        )

