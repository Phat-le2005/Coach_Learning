from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.core.exceptions import ApplicationError
from app.prepare_pdf_handoff_review import main
from app.questions.import_service import QuestionImportService
from app.questions import pdf_handoff_review as review
from app.questions.pdf_handoff_staging import DEFAULT_SOURCE, METADATA, HandoffValidationError, json_bytes


pytestmark = pytest.mark.skipif(
    not (review.DEFAULT_REVIEW_OUTPUT / "review_records.json").is_file(),
    reason="Optional local PDF handoff is not distributed with the source repository",
)


@pytest.fixture(scope="module")
def package() -> review.ReviewPackage:
    path = review.DEFAULT_REVIEW_OUTPUT
    records = json.loads((path / "review_records.json").read_text(encoding="utf-8"))
    report = json.loads((path / "readiness_report.json").read_text(encoding="utf-8"))
    payloads = {"review_records.json": json_bytes(records), "readiness_report.json": json_bytes(report)}
    digest = hashlib.sha256(b"".join(name.encode() + b"\0" + payloads[name] for name in sorted(payloads))).hexdigest()
    return review.ReviewPackage(records, report, (path / "index.html").read_text(encoding="utf-8"), digest)


def test_full_review_package_counts_and_replacement_blocked(package: review.ReviewPackage) -> None:
    report = package.report
    assert report["total_questions"] == report["with_source_solution"] == 200
    assert report["with_structured_final_answer"] == 43
    assert report["with_answer_in_reference_solution"] == 200
    assert report["answer_not_separated_from_solution"] == 157
    assert report["source_crop_counts"] == {"question": 233, "solution": 288, "answer": 23}
    assert report["text_and_latex_completeness"] == "NOT_ESTABLISHED"
    assert report["structurally_complete_final_answer"] == 40
    assert report["question_type_candidates"] == {"MULTIPLE_CHOICE": 33, "SHORT_ANSWER": 10, "UNREVIEWED": 157}
    assert report["importable_questions"] == report["official_step_grading_ready"] == 0
    gate = report["replacement_preflight"]
    assert gate["replace_database_allowed"] is gate["delete_existing_questions_allowed"] is False
    assert set(gate["missing_chapters"]) == {"VECTORS_GEOMETRY", "OXYZ_CHAPTER"}
    review.validate_review(package, review.DEFAULT_REVIEW_OUTPUT)


def test_no_invented_taxonomy_difficulty_rubric_or_approval(package: review.ReviewPackage) -> None:
    assert len({r["candidate_id"] for r in package.records}) == 200
    for record in package.records:
        draft = record["import_draft"]
        assert record["academic_decision"] == record["rights_decision"] == record["source_academic_review"] == "PENDING"
        assert record["database_import_allowed"] is record["production_release_eligible"] is record["step_grading_ready"] is False
        assert record["rubric"] is draft["difficulty"] is draft["exam_weight"] is None
        assert draft["concepts"] == draft["problem_types"] == draft["learning_outcomes"] == []
        if not record["source_answer_spec"]:
            assert draft["question_type"] is draft["correct_answer"] is None


def test_solution_answer_availability_is_separate_from_key_extraction(package: review.ReviewPackage) -> None:
    for record in package.records:
        availability = record["answer_availability"]
        assert availability["reference_solution_present"] is True
        assert availability["answer_location"] == "REFERENCE_SOLUTION"
        assert availability["academic_correctness_verified"] is False
        coverage = record["extraction_coverage"]
        assert coverage["question_source_available"] is coverage["solution_source_available"] is True
        assert coverage["text_and_latex_completeness"] == "NOT_ESTABLISHED"
        if record["source_answer_spec"]:
            assert availability["structured_final_key_present"] is True
            assert availability["key_extraction_status"] == "SOURCE_KEY_CANDIDATE"
        else:
            assert availability["structured_final_key_present"] is False
            assert availability["key_extraction_status"] == "NOT_SEPARATED_FROM_SOLUTION"
            assert record["import_draft"]["correct_answer"] is None


def test_target_metadata_and_real_source_references(package: review.ReviewPackage) -> None:
    for record in package.records:
        draft = record["import_draft"]
        assert record["grade_level"] == 12
        assert record["target_curriculum_code"] == "GDPT2018"
        assert draft["subject_code"] == "MATH_G12"
        assert draft["curriculum_version_code"] == "GDPT2018_2018"
        assert draft["source"] == "PDF_HANDOFF_200"
        assert draft["source_year"] is None
        assert record["source_question_id"] in draft["source_reference"]
        assert record["source_pdf"]["sha256"] in draft["source_reference"]
        assert len(draft["source_reference"]) <= 500


def test_known_source_error_is_flagged_without_silently_correcting(package: review.ReviewPackage) -> None:
    row = next(record for record in package.records if record["collection_number"] == 3140)
    assert review.KNOWN_SOURCE_ISSUES[row["source_question_id"]] in row["promotion_blockers"]
    assert row["import_draft"]["correct_answer"] is None


def test_review_records_cannot_enter_generic_import_before_db_access(package: review.ReviewPackage) -> None:
    session = Mock()
    with pytest.raises(ApplicationError) as error:
        QuestionImportService(session).preview(Mock(), file_name="review_records.json", content=json_bytes(package.records))
    assert error.value.code == "STAGING_CANDIDATE_NOT_VERIFIED"
    assert session.mock_calls == []


def test_deterministic_non_overwriting_review_output(package: review.ReviewPackage, tmp_path: Path) -> None:
    output = tmp_path / "review"
    review.write_review(package, output)
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    review.write_review(package, output)
    review.validate_review(package, output)
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}
    assert set(before) == set(review.REVIEW_FILES)
    assert package.aggregate_sha256 == "d2707d540688ef79789201ecb38e1397770299ce3ba301cd271c2cae7b421057"


@pytest.mark.parametrize("mutation", ["answer", "solution", "page", "crop", "hash", "approval", "rights", "delete_permission", "missing", "html", "manifest"])
def test_changed_review_output_never_validates(package: review.ReviewPackage, tmp_path: Path, mutation: str) -> None:
    output = tmp_path / "review"
    review.write_review(package, output)
    path = output / "review_records.json"
    records = deepcopy(package.records)
    if mutation == "answer":
        records[0]["import_draft"]["correct_answer"] = "CHANGED"
    elif mutation == "solution":
        records[0]["import_draft"]["explanation"] = "CHANGED"
    elif mutation in {"page", "crop", "hash"}:
        image = records[0]["parts"]["solution"]["images"][0]
        image[{"page": "page_number", "crop": "bbox", "hash": "sha256"}[mutation]] = "CHANGED"
    elif mutation == "approval":
        records[0]["academic_decision"] = "APPROVED"
    elif mutation == "rights":
        records[0]["rights_decision"] = "ALLOW_DRAFT"
    elif mutation == "delete_permission":
        report = deepcopy(package.report)
        report["replacement_preflight"]["delete_existing_questions_allowed"] = True
        (output / "readiness_report.json").write_bytes(json_bytes(report))
    elif mutation == "missing":
        path.unlink()
    elif mutation == "html":
        (output / "index.html").write_text("changed", encoding="utf-8")
    elif mutation == "manifest":
        (output / "manifest.json").write_text("{}", encoding="utf-8")
    if mutation in {"answer", "solution", "page", "crop", "hash", "approval", "rights"}:
        path.write_bytes(json_bytes(records))
    with pytest.raises(HandoffValidationError):
        review.validate_review(package, output)
    if mutation != "missing":
        with pytest.raises(HandoffValidationError):
            review.write_review(package, output)


def test_original_source_package_is_not_a_valid_output(package: review.ReviewPackage) -> None:
    with pytest.raises(HandoffValidationError, match="read-only source"):
        review.write_review(package, DEFAULT_SOURCE / "review-output")


def test_cli_missing_source_is_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--source-package", str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL"


@pytest.mark.skipif(not DEFAULT_SOURCE.is_dir(), reason="Actual original handoff required for source integration")
def test_actual_source_semantics_assets_and_deterministic_projection(package: review.ReviewPackage) -> None:
    rebuilt = review.build_review()
    assert rebuilt.files() == package.files()
    rows = [json.loads(line) for line in (DEFAULT_SOURCE / METADATA).read_text(encoding="utf-8-sig").splitlines()]
    by_id = {r["question_id"]: r for r in rows}
    for record in package.records:
        original = by_id[record["source_question_id"]]
        assert record["source_record_semantic_sha256"] == hashlib.sha256(json_bytes(original)).hexdigest()
        assert record["import_draft"]["content"] == original["parts"]["question"]["markdown"]
        assert record["import_draft"]["explanation"] == original["reference_solution"]["markdown"]
        assert record["source_answer_spec"] == original.get("answer_spec")
        for role in ("question", "solution", "answer"):
            assert record["parts"][role]["source_spans"] == original["parts"][role]["source_spans"]
    # Unknown/grouped sources stay one record per original, without child splitting.
    assert {r["source_question_id"] for r in package.records} == set(by_id)
    assert all(r["group_policy"] == "KEEP_WHOLE_SOURCE_QUESTION_UNTIL_REVIEWED" for r in package.records)


@pytest.mark.skipif(not DEFAULT_SOURCE.is_dir(), reason="Actual source assets needed for rendering")
def test_source_text_is_escaped_in_html(package: review.ReviewPackage, tmp_path: Path) -> None:
    record = deepcopy(package.records[0])
    record["import_draft"]["content"] = '<script>alert("untrusted source")</script>'
    record["chapter_title"] = '<img src=x onerror="alert(1)">'
    html = review.render_review([record], review.readiness_report([record]), DEFAULT_SOURCE, tmp_path)
    assert '<script>alert("untrusted source")</script>' not in html
    assert '<img src=x onerror="alert(1)">' not in html
    assert "&lt;script&gt;" in html



def test_full_solution_is_primary_and_key_is_optional_for_all_200_records(package):
    assert package.report["grading_reference_policy"] == "REFERENCE_SOLUTION_PRIMARY_FINAL_ANSWER_KEY_OPTIONAL"
    assert package.report["solution_reference_records"] == 200
    assert package.report["missing_reference_solution"] == 0
    assert package.report["separate_final_answer_key_required_for_step_review"] is False
    for record in package.records:
        reference = record["reference_solution"]
        assert reference["markdown"] == record["import_draft"]["explanation"]
        assert reference["source_images"] == record["parts"]["solution"]["images"]
        assert reference["source_spans"] == record["parts"]["solution"]["source_spans"]
        assert reference["academic_review"] == "PENDING"
        assert record["grading_reference"]["kind"] == "REFERENCE_SOLUTION"
        assert record["grading_reference"]["separate_final_answer_key_required"] is False
        assert record["grading_reference"]["runtime_ready"] is False
        assert "STRUCTURED_ANSWER_REVIEW_REQUIRED" not in record["step_review_blockers"]
        assert "FINAL_ANSWER_KEY_NOT_STRUCTURED" not in record["step_review_blockers"]
