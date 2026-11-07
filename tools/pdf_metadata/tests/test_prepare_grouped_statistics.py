import hashlib
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_grouped_statistics import TAXONOMY, classify, read_json, substantive_solution, table_descriptor


@pytest.fixture
def types():
    return {item["code"]: item for item in read_json(TAXONOMY / "problem_types.json")}


def test_question_text_overrides_stale_pdf_heading(types):
    question = "Câu 51. Tính khoảng biến thiên của mẫu số liệu ghép nhóm. Trả lời: ..."
    candidate = classify(question, "", types)
    assert candidate["primary_problem_type_code"] == "CALCULATE_GROUPED_RANGE"
    assert candidate["topic_codes"] == ["GROUPED_RANGE_IQR_TOPIC"]
    assert candidate["question_type_candidate"] == "SHORT_ANSWER"
    assert candidate["scope_status"] == "GROUPED_DISPERSION_CANDIDATE"


def test_implicit_measure_is_flagged_and_does_not_create_verified_answer(types):
    candidate = classify(
        "Hai quả bất kì có hiệu số cân nặng không vượt quá 200 g. Đúng hay sai? Giải thích.",
        "Lời giải chưa kiểm chứng", types,
    )
    assert candidate["primary_problem_type_code"] == "CONCLUDE_FROM_GROUPED_DISPERSION"
    assert "CALCULATE_GROUPED_RANGE" in candidate["problem_type_codes"]
    assert candidate["classification_confidence"] == "LOW"
    assert "INFERRED_MEASURE_REVIEW" in candidate["review_flags"]
    assert candidate["question_type_candidate"] == "OPEN_RESPONSE"


def test_solution_heading_is_not_counted_as_a_worked_solution():
    assert not substantive_solution("Lời giải\n")
    assert substantive_solution("Lời giải\nVì Q_3-Q_1=5, khoảng tứ phân vị là 5.")


def test_table_geometry_never_invents_cell_values_and_checks_hash(tmp_path):
    image = Image.new("RGB", (320, 250), "white")
    draw = ImageDraw.Draw(image)
    draw.line((25, 70, 300, 70), fill="black", width=2)
    draw.line((25, 110, 300, 110), fill="black", width=2)
    draw.line((65, 30, 65, 210), fill="black", width=2)
    path = tmp_path / "table.png"
    image.save(path)
    asset = {
        "id": "table-test", "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "page_number": 1, "bbox": [0, 0, 100, 100],
    }
    result = table_descriptor(asset, tmp_path)
    assert result["structure_status"] == "GRID_GEOMETRY_CANDIDATE"
    assert result["cells"]
    assert all(cell["text"] is None and cell["value"] is None for cell in result["cells"])
    asset["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        table_descriptor(asset, tmp_path)
