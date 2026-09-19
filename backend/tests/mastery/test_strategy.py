from app.mastery.strategy import (
    AttemptEvidence,
    DeterministicMasteryCalculationStrategy,
    MappingEvidence,
    MasteryState,
    QuestionEvidence,
)


def calculate(
    *,
    previous: MasteryState | None = None,
    correct: bool = True,
    score: float | None = None,
    difficulty: float = 0.5,
    weight: float = 1.0,
    hints: int = 0,
) -> MasteryState:
    return DeterministicMasteryCalculationStrategy().calculate_from_attempt(
        previous or MasteryState(),
        QuestionEvidence(difficulty=difficulty),
        MappingEvidence(weight=weight),
        AttemptEvidence(
            is_correct=correct,
            score=float(correct) if score is None else score,
            hint_count=hints,
        ),
    )


def test_correct_difficult_question_is_stronger_than_correct_easy_question() -> None:
    easy = calculate(difficulty=0.0)
    difficult = calculate(difficulty=1.0)
    assert 0.0 < easy.mastery_score < difficult.mastery_score < 0.31


def test_incorrect_answer_reduces_existing_mastery() -> None:
    previous = MasteryState(
        mastery_score=0.6, confidence=0.5, attempt_count=5, correct_count=4
    )
    result = calculate(previous=previous, correct=False, difficulty=0.4)
    assert 0.0 <= result.mastery_score < previous.mastery_score
    assert result.attempt_count == 6
    assert result.correct_count == 4


def test_hints_reduce_evidence_strength_without_turning_success_into_failure() -> None:
    no_hint = calculate(hints=0)
    with_hints = calculate(hints=4)
    assert with_hints.mastery_score < no_hint.mastery_score
    assert with_hints.confidence < no_hint.confidence
    assert with_hints.correct_count == 1


def test_confidence_increases_with_repeated_evidence() -> None:
    state = MasteryState()
    confidences: list[float] = []
    for _ in range(5):
        state = calculate(previous=state)
        confidences.append(state.confidence)
    assert confidences == sorted(confidences)
    assert len(set(confidences)) == len(confidences)


def test_single_answer_is_bounded_and_does_not_create_extreme_mastery() -> None:
    state = calculate(difficulty=1.0)
    assert state.mastery_score <= 0.3
    assert state.confidence <= 0.2


def test_repeated_evidence_stays_in_bounds() -> None:
    state = MasteryState()
    for _ in range(100):
        state = calculate(previous=state, difficulty=1.0)
    assert 0.0 <= state.mastery_score <= 1.0
    assert 0.0 <= state.confidence <= 1.0
    assert state.attempt_count == 100
    assert state.correct_count == 100


def test_strategy_is_deterministic() -> None:
    previous = MasteryState(
        mastery_score=0.42, confidence=0.37, attempt_count=4, correct_count=2
    )
    first = calculate(previous=previous, difficulty=0.73, weight=0.65, hints=2)
    second = calculate(previous=previous, difficulty=0.73, weight=0.65, hints=2)
    assert first == second

