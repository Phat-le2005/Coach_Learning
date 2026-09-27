from __future__ import annotations

import json
from pathlib import Path

from app.curriculum.derivative_candidate import (
    DEFAULT_CANONICAL_CURRICULUM_PATH,
    DEFAULT_DERIVATIVE_STAGING_PATH,
    EXPECTED_CANDIDATE_COUNTS,
    DerivativeCurriculumCandidateBuilder,
    DerivativeCurriculumCandidateValidator,
)


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _by_code(rows: object) -> dict[str, dict[str, object]]:
    assert isinstance(rows, list)
    return {str(row["code"]): row for row in rows}


def test_derivative_candidate_has_exact_counts_and_metadata() -> None:
    report = DerivativeCurriculumCandidateValidator().validate()

    assert report.is_valid
    assert report.errors == ()
    assert report.counts == EXPECTED_CANDIDATE_COUNTS
    assert report.candidate is not None
    assert report.candidate.metadata["dataset_version"] == "1.2.0"
    assert report.candidate.metadata["verified_at"] is None
    assert report.candidate.metadata["importable"] is False
    assert report.candidate.subject.code == "MATH_G12"


def test_non_derivative_canonical_rows_are_preserved() -> None:
    candidate = DerivativeCurriculumCandidateBuilder().build()
    canonical_topics = _by_code(
        _load(DEFAULT_CANONICAL_CURRICULUM_PATH / "topics.json")
    )
    staging_topics = _by_code(
        _load(DEFAULT_DERIVATIVE_STAGING_PATH / "topics.json")
    )
    candidate_topics = {
        item.code: item.model_dump(mode="json") for item in candidate.topics
    }
    for code in canonical_topics.keys() - staging_topics.keys():
        assert candidate_topics[code] == canonical_topics[code]

    canonical_problems = _by_code(
        _load(DEFAULT_CANONICAL_CURRICULUM_PATH / "problem_types.json")
    )
    staging_problems = _by_code(
        _load(DEFAULT_DERIVATIVE_STAGING_PATH / "problem_types.json")
    )
    candidate_problems = {
        item.code: item.model_dump(mode="json") for item in candidate.problem_types
    }
    for code in canonical_problems.keys() - staging_problems.keys():
        if code != "COMPLETE_FUNCTION_ANALYSIS":
            assert candidate_problems[code] == canonical_problems[code]

    canonical_concepts = _by_code(
        _load(DEFAULT_CANONICAL_CURRICULUM_PATH / "concepts.json")
    )
    staging_concepts = _by_code(
        _load(DEFAULT_DERIVATIVE_STAGING_PATH / "concepts.json")
    )
    candidate_concepts = {
        item.code: item.model_dump(mode="json") for item in candidate.concepts
    }
    for code in canonical_concepts.keys() - staging_concepts.keys():
        assert candidate_concepts[code] == canonical_concepts[code]

    canonical_outcomes = _by_code(
        _load(DEFAULT_CANONICAL_CURRICULUM_PATH / "learning_outcomes.json")
    )
    candidate_outcomes = {
        item.code: item.model_dump(mode="json")
        for item in candidate.learning_outcomes
    }
    for code, record in canonical_outcomes.items():
        assert candidate_outcomes[code] == record


def test_staging_wins_exact_derivative_overlaps() -> None:
    candidate = DerivativeCurriculumCandidateBuilder().build()
    candidate_problems = {item.code: item for item in candidate.problem_types}
    staging_problems = _by_code(
        _load(DEFAULT_DERIVATIVE_STAGING_PATH / "problem_types.json")
    )

    for code in (
        "MONOTONICITY_FROM_EXPRESSION",
        "PARAMETER_MONOTONICITY",
        "FIND_FUNCTION_EXTREMA",
    ):
        assert candidate_problems[code].model_dump(mode="json") == (
            staging_problems[code]
        )


def test_complete_function_analysis_is_retained_but_inactive() -> None:
    candidate = DerivativeCurriculumCandidateBuilder().build()
    legacy = next(
        item
        for item in candidate.problem_types
        if item.code == "COMPLETE_FUNCTION_ANALYSIS"
    )

    assert legacy.is_active is False


def test_candidate_materialization_is_deterministic() -> None:
    first = DerivativeCurriculumCandidateBuilder().build()
    second = DerivativeCurriculumCandidateBuilder().build()

    assert first.content_hash == second.content_hash
    assert first.canonical_payload() == second.canonical_payload()


def test_no_second_import_discoverable_canonical_manifest_exists() -> None:
    curriculum_root = DEFAULT_CANONICAL_CURRICULUM_PATH.parents[2]
    matching = []
    for path in curriculum_root.rglob("manifest.json"):
        value = _load(path)
        if isinstance(value, dict) and value.get("dataset_code") == (
            "MATH_G12_GDPT2018_CORE"
        ):
            matching.append(path.resolve())

    assert matching == [
        (DEFAULT_CANONICAL_CURRICULUM_PATH / "manifest.json").resolve()
    ]
