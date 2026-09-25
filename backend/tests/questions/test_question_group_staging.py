from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
    EXPECTED_RAW_CANDIDATE_SHA256,
    QuestionGroupStagingBuild,
    QuestionGroupStagingBuilder,
    QuestionGroupStructureParser,
)
from app.questions.question_group_staging_validator import (
    QuestionGroupStagingValidator,
)
from app.questions.staging_validator import (
    DEFAULT_QUESTION_STAGING_PATH,
    QuestionStagingValidator,
    candidate_promotion_blockers,
)


QUESTION_TYPE_CORRECTION_IDS = {
    "M12_DERIV_CAND_0012",
    "M12_DERIV_CAND_0019",
    "M12_DERIV_CAND_0035",
    "M12_DERIV_CAND_0047",
    "M12_DERIV_CAND_0052",
}
RECLASSIFIED_MCQ_IDS = {
    "M12_DERIV_CAND_0002",
    "M12_DERIV_CAND_0005",
    "M12_DERIV_CAND_0011",
    "M12_DERIV_CAND_0023",
    "M12_DERIV_CAND_0028",
    "M12_DERIV_CAND_0034",
    "M12_DERIV_CAND_0037",
    "M12_DERIV_CAND_0051",
}
REJECTED_RAW_GROUP_DUPLICATE_IDS = {
    "M12_DERIV_CAND_0016",
    "M12_DERIV_CAND_0029",
    "M12_DERIV_CAND_0039",
    "M12_DERIV_CAND_0064",
    "M12_DERIV_CAND_0067",
    "M12_DERIV_CAND_0142",
}


@pytest.fixture(scope="module")
def group_build() -> QuestionGroupStagingBuild:
    return QuestionGroupStagingBuilder().build()


def _source_ids(build: QuestionGroupStagingBuild) -> set[str]:
    return {
        str(record["source_candidate_id"])
        for record in (*build.groups, *build.structural_holds)
    }


def test_build_has_expected_structural_boundary_counts(
    group_build: QuestionGroupStagingBuild,
) -> None:
    assert group_build.report["active_group_inputs"] == 68
    assert group_build.report["emitted_groups"] == 67
    assert group_build.report["structural_holds"] == 1
    assert group_build.report["emitted_child_statements"] == 268
    assert group_build.report["assigned_child_answers"] == 0
    assert len(group_build.groups) == 67
    assert sum(len(group["items"]) for group in group_build.groups) == 268
    assert all(
        item["correct_answer"] is None
        for group in group_build.groups
        for item in group["items"]
    )


def test_known_invalid_label_order_is_the_only_structural_hold(
    group_build: QuestionGroupStagingBuild,
) -> None:
    assert group_build.structural_holds == ({
        "source_candidate_id": "M12_DERIV_CAND_0061",
        "source_fingerprint": "1b3a79b7095c4004",
        "source_code": "SRC_TRUONG_NGOC_VY_40_2026",
        "raw_subsource_code": "NGOC_VY_2026_02",
        "effective_subsource_code": "NGOC_VY_2026_02",
        "provenance_correction_code": None,
        "source_page": 24,
        "question_number": "1",
        "source_review_status": "UNTOUCHED_REVIEW_REQUIRED",
        "hold_code": "LABEL_ORDER_INVALID",
        "observed_labels": ["a", "c", "b", "d"],
        "expected_labels": ["a", "b", "c", "d"],
        "reason": "Statement labels must remain in extracted order a, b, c, d.",
        "action": "SOURCE_PAGE_REVIEW_REQUIRED",
    },)


@pytest.mark.parametrize(
    ("text", "expected_context", "expected_statements"),
    [
        (
            "Context a) one b) two c) three d) four",
            "Context",
            ("one", "two", "three", "four"),
        ),
        (
            "Context (a) one (b) two (c) three (d) four",
            "Context",
            ("one", "two", "three", "four"),
        ),
        (
            "Graph (C) and f(a) belong here. (a) one (b) two (c) three (d) four",
            "Graph (C) and f(a) belong here.",
            ("one", "two", "three", "four"),
        ),
    ],
)
def test_parser_accepts_supported_markers_without_treating_uppercase_graph_name_as_c(
    text: str,
    expected_context: str,
    expected_statements: tuple[str, ...],
) -> None:
    result = QuestionGroupStructureParser().parse(text)

    assert result.issue is None
    assert result.group_context == expected_context
    assert result.statements == expected_statements


@pytest.mark.parametrize(
    ("text", "expected_code"),
    [
        ("Context a) one c) three b) two d) four", "LABEL_ORDER_INVALID"),
        ("Context a) one b) two d) four", "MARKERS_MISSING"),
        (
            "Context a) one b) two c) three c) duplicate d) four",
            "MARKERS_DUPLICATED",
        ),
        ("Context a) one b) c) three d) four", "EMPTY_STATEMENT"),
        ("a) one b) two c) three d) four", "EMPTY_GROUP_CONTEXT"),
    ],
)
def test_parser_holds_invalid_structure(text: str, expected_code: str) -> None:
    result = QuestionGroupStructureParser().parse(text)

    assert result.issue is not None
    assert result.issue.code == expected_code
    assert result.issue.action == "SOURCE_PAGE_REVIEW_REQUIRED"


def test_effective_selection_includes_and_excludes_reviewed_boundaries(
    group_build: QuestionGroupStagingBuild,
) -> None:
    selected_ids = _source_ids(group_build)

    assert QUESTION_TYPE_CORRECTION_IDS <= selected_ids
    assert RECLASSIFIED_MCQ_IDS.isdisjoint(selected_ids)
    assert REJECTED_RAW_GROUP_DUPLICATE_IDS.isdisjoint(selected_ids)
    assert group_build.report["review_added_group_requirement_from_non_group_raw"] == 5
    assert group_build.report["review_reclassified_group_to_mcq"] == 8
    assert group_build.report["rejected_raw_group_duplicates"] == 6


def test_provenance_correction_is_effective_without_mutating_raw_provenance(
    group_build: QuestionGroupStagingBuild,
) -> None:
    group = next(
        record
        for record in group_build.groups
        if record["source_candidate_id"] == "M12_DERIV_CAND_0031"
    )

    assert group["raw_subsource_code"] == "HA_TINH_2025"
    assert group["effective_subsource_code"] == "HUNG_YEN_2025"
    assert group["provenance_correction_code"] == (
        "PROV_CORR_HUNG_YEN_2025_PAGE_BOUNDARY"
    )


def test_child_taxonomy_remains_review_required(
    group_build: QuestionGroupStagingBuild,
) -> None:
    group = group_build.groups[0]

    assert group["parent_concepts"]
    assert group["parent_learning_outcomes"]
    assert group["child_taxonomy_status"] == "REVIEW_REQUIRED"
    assert all(item["taxonomy_status"] == "REVIEW_REQUIRED" for item in group["items"])
    assert all("concepts" not in item for item in group["items"])
    assert all("learning_outcomes" not in item for item in group["items"])


def test_generated_staging_matches_fresh_build_and_passes_read_only_validation() -> None:
    report = QuestionGroupStagingValidator().validate()

    assert DEFAULT_QUESTION_GROUP_STAGING_PATH.is_dir()
    assert report.status == "PASS"
    assert all(report.checks.values())
    assert report.errors == ()
    assert report.counts == {
        "groups": 67,
        "structural_holds": 1,
        "child_statements": 268,
        "assigned_child_answers": 0,
    }


def test_existing_effective_review_counts_and_promotion_guard_remain_unchanged() -> None:
    report = QuestionStagingValidator().validate()

    assert report.effective_reviewed.status_summary == {
        "total": 175,
        "verified": 29,
        "hold": 40,
        "rejected": 43,
        "untouched_review_required": 63,
    }
    candidate = next(
        row
        for row in report.materialization.effective_candidates
        if row["candidate_id"] == "M12_DERIV_CAND_0012"
    )
    assert "TRUE_FALSE_GROUP_UNSUPPORTED" in candidate_promotion_blockers(candidate)


def test_build_does_not_change_raw_candidate_bytes_or_hash() -> None:
    raw_path = DEFAULT_QUESTION_STAGING_PATH / "candidate_questions.json"
    before = raw_path.read_bytes()

    QuestionGroupStagingBuilder().build()

    after = raw_path.read_bytes()
    assert after == before
    assert hashlib.sha256(after).hexdigest() == EXPECTED_RAW_CANDIDATE_SHA256
