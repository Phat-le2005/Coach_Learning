from dataclasses import dataclass
from typing import Any
from uuid import UUID
from app.math_solutions.models import SolutionRubric


@dataclass(frozen=True)
class RubricCriterionMatch:
    criterion_id: str
    weight: float
    score_achieved: float
    matched_step_index: int


DEFAULT_M12_MONOTONICITY_CRITERIA = [
    {"id": "step_domain", "step_type": "ASSUMPTION", "weight": 0.10, "name": "Tập xác định D = R"},
    {"id": "step_derivative", "step_type": "DERIVATIVE_CALCULATION", "weight": 0.30, "name": "Tính đạo hàm y' = x^2 - 2x - 3"},
    {"id": "step_roots", "step_type": "ROOT_FINDING", "weight": 0.20, "name": "Giải phương trình y' = 0"},
    {"id": "step_sign_table", "step_type": "SIGN_TABLE", "weight": 0.25, "name": "Bảng xét dấu tam thức bậc hai"},
    {"id": "step_conclusion", "step_type": "CONCLUSION", "weight": 0.15, "name": "Kết luận khoảng đồng biến, nghịch biến"},
]


class SolutionRubricEvaluator:
    """
    Tier-3 Solution Rubric Matcher.
    Maps validated step revisions to rubric criteria and computes weighted attempt scores.
    """

    def __init__(self, rubric: SolutionRubric | None = None) -> None:
        self.rubric = rubric

    def evaluate(
        self,
        step_validities: list[dict[str, Any]],
    ) -> tuple[float, list[RubricCriterionMatch]]:
        """
        step_validities: list of dicts with:
        - step_index: int
        - step_type: str
        - validity: 'VALID' | 'INVALID' | 'UNDETERMINED' | 'NEEDS_REVIEW'
        - raw_score: float | None
        """
        criteria = DEFAULT_M12_MONOTONICITY_CRITERIA
        if self.rubric and self.rubric.criteria:
            if isinstance(self.rubric.criteria, list):
                criteria = self.rubric.criteria
            elif isinstance(self.rubric.criteria, dict) and "criteria" in self.rubric.criteria:
                criteria = self.rubric.criteria["criteria"]

        matches: list[RubricCriterionMatch] = []
        total_score = 0.0

        for crit in criteria:
            crit_id = crit.get("id", "crit")
            crit_type = crit.get("step_type", "CUSTOM")
            weight = float(crit.get("weight", 0.2))

            # Find matching step
            matched_step = None
            for s in step_validities:
                if s["step_type"] == crit_type:
                    matched_step = s
                    break

            if matched_step is not None:
                step_idx = matched_step["step_index"]
                val = matched_step.get("validity")
                raw = matched_step.get("raw_score")
                if val == "VALID":
                    factor = 1.0 if raw is None else float(raw)
                elif val == "NEEDS_REVIEW":
                    factor = 0.5
                else:
                    factor = 0.0

                achieved = round(weight * factor, 4)
                total_score += achieved
                matches.append(
                    RubricCriterionMatch(
                        criterion_id=crit_id,
                        weight=weight,
                        score_achieved=achieved,
                        matched_step_index=step_idx,
                    )
                )
            else:
                matches.append(
                    RubricCriterionMatch(
                        criterion_id=crit_id,
                        weight=weight,
                        score_achieved=0.0,
                        matched_step_index=-1,
                    )
                )

        final_score = round(min(1.0, max(0.0, total_score)), 2)
        return final_score, matches
