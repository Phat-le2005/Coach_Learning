from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.core.exceptions import ApplicationError
from app.questions.import_service import QuestionImportService
from app.questions import pdf_handoff_staging as staging
from app.validate_pdf_handoff_staging import main


pytestmark = pytest.mark.skipif(
    not (staging.DEFAULT_OUTPUT / "candidate_questions.json").is_file(),
    reason="Optional local PDF handoff is not distributed with the source repository",
)


@pytest.fixture(scope="module")
def bundle() -> staging.StagingBundle:
    # Unit/mutation tests need only the lightweight staging, not the 283 MB handoff.
    files = {name: json.loads((staging.DEFAULT_OUTPUT / name).read_text(encoding="utf-8")) for name in staging.OUTPUT_FILES}
    digest = hashlib.sha256(b"".join(name.encode() + b"\0" + staging.json_bytes(files[name]) for name in sorted(files))).hexdigest()
    return staging.StagingBundle(files, digest)


@pytest.fixture(scope="module")
def source_rows() -> list[dict]:
    if not staging.DEFAULT_SOURCE.is_dir():
        pytest.skip("Original user handoff not installed; actual-source integration requires the pinned package")
    return [json.loads(line) for line in (staging.DEFAULT_SOURCE / staging.METADATA).read_text(encoding="utf-8-sig").splitlines()]


def test_actual_original_assets_match_pinned_staging(bundle: staging.StagingBundle, source_rows: list[dict]) -> None:
    # Real original PNG/PDF bytes, not just declared hashes; no OCR, DB or network.
    rebuilt = staging.build_bundle()
    assert rebuilt.files == bundle.files
    assert rebuilt.aggregate_sha256 == bundle.aggregate_sha256


def test_actual_package_partition_and_locked_boundaries(bundle: staging.StagingBundle) -> None:
    report = bundle.files["validation_report.json"]
    assert report["source_questions"] == 200
    assert report["source_manifest_files_verified"] == 9979
    assert report["structural_candidates"] == 40
    assert report["candidate_types"] == {"MCQ": 30, "SHORT_ANSWER": 10}
    assert report["held_for_source_review"] == 160
    assert report["academic_review_pending"] == 200
    assert report["policy"]["database_import_allowed"] is False
    assert report["policy"]["canonical_snapshot_allowed"] is False
    assert report["policy"]["step_grading_allowed"] is False
    assert report["policy"]["production_release_eligible"] == 0
    staging.validate_bundle(bundle, staging.DEFAULT_OUTPUT)


def test_projection_preserves_source_semantics_and_all_identities(bundle: staging.StagingBundle, source_rows: list[dict]) -> None:
    rows = source_rows
    by_id = {row["question_id"]: row for row in rows}
    candidates = bundle.files["candidate_questions.json"]
    queue = bundle.files["review_queue.json"]
    projected_ids = [row["source_question_id"] for row in candidates + queue]
    assert len(projected_ids) == len(set(projected_ids)) == 200
    assert set(projected_ids) == set(by_id)
    for candidate in candidates:
        assert candidate["source_record"] == by_id[candidate["source_question_id"]]
        assert candidate["status"] == "STRUCTURAL_CANDIDATE"
        assert candidate["production_release_eligible"] is False
        assert candidate["step_grading_ready"] is False
    assert staging.project_rows(rows) == staging.project_rows(list(reversed(rows)))


def test_incomplete_mcqs_are_held_without_changing_source_groups(bundle: staging.StagingBundle) -> None:
    queue = bundle.files["review_queue.json"]
    incomplete = [row for row in queue if "INCOMPLETE_STRUCTURED_MCQ_OPTIONS" in row["blockers"]]
    assert {row["source_collection_number"] for row in incomplete} == {3065, 3124, 3133}
    assert len(incomplete) == 3


def test_true_false_image_groups_remain_atomic(bundle: staging.StagingBundle, source_rows: list[dict]) -> None:
    rows = source_rows
    image_ids = {row["question_id"] for row in rows if row["usage_group"] == "image_reference"}
    assert len(image_ids) == 157
    # All 157 originals remain whole references, regardless of their internal child structure.
    queue = bundle.files["review_queue.json"]
    assert image_ids <= {row["source_question_id"] for row in queue}
    assert not image_ids & {row["source_question_id"] for row in bundle.files["candidate_questions.json"]}
    assert all("children" not in row and "child_id" not in row for row in queue)


def test_deterministic_hash_and_idempotent_non_destructive_write(bundle: staging.StagingBundle, tmp_path: Path) -> None:
    output = tmp_path / "staging"
    staging.write_bundle(bundle, output)
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    staging.write_bundle(bundle, output)
    staging.validate_bundle(bundle, output)
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}
    assert not list(output.rglob("*.png"))
    assert not (output / "manifest.json").exists()
    digest = hashlib.sha256(b"".join(name.encode() + b"\0" + staging.json_bytes(bundle.files[name]) for name in sorted(bundle.files))).hexdigest()
    assert bundle.aggregate_sha256 == digest
    assert digest == "e738d6bf4d4774e8ceacf9df966676d0c4bcbf4270f202d8cb4bb45aa253c53c"


@pytest.mark.parametrize("mutation", ["answer", "page", "crop", "hash", "status", "policy", "missing", "extra", "manifest"])
def test_staging_mutations_rejected(bundle: staging.StagingBundle, tmp_path: Path, mutation: str) -> None:
    output = tmp_path / "staging"
    staging.write_bundle(bundle, output)
    path = output / "candidate_questions.json"
    candidates = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "answer":
        candidates[0]["source_record"]["answer_spec"]["expected_label"] = "CHANGED"
    elif mutation in {"page", "crop", "hash"}:
        fragment = candidates[0]["source_record"]["parts"]["question"]["fragments"][0]
        fragment[{"page": "page_number", "crop": "bbox", "hash": "source_asset_sha256"}[mutation]] = "CHANGED"
    elif mutation == "status":
        candidates[0]["status"] = "VERIFIED"
    elif mutation == "policy":
        candidates[0]["database_import_allowed"] = True
    elif mutation == "missing":
        path.unlink()
    elif mutation == "extra":
        (output / "undeclared.png").write_bytes(b"undeclared")
    elif mutation == "manifest":
        (output / "manifest.json").write_text("{}")
    if mutation not in {"missing", "extra", "manifest"}:
        path.write_bytes(staging.json_bytes(candidates))
    with pytest.raises(staging.HandoffValidationError):
        staging.validate_bundle(bundle, output)
    if mutation in {"answer", "page", "crop", "hash", "status", "policy"}:
        changed = path.read_bytes()
        with pytest.raises(staging.HandoffValidationError, match="Refusing to overwrite"):
            staging.write_bundle(bundle, output)
        assert path.read_bytes() == changed


@pytest.mark.parametrize("path", ["../escape.png", "/absolute.png", "C:/absolute.png", "assets\\image.png", "assets/../image.png"])
def test_unsafe_source_paths_rejected(tmp_path: Path, path: str) -> None:
    with pytest.raises(staging.HandoffValidationError):
        staging.safe_file(tmp_path, path)


def test_original_source_identity_cannot_be_replaced(tmp_path: Path) -> None:
    (tmp_path / "manifest.sha256").write_text("changed source")
    with pytest.raises(staging.HandoffValidationError, match="Pinned source identity"):
        staging.verify_source(tmp_path)


@pytest.mark.parametrize("mutation", ["asset_bytes", "missing_asset", "unlisted_asset", "manifest_hash"])
def test_manifest_verifier_detects_actual_source_asset_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    # Tiny test-only package exercises byte verification without altering supplied files.
    metadata = tmp_path / staging.METADATA
    metadata.parent.mkdir(parents=True)
    metadata.write_bytes(b"")
    asset = tmp_path / "source.png"
    asset.write_bytes(b"original asset bytes")
    manifest = tmp_path / "manifest.sha256"
    manifest.write_text(f"{staging.sha256_file(metadata)}  {staging.METADATA}\n{staging.sha256_file(asset)}  source.png\n", encoding="utf-8")
    monkeypatch.setattr(staging, "MANIFEST_SHA256", staging.sha256_file(manifest))
    monkeypatch.setattr(staging, "METADATA_SHA256", staging.sha256_file(metadata))
    assert staging.verify_source(tmp_path)[0] == []
    if mutation == "asset_bytes":
        asset.write_bytes(b"changed asset bytes")
    elif mutation == "missing_asset":
        asset.unlink()
    elif mutation == "unlisted_asset":
        (tmp_path / "undeclared.png").write_bytes(b"extra")
    else:
        manifest.write_text("tampered manifest", encoding="utf-8")
    with pytest.raises(staging.HandoffValidationError):
        staging.verify_source(tmp_path)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "not-a-number"])
def test_invalid_numeric_answers_are_never_inferred(bundle: staging.StagingBundle, value: str) -> None:
    row = deepcopy(next(c["source_record"] for c in bundle.files["candidate_questions.json"] if c["question_type"] == "SHORT_ANSWER"))
    row["answer_spec"]["expected_decimal"] = value
    assert staging.structural_blockers(row) == ["INVALID_EXACT_DECIMAL_ANSWER"]


def test_generic_import_rejects_candidates_before_any_database_write(bundle: staging.StagingBundle) -> None:
    session = Mock()
    actor = Mock()
    with pytest.raises(ApplicationError) as caught:
        QuestionImportService(session).preview(actor, file_name="candidate_questions.json", content=staging.json_bytes(bundle.files["candidate_questions.json"]))
    assert caught.value.code == "STAGING_CANDIDATE_NOT_VERIFIED"
    assert session.mock_calls == []


def test_source_cannot_be_used_as_output(bundle: staging.StagingBundle) -> None:
    with pytest.raises(staging.HandoffValidationError, match="read-only source package"):
        staging.write_bundle(bundle, staging.DEFAULT_SOURCE / "accidental-output")


def test_cli_reports_missing_source_without_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--source-package", str(tmp_path), "--path", str(tmp_path / "output")]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL"
