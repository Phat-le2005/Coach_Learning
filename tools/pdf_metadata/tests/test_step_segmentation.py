from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
import pytest

from pdfmeta.step_segmentation import classify, propose_steps, split_reasoning, validate_grounding


def block(identifier, text, box):
    return {"block_id": identifier, "text_raw": text, "bbox": box, "glyphs": []}


def example():
    # Deliberately use different variable, distance, speed and source number than q152.
    first = [block("b1", "Khi đi ngược dòng vận tốc là u − 4", [20, 50, 280, 62]),
             block("b2", "200", [200, 72, 220, 84]),
             block("b3", "Thời gian di chuyển là t = (u > 4)", [20, 80, 300, 92]),
             block("b4", "u − 4", [198, 90, 225, 102]),
             block("b5", "200 u3", [220, 112, 260, 124]),
             block("b6", "Năng lượng tiêu hao là H(u) = 200c", [20, 120, 300, 132]),
             block("b7", "u − 4", [220, 132, 255, 144]),
             block("b8", "u − 6", [150, 162, 175, 174]),
             block("b9", "H′(u) = 400cu2 ; H′(u) = 0 ⇔ u = 6", [20, 170, 350, 182]),
             block("b10", "(u − 4)2", [145, 180, 185, 192]),
             block("b11", "Bảng biến thiên:", [20, 220, 200, 232])]
    second = [block("b12", "Vận tốc nằm trong khoảng (4;6) thì năng lượng giảm", [20, 110, 400, 122]),
              block("b13", "a = 4", [30, 130, 80, 142]),
              block("b14", "⇒ a + b = 10", [20, 140, 180, 152]),
              block("b15", "b = 6", [30, 150, 80, 162])]
    pages = {1: {"page_number": 1, "blocks": first, "width": 600, "height": 800},
             2: {"page_number": 2, "blocks": second, "width": 600, "height": 800}}
    source = {"question_id": "test:q999", "source_number": 999, "source_sha256": "a" * 64,
              "reference_steps": [{}, {}, {}], "ocr_evidence": [],
              "solution": {"source_spans": [
                  {"page_number": 1, "bbox": [0, 40, 600, 250], "block_ids": [b["block_id"] for b in first]},
                  {"page_number": 2, "bbox": [0, 30, 600, 180], "block_ids": [b["block_id"] for b in second]}]}}
    return source, pages


def test_fraction_baselines_inline_reasoning_and_cross_page_table():
    source, pages = example()
    original = deepcopy((source, pages))
    result = propose_steps(source, pages)
    steps = result["steps"]
    assert [s["kind_candidate"] for s in steps] == ["MODEL_SETUP"] * 3 + [
        "DERIVATIVE_CALCULATION", "ROOT_FINDING", "SIGN_TABLE", "CONCLUSION"]
    assert "200" in steps[1]["text_candidate"] and "200 u3" not in steps[1]["text_candidate"]
    assert "u − 6" not in steps[2]["text_candidate"]
    assert "u − 6" in steps[3]["text_candidate"]
    assert "H′(u) = 0" not in steps[3]["text_candidate"]
    assert steps[4]["text_candidate"].startswith("H′(u) = 0")
    assert any(s["page_number"] == 2 and s["bbox"][1] == 30 and s["bbox"][3] < 110
               for s in steps[5]["context_spans"])
    assert "a + b = 10" in steps[-1]["text_candidate"]
    validate_grounding(result, source, pages)
    assert (source, pages) == original


@pytest.mark.parametrize("expression", ["H′(u)=0,003u2−u", "H'(u)=0.25u", "H^{\\prime}(u)=0.003u"])
def test_decimal_coefficient_is_not_a_zero_equation(expression):
    assert classify(expression) == "DERIVATIVE_CALCULATION"


def test_interval_semicolon_is_not_a_step_separator():
    text = "H′(u)=u (u ∈ (4;6))"
    assert split_reasoning(text) == [(0, len(text))]


def test_latex_candidate_is_split_with_its_source_and_disagreements_retained():
    source, pages = example()
    source["ocr_evidence"] = [
        {"block_id": "m", "block_type": "display_formula", "page_number": 1, "bbox": [18, 160, 355, 194],
         "parser_id": "PP-FormulaNet_plus-M", "text_raw": r"H^{\prime}(u)=400cu^2\frac{u-6}{(u-4)^2};H^{\prime}(u)=0\Leftrightarrow u=6"},
        {"block_id": "s", "block_type": "display_formula", "page_number": 1, "bbox": [18, 160, 355, 194],
         "parser_id": "PP-FormulaNet_plus-S", "text_raw": r"H^{\prime}(u)=400cu^2\frac{u-7}{(u-4)^2};H^{\prime}(u)=0\Leftrightarrow u=7"}]
    steps = propose_steps(source, pages)["steps"]
    assert not steps[2]["latex_candidates"]
    assert all("Leftrightarrow" not in c["latex"] for c in steps[3]["latex_candidates"])
    assert len(steps[4]["latex_candidates"]) == 2
    assert all("frac" not in c["latex"] for c in steps[4]["latex_candidates"])


def test_wrapped_sentence_and_cases_stay_in_one_conclusion():
    source, pages = example()
    pages[2]["blocks"][0]["text_raw"] = "Vậy vận tốc tăng đến"
    pages[2]["blocks"][1]["text_raw"] = "khi động cơ dừng."
    result = propose_steps(source, pages)
    assert len(result["steps"]) == 7
    assert "khi động cơ dừng" in result["steps"][-1]["text_candidate"]
    validate_grounding(result, source, pages)


def test_missing_block_is_reported_and_other_question_blocks_are_rejected():
    source, pages = example()
    source["solution"]["source_spans"][0]["block_ids"].append("missing")
    result = propose_steps(source, pages)
    assert "MISSING_SOURCE_BLOCKS" in result["review_flags"]
    result["steps"][0]["text_slices"][0]["block_id"] = "foreign"
    with pytest.raises(ValueError, match="another question"):
        validate_grounding(result, source, pages)


def test_grounding_rejects_lost_text_duplicate_text_and_outside_context():
    source, pages = example()
    result = propose_steps(source, pages)
    lost = deepcopy(result)
    lost["steps"][1]["text_slices"].pop()
    with pytest.raises(ValueError, match="lost"):
        validate_grounding(lost, source, pages)
    duplicate = deepcopy(result)
    duplicate["steps"][0]["text_slices"].append(duplicate["steps"][0]["text_slices"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        validate_grounding(duplicate, source, pages)
    result["steps"][0]["context_spans"][0]["bbox"][1] = 0
    with pytest.raises(ValueError, match="outside"):
        validate_grounding(result, source, pages)


def test_proposals_cannot_promote_into_grading():
    source, pages = example()
    result = propose_steps(source, pages)
    result.update(candidate_generation="b" * 64, review_document_revision=0)
    schema = json.loads((Path(__file__).parents[1] / "schemas" / "solution-step-proposals.v1.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    validator.validate(result)
    result["steps"][0]["checker"] = "approved"
    with pytest.raises(ValidationError):
        validator.validate(result)


def test_glyph_descender_outside_native_region_is_flagged_and_context_clipped():
    source, pages = example()
    pages[2]["blocks"][-1]["bbox"][3] = 180.6
    result = propose_steps(source, pages)
    validate_grounding(result, source, pages)
    assert "SOURCE_GLYPH_EXTENDS_REGION" in result["review_flags"]
    assert result["steps"][-1]["context_spans"][-1]["bbox"][3] == 180
