"""Prepare all source questions for review without publishing or touching a DB."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html import escape
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.questions.reference_solution import SOLUTION_PRIMARY_SOURCE_TYPE

from app.questions.pdf_handoff_staging import (
    DATA_ROOT, DEFAULT_SOURCE, MANIFEST_SHA256, METADATA, METADATA_SHA256,
    HandoffValidationError, json_bytes, safe_file, structural_blockers,
    validate_rows, verify_lineage, verify_source,
)


DEFAULT_REVIEW_OUTPUT = DATA_ROOT / "questions/math/grade12/pdf_handoff_200_v0_1/review_preparation/v0_1"
CHAPTER_CODES = {
    "derivative_applications": "DERIVATIVE_APPLICATIONS",
    "integrals": "INTEGRALS",
    "grouped_statistics": "GROUPED_DATA_DISPERSION",
    "probability": "PROBABILITY_CHAPTER",
}
EXPECTED_REPLACEMENT_CHAPTERS = frozenset({
    *CHAPTER_CODES.values(), "VECTORS_GEOMETRY", "OXYZ_CHAPTER",
})
# Target identifiers verified against the existing Math 12 development catalog.
# Selecting this context does not approve an academic taxonomy mapping.
TARGET_SUBJECT_CODE = "MATH_G12"
TARGET_CURRICULUM_VERSION_CODE = "GDPT2018_2018"
JSON_FILES = ("review_records.json", "readiness_report.json")
REVIEW_FILES = (*JSON_FILES, "index.html")
KNOWN_SOURCE_ISSUES = {
    "011b4f91bb93163d:q1:n12": "SOURCE_ARITHMETIC_CONFLICT_450_MINUS_350_EQUALS_200",
}


def prepare_record(row: dict[str, Any], documents: dict[str, str]) -> dict[str, Any]:
    spec = row.get("answer_spec") or {}
    kind = spec.get("kind")
    question_type = {"MULTIPLE_CHOICE": "MULTIPLE_CHOICE", "NUMBER": "SHORT_ANSWER"}.get(kind)
    answer = spec.get("expected_label") if kind == "MULTIPLE_CHOICE" else spec.get("expected_decimal") if kind == "NUMBER" else None
    issues = structural_blockers(row)
    blockers = [
        "ACADEMIC_REVIEW_PENDING", "RIGHTS_REVIEW_REQUIRED",
        "TAXONOMY_REVIEW_REQUIRED", "DIFFICULTY_AND_EXAM_WEIGHT_REQUIRED",
        "SOURCE_PRESENTATION_REVIEW_REQUIRED", "DUPLICATE_REVIEW_REQUIRED",
        *issues,
    ]
    if question_type is None:
        blockers.append("QUESTION_TYPE_REVIEW_REQUIRED")
    known_issue = KNOWN_SOURCE_ISSUES.get(row["question_id"])
    if known_issue:
        blockers.append(known_issue)
    solution_present = bool(row["reference_solution"]["markdown"].strip() and row["parts"]["solution"]["fragments"])
    question_pages = sorted({span["page_number"] for span in row["parts"]["question"]["source_spans"]})
    # This is a source projection, not a QuestionImportRecord or approved answer.
    draft = {
        "subject_code": TARGET_SUBJECT_CODE,
        "curriculum_version_code": TARGET_CURRICULUM_VERSION_CODE,
        "source": SOLUTION_PRIMARY_SOURCE_TYPE,
        "source_reference": f"pdf-handoff:{row['question_id']} | pages:{','.join(map(str, question_pages))} | sha256:{row['source']['sha256']}",
        "source_year": None,
        "content": row["parts"]["question"]["markdown"],
        "question_type": question_type,
        "difficulty": None,
        "exam_weight": None,
        "correct_answer": answer,
        "explanation": row["reference_solution"]["markdown"],
        "options": [
            {"label": choice["label"], "content": choice["markdown"], "order_index": index}
            for index, choice in enumerate(row["parts"]["question"].get("choices", []))
        ] if kind == "MULTIPLE_CHOICE" else [],
        "concepts": [], "problem_types": [], "learning_outcomes": [],
    }
    parts = {}
    for role in ("question", "solution", "answer"):
        part = row["parts"][role]
        parts[role] = {
            "markdown": part["markdown"],
            "source_spans": part["source_spans"],
            "images": [{
                "package_path": "01_metadata_200_cau/" + fragment["source_asset"],
                "sha256": fragment["source_asset_sha256"],
                "page_number": fragment["page_number"],
                "bbox": fragment["bbox"],
            } for fragment in part["fragments"]],
        }
    return {
        "candidate_id": "PDF200_" + hashlib.sha256(row["question_id"].encode()).hexdigest()[:24],
        "source_question_id": row["question_id"],
        "collection_number": row["collection_number"],
        "chapter_id": row["chapter_id"],
        "chapter_title": row["chapter_title"],
        "chapter_code_hint": CHAPTER_CODES[row["chapter_id"]],
        "grade_level": 12,
        "target_curriculum_code": "GDPT2018",
        "status": "PENDING_SOURCE_REVIEW",
        "source_usage_group": row["usage_group"],
        "source_academic_review": row["academic_review"],
        "source_record_semantic_sha256": hashlib.sha256(json_bytes(row)).hexdigest(),
        "source_metadata_sha256": METADATA_SHA256,
        "source_pdf": {**row["source"], "package_path": documents[row["source"]["sha256"]]},
        "source_answer_spec": row.get("answer_spec"),
        "presentation_mode": row["presentation_mode"],
        "source_text_review_reasons": row.get("text_review_reasons", []),
        "parts": parts,
        "import_draft": draft,
        "reference_solution": {
            "markdown": row["reference_solution"]["markdown"],
            "source_images": parts["solution"]["images"],
            "source_spans": parts["solution"]["source_spans"],
            "academic_review": row["academic_review"],
        },
        "grading_reference": {
            "kind": "REFERENCE_SOLUTION",
            "reference_solution_present": solution_present,
            "separate_final_answer_key_required": False,
            "runtime_ready": False,
            "requires_approved_source": True,
            "official_score_requires_approved_rubric_or_teacher": True,
        },
        "step_review_blockers": [
            "ACADEMIC_REVIEW_PENDING", "RIGHTS_REVIEW_REQUIRED",
            "REFERENCE_SOLUTION_TEXT_REVIEW_REQUIRED", "TAXONOMY_REVIEW_REQUIRED",
        ] + ([known_issue] if known_issue else []),
        "objective_auto_scoring_blockers": (["FINAL_ANSWER_KEY_NOT_STRUCTURED"] if not spec else []) + issues,
        "answer_availability": {
            "reference_solution_present": solution_present,
            "answer_location": "REFERENCE_SOLUTION" if solution_present else "UNESTABLISHED",
            "structured_final_key_present": bool(spec),
            "key_extraction_status": "SOURCE_KEY_CANDIDATE" if spec else "NOT_SEPARATED_FROM_SOLUTION",
            "academic_correctness_verified": False,
        },
        "extraction_coverage": {
            "question_source_crop_count": len(parts["question"]["images"]),
            "solution_source_crop_count": len(parts["solution"]["images"]),
            "separate_answer_source_crop_count": len(parts["answer"]["images"]),
            "question_source_available": bool(parts["question"]["images"]),
            "solution_source_available": bool(parts["solution"]["images"]),
            "text_and_latex_completeness": "NOT_ESTABLISHED",
        },
        "structured_final_answer_present": bool(spec),
        "structurally_complete_final_answer": not issues,
        "group_policy": "KEEP_WHOLE_SOURCE_QUESTION_UNTIL_REVIEWED",
        "promotion_blockers": blockers,
        "academic_decision": "PENDING",
        "rights_decision": "PENDING",
        "database_import_allowed": False,
        "production_release_eligible": False,
        "step_grading_ready": False,
        "rubric": None,
    }


def readiness_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    chapters = Counter(record["chapter_code_hint"] for record in records)
    blockers = Counter(code for record in records for code in record["promotion_blockers"])
    return {
        "schema_version": "pdf-handoff-review-preparation/v1",
        "status": "PREPARED_FOR_REVIEW_REPLACEMENT_BLOCKED",
        "source_manifest_sha256": MANIFEST_SHA256,
        "source_metadata_sha256": METADATA_SHA256,
        "total_questions": len(records),
        "with_source_solution": sum(bool(r["parts"]["solution"]["images"]) for r in records),
        "grading_reference_policy": "REFERENCE_SOLUTION_PRIMARY_FINAL_ANSWER_KEY_OPTIONAL",
        "separate_final_answer_key_required_for_step_review": False,
        "solution_reference_records": sum(r["grading_reference"]["reference_solution_present"] for r in records),
        "missing_reference_solution": sum(not r["grading_reference"]["reference_solution_present"] for r in records),
        "with_answer_in_reference_solution": sum(r["answer_availability"]["reference_solution_present"] for r in records),
        "answer_not_separated_from_solution": sum(not r["answer_availability"]["structured_final_key_present"] for r in records),
        "source_crop_counts": {role: sum(len(r["parts"][role]["images"]) for r in records) for role in ("question", "solution", "answer")},
        "text_and_latex_completeness": "NOT_ESTABLISHED",
        "with_structured_final_answer": sum(r["structured_final_answer_present"] for r in records),
        "structurally_complete_final_answer": sum(r["structurally_complete_final_answer"] for r in records),
        "question_type_candidates": dict(Counter(r["import_draft"]["question_type"] or "UNREVIEWED" for r in records)),
        "chapter_counts": dict(chapters),
        "blocker_counts": dict(blockers),
        "importable_questions": 0,
        "official_step_grading_ready": 0,
        "replacement_preflight": {
            "status": "BLOCKED",
            "delete_existing_questions_allowed": False,
            "replace_database_allowed": False,
            "required_chapters": sorted(EXPECTED_REPLACEMENT_CHAPTERS),
            "missing_chapters": sorted(EXPECTED_REPLACEMENT_CHAPTERS - set(chapters)),
            "reasons": ["ACADEMIC_AND_RIGHTS_REVIEW_INCOMPLETE", "IMPORT_METADATA_INCOMPLETE", "REPLACEMENT_CHAPTER_COVERAGE_INCOMPLETE"],
            "policy": "KEEP_CURRENT_DATABASE_UNTIL_REVIEW_AND_REPLACEMENT_PREFLIGHT_PASS",
        },
    }


def _local_url(output: Path, source: Path, relative: str) -> str:
    path = safe_file(source, relative)
    try:
        local_path = os.path.relpath(path, output)
    except ValueError:
        # Windows cannot express a relative path between two different drives.
        # The review is a local artifact, so use the actual source file URI.
        return path.as_uri()
    return quote(Path(local_path).as_posix(), safe="/.")


def render_review(records: list[dict[str, Any]], report: dict[str, Any], source: Path, output: Path) -> str:
    sections = []
    for record in records:
        parts = []
        for role, label in (("question", "Đề bài gốc"), ("solution", "Lời giải gốc"), ("answer", "Vùng đáp án riêng")):
            part = record["parts"][role]
            if not part["images"]:
                continue
            figures = []
            for image in part["images"]:
                image_url = escape(_local_url(output, source, image["package_path"]), quote=True)
                page = image["page_number"]
                pdf_url = escape(_local_url(output, source, record["source_pdf"]["package_path"]) + f"#page={page}", quote=True)
                figures.append(f'<figure><a href="{image_url}" target="_blank" rel="noopener"><img loading="lazy" src="{image_url}" alt="{label} · trang nguồn {page}"></a><figcaption>Trang PDF gốc {page} · <a href="{pdf_url}" target="_blank" rel="noopener">Mở trang nguồn</a> · Bấm ảnh để phóng to</figcaption></figure>')
            parts.append(f'<section class="source-part"><h3>{label}</h3>{"".join(figures)}</section>')
        draft = record["import_draft"]
        key = draft["correct_answer"]
        key_text = f'Khóa cuối trích từ nguồn: {escape(str(key))}' if key is not None else 'Đáp án nằm trong lời giải nguồn; chưa tách thành khóa riêng'
        options = "".join(f'<li><strong>{escape(str(o["label"]))}.</strong> {escape(o["content"])}</li>' for o in draft["options"])
        flags = "".join(f'<li>{escape(flag)}</li>' for flag in record["promotion_blockers"])
        ident = escape(record["source_question_id"], quote=True)
        search = escape(f'{record["collection_number"]} {record["source_question_id"]} {record["chapter_title"]} {draft["content"]}'.casefold(), quote=True)
        sections.append(f'''<details class="question" data-chapter="{escape(record['chapter_id'], quote=True)}" data-search="{search}">
<summary>Câu nguồn {record['collection_number']} · {escape(record['chapter_title'])}<span>{'Đủ cấu trúc khóa cuối' if record['structurally_complete_final_answer'] else 'Cần xử lý nguồn'}</span></summary>
<div class="question-body"><p class="muted">ID: {ident} · PENDING · {escape(str(draft['question_type'] or 'Chưa xác nhận loại câu'))}</p>
<p><strong>{key_text}</strong> — chưa phải đáp án đã duyệt.</p><div class="source-grid">{''.join(parts)}</div>
<details><summary>Văn bản trích và phương án — bản nháp để đối chiếu</summary><pre>{escape(draft['content'])}</pre><ol>{options}</ol><pre>{escape(draft['explanation'])}</pre></details>
<details><summary>Điều kiện còn thiếu để import</summary><ul>{flags}</ul></details>
<label for="note-{record['candidate_id']}">Ghi chú khi đối chiếu nguồn</label><textarea id="note-{record['candidate_id']}" data-source-id="{ident}" rows="2" placeholder="Ghi vị trí sai, thiếu hoặc cần giáo viên kiểm tra. Không sửa tự động dữ liệu nguồn."></textarea>
</div></details>''')
    chapter_labels = {r["chapter_id"]: r["chapter_title"] for r in records}
    options = "".join(f'<option value="{escape(key, quote=True)}">{escape(title)}</option>' for key, title in sorted(chapter_labels.items()))
    return '''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Duyệt bộ 200 câu Toán 12</title><style>
:root{font-family:system-ui,sans-serif;color:#183d32;background:#f3f8f2}*{box-sizing:border-box}body{max-width:1440px;margin:auto;padding:24px}h1{margin-bottom:8px}h3{margin-top:0}a{color:#135e46}header,.question{background:white;border:1px solid #c5d9ce;border-radius:14px;margin-bottom:16px;padding:20px}.warning{padding:16px;background:#fff4d9;border-left:4px solid #b17216}.toolbar{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0}input,select,button,textarea{font:inherit;border:1px solid #9eb8aa;border-radius:8px;padding:10px;background:white;color:inherit}input{flex:1;min-width:200px}button{cursor:pointer}textarea{display:block;width:100%;margin-top:8px}summary{cursor:pointer;font-weight:650;padding:8px;overflow-wrap:anywhere}summary span{display:block;font-size:.85rem;font-weight:400;color:#526d61;margin-top:5px}.source-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:20px}.source-part{background:#f8fbf7;border:1px solid #d2e1d7;border-radius:10px;padding:12px}figure{margin:12px 0}img{width:100%;height:auto;display:block;background:white;border:1px solid #d5ded8}figcaption,.muted{font-size:.85rem;color:#536e62;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;background:#f7faf6;padding:12px}.question-body{padding-top:12px}.question-body>details{margin:16px 0}label{font-weight:600}:focus-visible{outline:3px solid #a86d18;outline-offset:3px}[hidden]{display:none!important}@media(max-width:600px){body{padding:10px}header,.question{padding:12px}.toolbar>*{width:100%}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
</style></head><body><header><p class="muted">BẢN DUYỆT NỘI BỘ · KHÔNG PHẢI KHO BÀI ĐÃ PHÁT HÀNH</p><h1>Đề và lời giải của 200 câu Toán 12</h1>
<p>200 câu có lời giải tham chiếu · Chấm từng bước dựa vào lời giải, không bắt buộc khóa đáp án riêng · 0 câu đã được duyệt để thay DB.</p>
<p class="warning">Giữ nguyên database cũ. Toàn bộ nguồn còn PENDING; chưa có quyền sử dụng được duyệt, mapping đầy đủ hoặc rubric chấm từng bước. Bộ này chưa có Vectơ và Oxyz. Ảnh gốc có thể in nổi bật đáp án; chỉ dùng để duyệt.</p>
<p>Xem trực tiếp đề và lời giải bằng ảnh gốc; văn bản OCR là bản nháp. Giữ cùng vị trí tương đối với gói nguồn, không chuyển riêng file HTML. Ghi chú chỉ được tải thành tệp khi bấm xuất, không tự lưu hoặc gửi lên máy chủ.</p>
<div class="toolbar"><input id="search" aria-label="Tìm câu" placeholder="Tìm số câu, ID hoặc nội dung"><select id="chapter" aria-label="Lọc chương"><option value="">Tất cả chương</option>''' + options + '''</select><button type="button" id="export">Xuất ghi chú đối chiếu</button></div><p id="count" role="status">Hiển thị 200/200 câu</p></header>''' + "".join(sections) + '''<script>
const questions=[...document.querySelectorAll('.question')];
function filter(){const term=document.getElementById('search').value.trim().toLocaleLowerCase('vi');const chapter=document.getElementById('chapter').value;let count=0;for(const item of questions){item.hidden=!(item.dataset.search.includes(term)&&(!chapter||item.dataset.chapter===chapter));if(!item.hidden)count++;}document.getElementById('count').textContent=`Hiển thị ${count}/200 câu`;}
document.getElementById('search').addEventListener('input',filter);document.getElementById('chapter').addEventListener('change',filter);
document.getElementById('export').addEventListener('click',()=>{const notes=[...document.querySelectorAll('textarea[data-source-id]')].filter(e=>e.value.trim()).map(e=>({source_question_id:e.dataset.sourceId,note:e.value.trim()}));const payload={schema_version:'pdf-handoff-source-review-notes/v1',source_metadata_sha256:''' + json.dumps(METADATA_SHA256) + ''',academic_approval:false,notes};const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='pdf-handoff-review-notes.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
</script></body></html>'''


@dataclass(frozen=True)
class ReviewPackage:
    records: list[dict[str, Any]]
    report: dict[str, Any]
    html: str
    aggregate_sha256: str

    def files(self) -> dict[str, bytes]:
        return {"review_records.json": json_bytes(self.records), "readiness_report.json": json_bytes(self.report), "index.html": self.html.encode("utf-8")}


def build_review(source: Path = DEFAULT_SOURCE, output: Path = DEFAULT_REVIEW_OUTPUT) -> ReviewPackage:
    rows, declared = verify_source(source)
    validate_rows(rows)
    verify_lineage(source, rows, declared)
    plan = json.loads((source / "03_chay_lai_pipeline/plan.relative.json").read_text(encoding="utf-8-sig"))
    documents = {doc["sha256"]: "03_chay_lai_pipeline/" + doc["path"] for doc in plan["documents"]}
    records = [prepare_record(row, documents) for row in sorted(rows, key=lambda row: row["collection_number"])]
    report = readiness_report(records)
    if report["with_source_solution"] != 200 or report["with_structured_final_answer"] != 43 or report["structurally_complete_final_answer"] != 40:
        raise HandoffValidationError("The pinned handoff's solution/answer counts changed")
    payloads = {"review_records.json": json_bytes(records), "readiness_report.json": json_bytes(report)}
    aggregate = hashlib.sha256(b"".join(name.encode() + b"\0" + payloads[name] for name in sorted(payloads))).hexdigest()
    return ReviewPackage(records, report, render_review(records, report, source, output), aggregate)


def check_output_directory(output: Path, source: Path) -> None:
    if output.resolve().is_relative_to(source.resolve()) or source.resolve().is_relative_to(output.resolve()):
        raise HandoffValidationError("Review output must be separate from the read-only source package")
    if output.exists():
        unexpected = {path.name for path in output.iterdir()} - set(REVIEW_FILES)
        if unexpected:
            raise HandoffValidationError("Undeclared review files: " + ", ".join(sorted(unexpected)))
        if any((output / name).is_symlink() for name in REVIEW_FILES):
            raise HandoffValidationError("Review output symlinks are forbidden")


def write_review(package: ReviewPackage, output: Path, source: Path = DEFAULT_SOURCE) -> None:
    check_output_directory(output, source)
    for name, payload in package.files().items():
        path = output / name
        if path.exists() and path.read_bytes() != payload:
            raise HandoffValidationError(f"Refusing to overwrite changed review output: {name}")
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in package.files().items():
        (output / name).write_bytes(payload)


def validate_review(package: ReviewPackage, output: Path, source: Path = DEFAULT_SOURCE) -> None:
    check_output_directory(output, source)
    for name, payload in package.files().items():
        path = output / name
        if not path.is_file() or path.read_bytes() != payload:
            raise HandoffValidationError(f"Review output differs from pinned projection: {name}")
