from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RepairPolicy:
    """Pedagogical policy governing Repair Session thresholds, question selection,

    and deterministic success criteria.
    """

    min_performance_threshold: float = 0.70
    require_final_recheck_correct: bool = True
    min_questions_attempted: int = 4
    allow_ai_generation: bool = False
    easy_difficulty_ceiling: float = 0.40
    medium_difficulty_ceiling: float = 0.70

    def __post_init__(self) -> None:
        if not 0.0 < self.min_performance_threshold <= 1.0:
            raise ValueError("min_performance_threshold must be between 0.0 and 1.0")
        if self.min_questions_attempted < 1:
            raise ValueError("min_questions_attempted must be at least 1")
        if not 0.0 < self.easy_difficulty_ceiling <= self.medium_difficulty_ceiling <= 1.0:
            raise ValueError("Difficulty ceilings must satisfy 0 < easy <= medium <= 1.0")
