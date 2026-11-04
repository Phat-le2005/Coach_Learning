import json

import httpx
import pytest
import sympy as sp
from jsonschema import ValidationError

from pdfmeta.compact_review import validate
from pdfmeta.local_client import LocalClient, LocalConfig, local_schema
from pdfmeta.math_audit import audit_question
from pdfmeta.safe_math import UnsupportedMath, assignment, derivative_check, parse_expression


@pytest.mark.parametrize("formula,expected", [
    ("-x^2+2x-3", "-x**2+2*x-3"),
    (r"\frac{300}{v-6}", "300/(v-6)"),
    ("0,025x^2(30-x)", "x**2*(30-x)/40"),
    (r"\sin(x)+\cos(x)^2", "sin(x)+cos(x)**2"),
])
def test_safe_arithmetic_preserves_supported_notation(formula, expected):
    # The expected strings are test constants, never external model/source input.
    assert sp.simplify(parse_expression(formula).expression - sp.sympify(expected)) == 0


@pytest.mark.parametrize("formula", [
    "x2+3", "__import__('os')", "x[0]", "1e99999999", "1e-99999999",
    "x^999999", r"\begin{cases}x=2\end{cases}", "sin x", "1/0",
    "(" * 50 + "x" + ")" * 50,
])
def test_unsupported_ambiguous_or_unbounded_math_is_not_guessed(formula):
    with pytest.raises(UnsupportedMath):
        parse_expression(formula)


def test_derivative_identity_is_narrow_and_retains_excluded_points():
    base = assignment(r"E(v)=cv^3\frac{300}{v-6}(v>6)")
    derivative = assignment(r"E'(v)=600cv^2\frac{v-9}{(v-6)^2}")
    result = derivative_check(base, derivative)
    assert result["status"] == "PASS"
    assert "v - 6" in result["source_denominators"]
    assert base["conditions_raw"] == "(v>6)"
    assert result["scope"] == "IDENTITY_ONLY_NOT_DOMAIN_SIGN_OR_ANSWER_APPROVAL"
    assert derivative_check(base, assignment(r"E'(v)=600cv^2"))["status"] == "FAIL"


def test_chain_errors_and_different_variables_cannot_become_symbolic_pass():
    assert not assignment("E(v)=cv^3=300cv^3/(v-6)")["chain_consistent"]
    assert derivative_check(assignment("E(v)=v^3"), assignment("E'(x)=3x^2"))["status"] == "NOT_ASSESSED"


def test_ambiguous_ocr_hypotheses_can_be_checked_without_selecting_canonical():
    def candidate(latex):
        return dict(latex=latex, page_number=1, bbox=[0, 0, 100, 20], block_id=latex)
    def step(number, kind, formulas):
        return dict(step_id=str(number), kind_candidate=kind, title=kind, text_candidate="",
                    source_spans=[], latex_candidates=[candidate(s) for s in formulas])
    proposal = {"steps": [step(1, "MODEL", ["y=x^3"]),
                           step(2, "DERIVATIVE_CALCULATION", ["y'=3x^2", "y'=3x2"])]}
    result = audit_question(dict(question_id="q", source_number=1, source_sha256="a"*64), proposal)
    assert result["checks"][0]["status"] == "PASS"
    assert result["steps"][1]["formula_groups"][0]["selected_latex"] is None
    assert "OCR_FORMULA_ALTERNATIVES_UNRESOLVED" in result["flags"]
    assert result["publishable"] is False and result["academic_review"] == "PENDING"


def test_compact_metadata_adapter_never_sends_images_provenance_or_editorial_notes(tmp_path):
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]})
    client = LocalClient(LocalConfig(runtime=tmp_path, input_mode="metadata"), tmp_path / "usage.jsonl",
                         transport=httpx.MockTransport(handler))
    package = {"model_input": {"question": 152, "steps": []}, "prior_source_issues": ["GOLD_SECRET"],
               "references": [{"asset_path": "SOURCE_PATH"}]}
    client.generate([{"text": "Input:\n" + json.dumps(package)},
                     {"text": "SOURCE_PATH"}, {"inlineData": {"mimeType": "image/png", "data": "IMAGE_BYTES"}}],
                    {}, "metadata only", "job")
    payload = json.dumps(seen[0])
    assert "GOLD_SECRET" not in payload and "SOURCE_PATH" not in payload and "IMAGE_BYTES" not in payload
    assert seen[0]["messages"][1]["content"] == [{"type": "text", "text": json.dumps(package["model_input"])}]
    client.close()


def test_metadata_review_rejects_invented_step_ids_and_invalid_changes():
    with pytest.raises(ValueError, match="UNKNOWN_LOCAL_STEP_NUMBER"):
        validate(dict(status="ISSUES_FOUND", issues=[dict(code="OTHER", step_numbers=[8], note="x")], changes=[]), 7)
    with pytest.raises(ValidationError):
        validate(dict(status="NO_ISSUE_FOUND", issues=[], changes=[], publishable=True), 7)
    assert validate(dict(status="NO_ISSUE_FOUND", issues=[], changes=[]), 7) == []
    assert "COMPACT_INPUT_TRUNCATED_REVIEW_REQUIRED" in validate(
        dict(status="NO_ISSUE_FOUND", issues=[], changes=[]), 7, input_truncated=True)
    # A contradiction in the model's own status is flagged, never approved.
    assert validate(dict(status="NO_ISSUE_FOUND", issues=[dict(code="OTHER", step_numbers=[1], note="x")], changes=[]), 7)
    with pytest.raises(ValueError, match="INVALID_SPLIT_OR_MERGE"):
        validate(dict(status="ISSUES_FOUND", issues=[], changes=[dict(action="SPLIT", step_numbers=[1, 2], reason="x")]), 7)


def test_llama_schema_preserves_limits_stripped_by_cloud_portable_subset():
    schema = {"type": "object", "additionalProperties": False, "properties": {
        "notes": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 140}},
        "status": {"enum": ["YES", "NO"]}}}
    result = local_schema(schema)
    assert result["properties"]["notes"]["maxItems"] == 3
    assert result["properties"]["notes"]["items"]["maxLength"] == 140
    assert result["properties"]["status"]["type"] == "string"
    assert result["additionalProperties"] is False


def test_trial_rejects_a_different_pdf_before_reading_candidates(tmp_path):
    from pdfmeta.math_audit import run
    (tmp_path / "manifest.json").write_text(json.dumps({"source_sha256": "a"*64}))
    pdf = tmp_path / "other.pdf"
    pdf.write_bytes(b"other PDF")
    with pytest.raises(ValueError, match="REQUESTED_PDF_DIFFERS_FROM_PILOT_SOURCE"):
        run(tmp_path, tmp_path / "output", pdf=pdf)


def test_trial_cannot_overwrite_source_or_review_directories(tmp_path):
    from pdfmeta.pilot_trial import run
    for output in [tmp_path, tmp_path.parent, tmp_path / "pages/subdir", tmp_path / "reviews"]:
        with pytest.raises(ValueError, match="SEPARATE_TRIAL_OUTPUT"):
            run(tmp_path, tmp_path / "source.pdf", output, [1], math_only=True)
