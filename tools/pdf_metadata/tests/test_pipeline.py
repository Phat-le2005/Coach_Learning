from pathlib import Path

import pytest

from pdfmeta.assemble import assemble
from pdfmeta.review import build_review
from pdfmeta.quality import compare_transcriptions
from pdfmeta.enrich import attach_evidence
from pdfmeta.native import extract_native
from pdfmeta.storage import write_json
from pdfmeta.validate import validate_candidates


def line(text, number, top, *, x=20, bottom=None):
    return {"block_id": f"l{number}", "text_raw": text,
            "bbox": [x, top, 550, bottom if bottom is not None else top + 12],
            "review_flags": [], "is_margin": False}


def page(number, lines):
    return {"page_number": number, "width": 600, "height": 840,
            "content_bounds": [0, 30, 600, 800], "blocks": lines}


def test_cross_page_solution_keeps_table_area_and_stops_at_next_question():
    pages = [page(1, [line("Câu 41. Một bài", 1, 60), line("Trả lời: ...", 2, 100),
                      line("Lời giải", 3, 130), line("Đáp án: 15.", 4, 160),
                      line("Bảng biến thiên:", 5, 190)]),
             page(2, [line("Vậy a+b=15", 6, 200), line("Câu 42. Bài tiếp theo", 7, 260),
                      line("Trả lời: ...", 8, 300), line("Lời giải", 9, 330),
                      line("Đáp án 3", 10, 360), line("Có ba cực trị.", 11, 390)])]
    items, _ = assemble(pages, "abc123")
    assert len(items) == 2
    assert [s["page_number"] for s in items[0]["solution"]["source_spans"]] == [1, 2]
    assert items[0]["solution"]["source_spans"][1]["bbox"][1] == 30
    assert items[0]["solution"]["source_spans"][1]["bbox"][3] < 260
    assert "Câu 42" not in items[0]["solution"]["text_raw"]
    assert items[1]["answer"]["text_raw"] == "3"
    assert validate_candidates(items, pages)["structural_errors"] == []


@pytest.mark.parametrize("marker", ["Đáp án: 20", "Đáp án 20", "Đáp án:20", "Đáp số : 20"])
def test_answer_marker_variants(marker):
    items, _ = assemble([page(1, [line("Câu 1. Đề", 1, 60), line("Trả lời:", 2, 100),
                                 line("Lời giải", 3, 130), line(marker, 4, 160),
                                 line("Vậy được 20.", 5, 190)])], "source")
    assert items[0]["answer"]["text_raw"] == "20"
    assert "Đáp án" not in items[0]["stem"]["text_raw"]


def test_raised_fraction_belongs_to_new_question():
    pages = [page(1, [line("Câu 1. Đề", 1, 40), line("Lời giải", 2, 65),
                      line("Vậy kết thúc", 3, 90),
                      line("x+a", 4, 130, x=160, bottom=142),
                      line("Câu 2. Hàm y=...", 5, 138), line("x-1", 6, 147, x=160)])]
    items, _ = assemble(pages, "source")
    assert "x+a" not in items[0]["solution"]["text_raw"]
    assert "x+a" in items[1]["stem"]["text_raw"]
    assert items[1]["stem"]["source_spans"][0]["bbox"][1] <= 130


def test_response_at_top_of_next_page_creates_no_negative_crop():
    pages = [page(1, [line("Câu 1. Đề kéo dài", 1, 780)]),
             page(2, [line("Trả lời:", 2, 30), line("Lời giải", 3, 60),
                      line("Đáp án: 2", 4, 90), line("Vậy bằng 2", 5, 120)])]
    items, _ = assemble(pages, "source")
    assert len(items[0]["stem"]["source_spans"]) == 1
    assert validate_candidates(items, pages)["structural_errors"] == []


def test_repeated_numbers_have_distinct_ids_and_are_reported():
    pages = [page(1, [line("Câu 1. Đề A", 1, 60), line("Câu 1. Đề B", 2, 100)])]
    items, _ = assemble(pages, "source")
    report = validate_candidates(items, pages)
    assert items[0]["question_id"] != items[1]["question_id"]
    assert report["duplicate_source_numbers"] == [1]
    assert report["grading_ready_count"] == 0


def test_scan_is_not_reported_as_a_successful_question_extraction():
    items, _ = assemble([page(1, [])], "source")
    assert validate_candidates(items, [page(1, [])])["structural_status"] == "NEEDS_REVIEW"


def test_validator_rejects_private_source_overlap_and_unreviewed_promotion():
    pages = [page(1, [line("Câu 1. Đề", 1, 60), line("Lời giải", 2, 100),
                      line("Đáp án: 2", 3, 130), line("Vậy được 2", 4, 160)])]
    items, _ = assemble(pages, "source")
    items[0]["publishable"] = True
    items[0]["stem"]["source_spans"].extend(items[0]["answer"]["source_spans"])
    errors = validate_candidates(items, pages)["structural_errors"]
    assert any("UNREVIEWED_PROMOTION" in error for error in errors)
    assert any("STEM_PRIVATE_SOURCE_OVERLAP" in error for error in errors)


def test_review_payload_cannot_close_script_tag(tmp_path: Path):
    pages = [page(1, [line("Câu 1. </script><script>alert(1)</script>", 1, 60)])]
    items, _ = assemble(pages, "source")
    build_review(items, validate_candidates(items, pages), tmp_path)
    html = (tmp_path / "review.html").read_text(encoding="utf-8")
    assert "</script><script>alert(1)</script>" not in html
    assert "\\u003c/script>" in html


def test_decimal_corruption_and_variable_substitution_are_flagged():
    finding = compare_transcriptions("G(x)=0,025x2(30-x)", "G(x)=0, 0.25x^2(30-x)")
    assert "OCR_DECIMAL_DISAGREEMENT" in finding["flags"]
    assert "OCR_MALFORMED_DECIMAL" in finding["flags"]
    assert compare_transcriptions("E'(v)=600cv2", "E'(\\nu)=600c\\nu^2")["flags"] == ["OCR_LATIN_V_GREEK_NU_DISAGREEMENT"]


def test_latex_decimal_punctuation_can_match_native():
    assert compare_transcriptions("0,025", "0{,}025")["flags"] == []


def test_missing_derivative_and_changed_strict_boundary_are_flagged():
    assert "OCR_DERIVATIVE_MARK_MISSING" in compare_transcriptions("G'(x)=1,5x", "G^{\\ }(x)=1,5x")["flags"]
    assert "OCR_STRICT_BOUNDARY_CHANGED" in compare_transcriptions("v6", "\\nu\\geq6")["flags"]


@pytest.mark.parametrize("ocr", ["P^{'}(x)=0", "P^{\\prime}(x)=0", "P^\\prime(x)=0", "P'(x)=0"])
def test_equivalent_derivative_notation_is_not_flagged(ocr):
    assert "OCR_DERIVATIVE_MARK_MISSING" not in compare_transcriptions("P'(x)=0", ocr)["flags"]


def test_relations_on_different_variables_are_not_compared_as_one_bound():
    assert "OCR_STRICT_BOUNDARY_CHANGED" not in compare_transcriptions("m>0", "\\Delta\\geq0")["flags"]


def test_ocr_evidence_crossing_item_boundary_is_not_silently_assigned():
    pages = [page(1, [line("Câu 1. Đề", 1, 60), line("Câu 2. Đề", 2, 200)])]
    items, _ = assemble(pages, "source")
    experiments = [{"page_number": 1, "blocks": [{"block_id": "vl-1", "block_type": "text",
                    "text_raw": "Merged questions", "bbox": [20, 100, 550, 300], "reading_order": 1}]}]
    ambiguous, _ = attach_evidence(items, experiments, pages)
    assert ambiguous[0]["reason"] == "NO_UNAMBIGUOUS_ITEM_OWNER"
    assert all(not item.get("ocr_evidence") for item in items)


def test_output_directory_cannot_mix_different_source_documents(tmp_path: Path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"different source")
    output = tmp_path / "output"
    write_json(output / "manifest.json", {"source_sha256": "another-source"})
    with pytest.raises(ValueError, match="another source PDF"):
        extract_native(source, output)
