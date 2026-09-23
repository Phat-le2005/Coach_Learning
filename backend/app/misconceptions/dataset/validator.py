from __future__ import annotations

from typing import Iterable

from app.misconceptions.dataset.anonymizer import PIISanitizer
from app.misconceptions.dataset.schemas import (
    CognitiveTaxonomy,
    MisconceptionSample,
    MisconceptionSeverity,
    RecommendedHintType,
)
from app.misconceptions.models import MisconceptionCategory


class QualityValidationError(ValueError):
    """Raised when a sample fails quality approval checks."""


class QualityValidator:
    """Enforces strict quality approval gates for Misconception Detection dataset samples."""

    DEFAULT_ALLOWED_LABELS: set[str] = {
        "DERIVATIVE_SIGN_DIRECTION",
        "PARAMETER_CONDITION_NOT_GLOBAL",
        "DERIVATIVE_ZERO_ALWAYS_EXTREMUM",
        "LOG_SUM_DISTRIBUTION",
        "INDEFINITE_INTEGRAL_MISSING_CONSTANT",
        "PROBABILITY_INDEPENDENCE_ASSUMED",
        "VECTOR_COORDINATE_SIGN_ERROR",
        "OXYZ_NORMAL_VECTOR_MISUSED",
        "FUNCTION_GRAPH_AXES_MISREAD",
        "DERIVATIVE_ARITHMETIC_SLIP",
    }

    def __init__(self, allowed_labels: Iterable[str] | None = None) -> None:
        self.allowed_labels = set(allowed_labels) if allowed_labels else self.DEFAULT_ALLOWED_LABELS

    def validate_sample(self, sample: MisconceptionSample) -> list[str]:
        """Validate sample and return list of failure reasons. Empty list means APPROVED."""
        errors: list[str] = []

        # 1. Content completeness
        if not sample.question or len(sample.question.strip()) < 5:
            errors.append("Question content must be at least 5 characters.")
        if not sample.problem_type or len(sample.problem_type.strip()) < 2:
            errors.append("ProblemType is required and cannot be blank.")
        if not sample.concepts or len(sample.concepts) == 0:
            errors.append("At least one concept mapping is required.")
        if not sample.student_solution or len(sample.student_solution.strip()) < 2:
            errors.append("Student solution cannot be blank.")
        if not sample.reference_solution or len(sample.reference_solution.strip()) < 2:
            errors.append("Reference solution cannot be blank.")

        # 2. Student solution must not be identical to reference solution
        if sample.student_solution.strip().lower() == sample.reference_solution.strip().lower():
            errors.append("Student solution cannot be identical to correct reference solution.")

        # 3. Label verification against canonical taxonomy
        if sample.verified_misconception_label not in self.allowed_labels:
            errors.append(
                f"Misconception label '{sample.verified_misconception_label}' is not in the approved active taxonomy."
            )

        # 4. Enum validations
        if not isinstance(sample.error_category, MisconceptionCategory):
            errors.append(f"Invalid error category '{sample.error_category}'.")
        if not isinstance(sample.severity, MisconceptionSeverity):
            errors.append(f"Invalid severity level '{sample.severity}'.")
        if not isinstance(sample.recommended_hint_type, RecommendedHintType):
            errors.append(f"Invalid recommended hint type '{sample.recommended_hint_type}'.")
        if not isinstance(sample.taxonomy, CognitiveTaxonomy):
            errors.append(f"Invalid cognitive taxonomy '{sample.taxonomy}'.")

        # 5. Zero PII Guarantee
        for field_name, text in [
            ("question", sample.question),
            ("student_solution", sample.student_solution),
            ("reference_solution", sample.reference_solution),
        ]:
            if PIISanitizer.contains_pii(text):
                errors.append(f"Field '{field_name}' contains unredacted personally identifiable information (PII).")

        return errors

    def is_approved(self, sample: MisconceptionSample) -> bool:
        """Returns True if sample passes all quality approval checks."""
        return len(self.validate_sample(sample)) == 0

    def assert_approved(self, sample: MisconceptionSample) -> None:
        """Raise QualityValidationError if sample fails any approval gate."""
        errors = self.validate_sample(sample)
        if errors:
            raise QualityValidationError(f"Sample {sample.id} rejected: {'; '.join(errors)}")
