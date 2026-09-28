from __future__ import annotations

import json
from pathlib import Path

from app.curriculum.grade12_scope import (
    DATASET_ROOT,
    DEFAULT_GRADE12_SCOPE_PATH,
    EXPECTED_GRADE12_CHAPTER_ORDER,
    EXPECTED_REGISTRY_SHA256,
    Grade12ScopeValidator,
)
from app.validate_grade12_scope import main


def test_grade12_scope_registry_has_exact_order_and_legacy_exclusion() -> None:
    report = Grade12ScopeValidator().validate()

    assert report.is_valid, report.as_dict()
    assert report.in_scope_chapters == EXPECTED_GRADE12_CHAPTER_ORDER
    assert report.legacy_out_of_scope == ("EXPONENTIAL_LOGARITHM",)
    assert report.registry_sha256 == EXPECTED_REGISTRY_SHA256

    registry = json.loads(DEFAULT_GRADE12_SCOPE_PATH.read_text(encoding="utf-8"))
    legacy = registry["legacy_out_of_scope"][0]
    assert legacy["scope_status"] == "OUT_OF_SCOPE_GRADE12"
    assert legacy["actual_grade_level"] == 11
    assert legacy["destructive_delete_allowed"] is False


def test_scope_registry_preserves_canonical_legacy_rows_and_manifest() -> None:
    chapters = json.loads((DATASET_ROOT / "chapters.json").read_text(encoding="utf-8"))
    topics = json.loads((DATASET_ROOT / "topics.json").read_text(encoding="utf-8"))
    manifest = json.loads((DATASET_ROOT / "manifest.json").read_text(encoding="utf-8"))

    assert "EXPONENTIAL_LOGARITHM" in {row["code"] for row in chapters}
    assert "EXP_LOG_TOPIC" in {row["code"] for row in topics}
    assert manifest["verified_at"] is None
    assert Grade12ScopeValidator().validate().checks["canonical_preservation"] is True


def test_scope_validator_rejects_reordered_scope(tmp_path: Path) -> None:
    data = json.loads(DEFAULT_GRADE12_SCOPE_PATH.read_text(encoding="utf-8"))
    data["grade12_chapters"][0], data["grade12_chapters"][1] = (
        data["grade12_chapters"][1],
        data["grade12_chapters"][0],
    )
    path = tmp_path / "grade12_scope_registry_v0_1.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    report = Grade12ScopeValidator().validate(path)

    assert report.status == "FAIL"
    assert report.checks["grade12_scope_order"] is False
    assert report.checks["registry_identity"] is False


def test_scope_cli_is_deterministic(capsys) -> None:
    assert main([]) == 0
    first = capsys.readouterr().out
    assert main([]) == 0
    second = capsys.readouterr().out
    assert first == second
    assert json.loads(first)["status"] == "PASS"
