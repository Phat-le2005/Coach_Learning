from __future__ import annotations

import json

import pytest

from app.core.exceptions import ApplicationError
from app.questions.import_service import QuestionImportService
from app.questions.provenance_corrections import (
    QuestionProvenanceCorrectionResolver,
)
from app.questions.question_type_resolution import (
    effective_question_type,
    requires_question_group,
)
from app.questions.review_overlay import QuestionReviewOverlayResolver
from app.questions.staging_validator import DEFAULT_QUESTION_STAGING_PATH


DATA_ROOT = DEFAULT_QUESTION_STAGING_PATH.parent


def _effective_candidates() -> dict[str, dict[str, object]]:
    raw = json.loads(
        (DEFAULT_QUESTION_STAGING_PATH / "candidate_questions.json").read_text(
            encoding="utf-8"
        )
    )
    subsources = json.loads(
        (DEFAULT_QUESTION_STAGING_PATH / "subsource_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    provenance = QuestionProvenanceCorrectionResolver().resolve(
        raw,
        DEFAULT_QUESTION_STAGING_PATH / "provenance_corrections.json",
        subsources,
    )
    assert provenance.report.is_valid
    current = list(provenance.candidates)
    for batch_path in sorted((DATA_ROOT / "review").glob("batch_*")):
        overlay = QuestionReviewOverlayResolver().resolve(current, batch_path)
        assert overlay.report.is_valid
        current = list(overlay.candidates)
    return {str(candidate["candidate_id"]): candidate for candidate in current}


def test_effective_question_type_uses_confirmed_precedence() -> None:
    candidate = {
        "question_type_detected": "TRUE_FALSE_GROUP",
        "review_record": {"reviewed_question_type": "MULTIPLE_CHOICE"},
        "reviewed_question_type": "SHORT_ANSWER",
    }

    assert effective_question_type(candidate) == "SHORT_ANSWER"
    candidate.pop("reviewed_question_type")
    assert effective_question_type(candidate) == "MULTIPLE_CHOICE"
    candidate.pop("review_record")
    assert effective_question_type(candidate) == "TRUE_FALSE_GROUP"


def test_invalid_reviewed_type_does_not_fall_back_to_raw_detection() -> None:
    candidate = {
        "question_type_detected": "TRUE_FALSE_GROUP",
        "reviewed_question_type": "INVALID_TYPE",
    }

    assert effective_question_type(candidate) is None
    assert requires_question_group(candidate) is True


def test_suggested_type_is_not_a_confirmed_override() -> None:
    candidate = {
        "question_type_detected": "SHORT_ANSWER",
        "review_record": {"suggested_question_type": "TRUE_FALSE_GROUP"},
    }

    assert effective_question_type(candidate) == "SHORT_ANSWER"
    assert requires_question_group(candidate) is False
    candidate["review_record"]["requires_question_group_model"] = True
    assert requires_question_group(candidate) is True


def test_confirmed_mcq_overrides_raw_derived_group_marker() -> None:
    candidate = {
        "question_type_detected": "TRUE_FALSE_GROUP",
        "requires_question_group_model": True,
        "review_record": {"reviewed_question_type": "MULTIPLE_CHOICE"},
    }

    assert effective_question_type(candidate) == "MULTIPLE_CHOICE"
    assert requires_question_group(candidate) is False


@pytest.mark.parametrize(
    ("candidate_id", "expected_code"),
    [
        ("M12_DERIV_CAND_0034", "STAGING_CANDIDATE_REQUIRES_PROMOTION"),
        ("M12_DERIV_CAND_0002", "STAGING_CANDIDATE_NOT_VERIFIED"),
    ],
)
def test_import_guard_respects_reviewed_mcq_type(
    candidate_id: str,
    expected_code: str,
) -> None:
    candidate = _effective_candidates()[candidate_id]

    with pytest.raises(ApplicationError) as error:
        QuestionImportService._reject_staging_candidate_payload([(1, candidate)])

    assert error.value.code == expected_code


def test_import_guard_rejects_untouched_true_false_group() -> None:
    candidates = _effective_candidates()
    candidate = next(
        item
        for item in candidates.values()
        if "review_record" not in item
        and item["question_type_detected"] == "TRUE_FALSE_GROUP"
    )

    with pytest.raises(ApplicationError) as error:
        QuestionImportService._reject_staging_candidate_payload([(1, candidate)])

    assert error.value.code == "STAGING_QUESTION_GROUP_UNSUPPORTED"
