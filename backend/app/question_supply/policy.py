"""Central supply policy and deterministic signature generation."""

from __future__ import annotations

import hashlib
import json
from typing import Iterable
from uuid import UUID

from app.question_supply.models import (
    QuestionSupplyHealth,
    QuestionSupplySeverity,
    QuestionSupplyTargetType,
    QuestionSupplyUseCase,
)
from app.questions.models import QuestionType


class QuestionSupplyPolicy:
    """Deterministic thresholds and rule evaluation for question bank sufficiency."""

    # Threshold constants
    VERIFICATION_MIN_COUNT = 2
    VERIFICATION_PREFERRED_COUNT = 3
    VERIFICATION_DIFFICULTY_TOLERANCE = 0.10

    REPAIR_MIN_COUNT = 4
    REPAIR_PREFERRED_COUNT = 8
    REPAIR_DIFFICULTY_TOLERANCE = 0.15

    REVIEW_MIN_COUNT = 1
    REVIEW_PREFERRED_COUNT = 3
    REVIEW_DIFFICULTY_TOLERANCE = 0.15

    CURRENT_LEARNING_MIN_COUNT = 1
    CURRENT_LEARNING_PREFERRED_COUNT = 3
    CURRENT_LEARNING_DIFFICULTY_TOLERANCE = 0.15

    AUTO_EVALUABLE_TYPES = frozenset(
        {QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE, QuestionType.SHORT_ANSWER}
    )

    @classmethod
    def get_defaults(
        cls, use_case: QuestionSupplyUseCase
    ) -> tuple[int, int, float, bool, frozenset[QuestionType] | None]:
        """Return (min_count, preferred_count, tolerance, require_auto_evaluable, allowed_types)."""
        if use_case == QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION:
            return (
                cls.VERIFICATION_MIN_COUNT,
                cls.VERIFICATION_PREFERRED_COUNT,
                cls.VERIFICATION_DIFFICULTY_TOLERANCE,
                True,
                cls.AUTO_EVALUABLE_TYPES,
            )
        elif use_case == QuestionSupplyUseCase.ADAPTIVE_REPAIR:
            return (
                cls.REPAIR_MIN_COUNT,
                cls.REPAIR_PREFERRED_COUNT,
                cls.REPAIR_DIFFICULTY_TOLERANCE,
                True,
                cls.AUTO_EVALUABLE_TYPES,
            )
        elif use_case == QuestionSupplyUseCase.REVIEW:
            return (
                cls.REVIEW_MIN_COUNT,
                cls.REVIEW_PREFERRED_COUNT,
                cls.REVIEW_DIFFICULTY_TOLERANCE,
                False,
                None,
            )
        elif use_case == QuestionSupplyUseCase.CURRENT_LEARNING:
            return (
                cls.CURRENT_LEARNING_MIN_COUNT,
                cls.CURRENT_LEARNING_PREFERRED_COUNT,
                cls.CURRENT_LEARNING_DIFFICULTY_TOLERANCE,
                False,
                None,
            )
        raise ValueError(f"Unsupported use case: {use_case}")

    @classmethod
    def compute_difficulty_band(
        cls, desired_difficulty: float | None, tolerance: float
    ) -> tuple[float, float]:
        """Compute clamped [difficulty_min, difficulty_max] band."""
        if desired_difficulty is None:
            return (0.0, 1.0)
        d = float(desired_difficulty)
        min_val = max(0.0, round(d - tolerance, 4))
        max_val = min(1.0, round(d + tolerance, 4))
        return (min_val, max_val)

    @classmethod
    def evaluate_health(
        cls,
        effective_count: int,
        effective_in_band_count: int,
        minimum_required: int,
        preferred: int,
    ) -> QuestionSupplyHealth:
        """Evaluate bank health against target count and difficulty coverage thresholds."""
        if effective_count < minimum_required:
            return QuestionSupplyHealth.INSUFFICIENT
        if effective_in_band_count < minimum_required:
            return QuestionSupplyHealth.INSUFFICIENT
        if effective_count < preferred:
            return QuestionSupplyHealth.THIN
        if effective_in_band_count < preferred:
            return QuestionSupplyHealth.THIN
        return QuestionSupplyHealth.SUFFICIENT

    @classmethod
    def evaluate_severity(
        cls,
        effective_count: int,
        effective_in_band_count: int,
        minimum_required: int,
        preferred: int,
    ) -> QuestionSupplySeverity:
        """Determine gap severity deterministically."""
        if effective_count == 0:
            return QuestionSupplySeverity.CRITICAL
        if (
            effective_in_band_count == 0
            or effective_count < minimum_required
            or effective_in_band_count < minimum_required
        ):
            return QuestionSupplySeverity.HIGH
        if effective_count < preferred or effective_in_band_count < preferred:
            return QuestionSupplySeverity.MEDIUM
        return QuestionSupplySeverity.LOW

    @classmethod
    def evaluate_is_startable(
        cls, use_case: QuestionSupplyUseCase, effective_count: int
    ) -> bool:
        """Determine if a learning session can be started with the available supply."""
        # For verification and repair, having at least 1 canonical fresh probe makes it startable
        return effective_count >= 1

    @classmethod
    def compute_signature(
        cls,
        *,
        subject_id: UUID,
        use_case: QuestionSupplyUseCase,
        target_type: QuestionSupplyTargetType,
        concept_id: UUID | None,
        problem_type_id: UUID | None,
        misconception_definition_id: UUID | None,
        difficulty_min: float,
        difficulty_max: float,
        minimum_required_count: int,
        allowed_question_types: Iterable[QuestionType | str] | None,
        require_auto_evaluable: bool,
    ) -> str:
        """Generate deterministic SHA-256 signature for a unique supply requirement."""
        normalized = {
            "subject_id": str(subject_id).lower(),
            "use_case": use_case.value if hasattr(use_case, "value") else str(use_case),
            "target_type": target_type.value if hasattr(target_type, "value") else str(target_type),
            "concept_id": str(concept_id).lower() if concept_id else "",
            "problem_type_id": str(problem_type_id).lower() if problem_type_id else "",
            "misconception_definition_id": (
                str(misconception_definition_id).lower()
                if misconception_definition_id
                else ""
            ),
            "difficulty_min": f"{float(difficulty_min):.4f}",
            "difficulty_max": f"{float(difficulty_max):.4f}",
            "minimum_required_count": int(minimum_required_count),
            "allowed_question_types": sorted(
                [
                    qt.value if hasattr(qt, "value") else str(qt)
                    for qt in (allowed_question_types or [])
                ]
            ),
            "require_auto_evaluable": bool(require_auto_evaluable),
        }
        payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
