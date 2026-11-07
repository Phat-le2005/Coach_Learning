"""Install ten source-backed exercises for local workspace testing only.

Preview: python -m app.seed_derivative_test_pack
Install: python -m app.seed_derivative_test_pack --apply
The original curated package is read-only. These isolated development copies
have no curriculum links, rubric, or official grading approval.
"""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from urllib.parse import quote
from uuid import UUID
import os

from app.core.config import BACKEND_DIR, get_settings
from app.database.session import get_session_factory
from app.questions.models import Question, QuestionStatus, QuestionType
from app.questions.pdf_handoff_staging import DEFAULT_SOURCE, METADATA, METADATA_SHA256, MANIFEST_SHA256, safe_file, sha256_file
from app.questions.reference_solution import SOLUTION_PRIMARY_SOURCE_TYPE
from app.seed_step_review_demo import DEMO_QUESTION_ID

PACK_FILE = BACKEND_DIR / "data/dev_only/derivative_step_review_10.json"
REPORT_FILE = BACKEND_DIR.parent / "reports/derivative_step_review_10/index.html"
PACK_ID = "derivative-step-review-10/v1"


def load_pack(source: Path = DEFAULT_SOURCE) -> list[dict]:
    pack = json.loads(PACK_FILE.read_text(encoding="utf-8"))
    if (pack["schema_version"] != PACK_ID or pack["source_metadata_sha256"] != METADATA_SHA256
            or pack["academic_publication_approved"] is not False or pack["official_grading_approved"] is not False):
        raise ValueError("Test pack identity changed")
    # Check the pinned catalog and only the evidence used by this local pack.
    # The separate handoff validator still checks the entire 9,979-file package.
    for relative, digest in ((METADATA, METADATA_SHA256), ("manifest.sha256", MANIFEST_SHA256)):
        if sha256_file(safe_file(source, relative)) != digest:
            raise ValueError("Source catalog identity changed")
    rows = [json.loads(line) for line in safe_file(source, METADATA).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    checked_pdfs = set()
    by_id = {row["question_id"]: row for row in rows}
    items = pack["questions"]
    if len(items) != 10 or len({x["source_question_id"] for x in items}) != 10:
        raise ValueError("Expected ten distinct source exercises")
    for index, item in enumerate(items, 101):
        if item["id"] != f"c0000000-0000-0000-0000-{index:012d}":
            raise ValueError("Unexpected development question ID")
        row = by_id[item["source_question_id"]]
        if row["chapter_id"] != "derivative_applications" or row["source"]["sha256"] != item["source_pdf_sha256"]:
            raise ValueError("Source chapter or PDF lineage changed")
        if item["source_pdf_sha256"] not in checked_pdfs:
            pdf = safe_file(source, "03_chay_lai_pipeline/original_pdfs/" + item["source_pdf_sha256"] + ".pdf")
            if sha256_file(pdf) != item["source_pdf_sha256"]:
                raise ValueError("Source PDF bytes changed")
            checked_pdfs.add(item["source_pdf_sha256"])
        if not item["content"].strip() or not item["reference_solution"].strip():
            raise ValueError("A readable question and solution are required")
        for role in ("question", "solution"):
            if item["source_fragments"][role] != row["parts"][role]["fragments"]:
                raise ValueError("Source image evidence changed")
            for fragment in item["source_fragments"][role]:
                path = safe_file(source / "01_metadata_200_cau", fragment["source_asset"])
                if sha256_file(path) != fragment["source_asset_sha256"]:
                    raise ValueError("Source image bytes changed")
    return items


def write_reference_booklet(items: list[dict], source: Path, output: Path) -> None:
    """Offline source booklet; never exposed through the student problem API."""
    output.parent.mkdir(parents=True, exist_ok=True)
    sections = []
    for number, item in enumerate(items, 1):
        images = {}
        for role in ("question", "solution"):
            parts = []
            for fragment in item["source_fragments"][role]:
                asset = safe_file(source / "01_metadata_200_cau", fragment["source_asset"])
                relative = quote(Path(os.path.relpath(asset, output.parent)).as_posix(), safe="/")
                parts.append(f'<img src="{escape(relative, quote=True)}" alt="{role} · trang {fragment["page_number"]}">')
            images[role] = "".join(parts)
        sections.append(f'<section><h2>Bài {number:02d} · {escape(item["title"])}</h2>'
                        f'<p>ID: {item["id"]} · Nguồn: {escape(item["source_question_id"])}</p>'
                        f'{images["question"]}<details><summary>Đối chiếu lời giải gốc</summary>{images["solution"]}</details></section>')
    output.write_text('<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>10 bài đạo hàm · Kiểm thử EduMS</title><style>body{font:16px system-ui;background:#f3f8f2;color:#173d31;max-width:1100px;margin:auto;padding:20px}'
        'section{background:white;border:1px solid #c5d9ce;border-radius:14px;padding:20px;margin:20px 0}img{display:block;max-width:100%;height:auto;margin:16px auto}'
        'summary{cursor:pointer;font-weight:600;padding:12px}p{overflow-wrap:anywhere}@media print{details{display:none}section{break-inside:avoid}}</style>'
        '<h1>Bộ 10 bài đạo hàm để thử chấm từng bước</h1>'
        '<p>Vào /student/attempts → chọn nhóm “Bộ 10 bài đạo hàm” → mở bài. Viết hoặc tải ảnh, trích xuất OCR, sửa và xác nhận từng bước, rồi nộp và yêu cầu nhận xét.</p>'
        '<p>Bản thử local: lời giải được đối chiếu ảnh nguồn; không phải bộ câu hỏi đã được duyệt phát hành. Nhận xét AI là tạm thời; chưa có rubric điểm chính thức.</p>'
        '<p>Kiểm thử cả bài đúng, sai dấu đạo hàm, thiếu điều kiện, cách giải khác và OCR nhận sai rồi sửa. So sánh nhận xét với lời giải gốc bên dưới.</p>'
        + "".join(sections) + '</html>', encoding="utf-8")


def install(*, apply: bool = False, source: Path = DEFAULT_SOURCE) -> dict:
    if get_settings().app_env not in {"development", "test"}:
        raise RuntimeError("Development test pack is disabled in production")
    items = load_pack(source)
    with get_session_factory()() as session:
        base = session.get(Question, DEMO_QUESTION_ID)
        if base is None or base.source_type != "SAMPLE_TEST" or base.status != QuestionStatus.APPROVED:
            raise RuntimeError("Expected development workspace sample is missing")
        pending = []
        for item in items:
            pages = ",".join(str(x["page_number"]) for x in item["source_fragments"]["question"])
            expected = dict(subject_id=base.subject_id, created_by=base.created_by,
                content=item["content"], explanation=item["reference_solution"], correct_answer=None,
                question_type=QuestionType.OPEN_RESPONSE, difficulty=0.5, exam_weight=0.0,
                source_type=SOLUTION_PRIMARY_SOURCE_TYPE,
                source_reference=f"DEV_ONLY | {PACK_ID} | {item['source_question_id']} | PDF p.{pages} | sha256:{item['source_pdf_sha256']}",
                status=QuestionStatus.APPROVED)
            existing = session.get(Question, UUID(item["id"]))
            if existing is not None:
                if (any(getattr(existing, key) != value for key, value in expected.items())
                        or existing.concept_links or existing.problem_type_links or existing.learning_outcome_links):
                    raise RuntimeError(f"Question ID conflict: {item['id']}; nothing was overwritten")
            else:
                pending.append(Question(id=UUID(item["id"]), **expected))
        # Validate the entire batch before any writes; one transaction, rerunnable.
        if apply:
            session.add_all(pending)
            session.commit()
    write_reference_booklet(items, source, REPORT_FILE)
    return {"status": "installed" if apply else "preview", "questions": len(items),
            "inserted": len(pending) if apply else 0, "pending_insert": len(pending),
            "existing": len(items) - len(pending), "official_rubrics_created": 0,
            "source_files_modified": False, "booklet": str(REPORT_FILE)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(install(apply=args.apply), ensure_ascii=True, indent=2))
