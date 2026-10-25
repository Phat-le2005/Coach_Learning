from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.questions.presentation_quality import (
    has_broken_math_extraction,
    question_has_broken_math_extraction,
)


def test_curated_oxyz_source_example_is_not_safe_to_display_as_math() -> None:
    root = Path(__file__).resolve().parents[2]
    rows = json.loads((root / "data/questions/math/grade12/oxyz_v0_1/academic_review/v0_1/verified_questions.json").read_text(encoding="utf-8"))
    row = next(item for item in rows if item["candidate_id"] == "M12_OXYZ_CAND_0176")
    assert has_broken_math_extraction(row["raw_question_text"])


def test_source_quality_guard_checks_options_and_preserves_clean_math() -> None:
    assert not has_broken_math_extraction("Trong Oxyz, cho $d: \\frac{x-2}{1}=\\frac{y-1}{2}$. Tìm điểm thuộc d.")
    assert not has_broken_math_extraction("Dòng một của một đoạn văn.\nDòng hai vẫn là văn bản thông thường.")
    question = SimpleNamespace(content="Câu hỏi hợp lệ", options=[SimpleNamespace(content="A. \n1\n2\n3")])
    assert question_has_broken_math_extraction(question)
    assert not question_has_broken_math_extraction(SimpleNamespace(content="x^2 + 1 = 0", options=[]))
