"""Versioned concept scores shared by publishing, replay and diagnosis.

Absence of the key preserves legacy aggregate evidence. An explicit empty map
means no concept was assessed (for example an overall-only teacher override).
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from uuid import UUID


KEY = "criterion_concept_outcomes"


@dataclass(frozen=True)
class ConceptOutcome:
    score: float
    is_correct: bool


def concept_outcome(metadata: dict | None, concept_id: UUID, *, score: float | None,
                    is_correct: bool | None) -> ConceptOutcome | None:
    metadata = metadata or {}
    if KEY not in metadata:
        return ConceptOutcome(score, is_correct) if score is not None and is_correct is not None else None
    data = metadata[KEY]
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("concepts"), dict):
        raise ValueError("Unsupported criterion concept evidence")
    item = data["concepts"].get(str(concept_id))
    if item is None:
        return None
    if (not isinstance(item, dict) or type(item.get("score")) not in (int, float)
            or not math.isfinite(item["score"]) or not 0 <= item["score"] <= 1
            or type(item.get("is_correct")) is not bool):
        raise ValueError("Invalid criterion concept outcome")
    return ConceptOutcome(float(item["score"]), item["is_correct"])


def build_outcomes(criteria: list[dict], matches: list, concept_ids: dict[str, UUID]) -> dict:
    by_id = {match.criterion_id: match for match in matches}
    totals: dict[str, list[float]] = {}
    details = []
    for criterion in criteria:
        match = by_id[criterion["id"]]
        codes = criterion.get("concept_codes", [])
        details.append({"criterion_id": match.criterion_id, "weight": match.weight,
                        "achieved": match.score_achieved, "step_index": match.matched_step_index,
                        "checks": match.details})
        numeric_checks = (match.details or {}).get("numeric_checks")
        contributions = ([(check["concept_codes"], match.weight * check["score"] / len(numeric_checks), match.weight / len(numeric_checks))
                          for check in numeric_checks] if numeric_checks else [(codes, match.score_achieved, match.weight)])
        for checked_codes, achieved, weight in contributions:
            for code in checked_codes:
                if code not in concept_ids or code not in codes:
                    raise ValueError("Rubric concept is not linked to this criterion and question")
                numerator, denominator = totals.setdefault(str(concept_ids[code]), [0.0, 0.0])
                totals[str(concept_ids[code])] = [numerator + achieved, denominator + weight]
    outcomes = {identifier: {"score": round(n / d, 6), "is_correct": n / d >= .85}
                for identifier, (n, d) in totals.items()}
    return {KEY: {"version": 1, "concepts": outcomes, "criteria": details}}
