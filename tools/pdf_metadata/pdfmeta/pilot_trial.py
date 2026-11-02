"""Reproducible local metadata trial over an existing, hash-matched PDF pilot."""
from __future__ import annotations

import argparse
from collections import Counter
from html import escape
import json
from pathlib import Path
from statistics import median
import time

from .compact_review import run as compact_run
from .math_audit import run as audit_run
from .storage import file_hash, read_json, write_json


def snapshot(pilot: Path, pdf: Path):
    paths = [pdf, pilot / "manifest.json", pilot / "questions.candidates.jsonl",
             pilot / "questions.enriched.candidates.jsonl", *sorted((pilot / "pages").glob("*"))]
    paths += [p for p in [pilot / "reviews/state.json", pilot / "curation.json",
                         pilot / "steps/questions.steps.jsonl"] if p.exists()]
    return {str(p.resolve()): file_hash(p) for p in paths if p.is_file()}


def build_view(output: Path, audits: list[dict], results: list[dict], report: dict):
    def e(value):
        return escape(str(value), quote=True)
    lookup = {r["source_package"]["source_number"]: r for r in results}
    failures = {r["source_number"]: r for r in (report.get("qwen") or {}).get("failures", [])}
    cards = []
    for audit in audits:
        n = audit["source_number"]
        record = lookup.get(n)
        failed = failures.get(n)
        checks = Counter(c["status"] for c in audit["checks"])
        detail = "".join(f'<li>{e(flag)}</li>' for flag in audit["flags"])
        body = "".join(f'<details><summary>Bước {s["number"]}: {e(s["title"])}</summary>'
                       f'<pre>{e(s["text_candidate"])}</pre></details>' for s in audit["steps"])
        ai = '<p>Chưa có kết quả Qwen hợp lệ trong lượt thử này.</p>'
        package = record["source_package"] if record else None
        if record:
            ai = f'<h4>Qwen: {e(record["result"]["status"])}</h4><pre>{e(json.dumps(record["result"], ensure_ascii=False, indent=2))}</pre>'
        elif failed and failed.get("job_key"):
            directory = output / "qwen/jobs" / failed["job_key"]
            package = read_json(directory / "package.json")
            ai = f'<h4>Phản hồi bị chặn: {e(failed["error_code"])}</h4>'
            if (directory / "response.json").exists():
                raw = read_json(directory / "response.json")
                ai += f'<details><summary>Phản hồi gốc chưa được chấp nhận</summary><pre>{e(json.dumps(raw.get("result", {}), ensure_ascii=False, indent=2))}</pre></details>'
        if package:
            ai += '<details><summary>Ảnh PDF gốc để đối chiếu</summary>'
            for ref in package["references"]:
                path = "qwen/" + ref["asset_path"]
                ai += f'<p>{e(ref["part"])} · Trang {ref["page_number"]}</p><img loading="lazy" src="{e(path)}" alt="Ảnh nguồn câu {n}">'
            ai += '</details>'
        cards.append(f'<details class="question"><summary>Câu {n} · {len(audit["steps"])} bước đề xuất · '
                     f'Kiểm tra ký hiệu: {e(dict(checks))}</summary><ul>{detail}</ul>{body}{ai}</details>')
    content = f'''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Thử pipeline metadata — {report['math']['page_count']} trang</title><style>
body{{font:15px/1.6 system-ui,sans-serif;background:#f3f6fa;color:#21334b;margin:0}}
main{{max-width:1120px;margin:36px auto;padding:0 24px}}h1{{font-size:28px;margin-bottom:8px}}
.notice{{background:#fff4d6;border:1px solid #edce82;padding:20px;border-radius:12px}}
.question{{background:white;padding:16px 20px;margin:12px 0;border:1px solid #dce4ed;border-radius:12px}}
summary{{cursor:pointer;font-weight:600}}details details{{margin:12px 0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.7 ui-monospace,monospace;background:#f5f8fb;padding:16px;border-radius:8px}}
img{{max-width:100%;height:auto;border:1px solid #dde4ef}}a{{color:#116d65}}li{{overflow-wrap:anywhere}}
</style><main><h1>Thử pipeline metadata · {report['math']['page_count']} trang · {len(audits)} câu</h1>
<p>Qwen chỉ đọc chữ/OCR và trả gợi ý. Ảnh bên dưới dành cho người đối chiếu; không gửi vào lượt suy luận metadata.</p>
<div class="notice"><b>Chưa đủ điều kiện dùng trực tiếp để chấm.</b> PASS chỉ xác nhận phép đồng nhất đạo hàm cho một cách đọc OCR;
không xác nhận cách đọc, miền xác định, bảng biến thiên hay đáp án cuối. Các bước vẫn là đề xuất.</div>
<p><a href="report.json">Báo cáo tổng</a> · <a href="math-report.json">Kiểm tra cả file</a> ·
<a href="questions.math-audit.pretty.json">Metadata có kiểm tra</a> · <a href="qwen/report.json">Lượt Qwen</a></p>
<pre>{e(json.dumps(report, ensure_ascii=False, indent=2))}</pre><h2>{len(audits)} câu đã trích xuất</h2>{''.join(cards)}</main></html>'''
    (output / "review.html").write_text(content, encoding="utf-8")


def run(pilot: Path, pdf: Path, output: Path, numbers: list[int], *, limit=8, max_output_tokens=768, math_only=False):
    pilot, pdf, output = pilot.resolve(), pdf.resolve(), output.resolve()
    if (output == pilot or pilot.is_relative_to(output)
            or any(output.is_relative_to(pilot / name) for name in ("pages", "reviews", "steps", "exports"))):
        raise ValueError("USE_A_SEPARATE_TRIAL_OUTPUT_DIRECTORY")
    if not 1 <= limit <= 20 or not 128 <= max_output_tokens <= 2048:
        raise ValueError("BOUNDED_TRIAL_LIMIT_REQUIRED")
    if len(numbers) != len(set(numbers)):
        raise ValueError("DUPLICATE_REQUESTED_QUESTION")
    started = time.perf_counter()
    before = snapshot(pilot, pdf)
    audits, math = audit_run(pilot, output, pdf=pdf)
    if set(numbers) - {a["source_number"] for a in audits}:
        raise ValueError("REQUESTED_QUESTION_NOT_FOUND")
    records, qwen = [], None
    if not math_only:
        records, qwen = compact_run(pilot, output / "qwen", audits, numbers, limit=limit,
                                    max_output_tokens=max_output_tokens)
    after = snapshot(pilot, pdf)
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    seconds = [r["seconds"] for r in records if r.get("seconds") is not None]
    report = {"schema_version": "pilot-metadata-trial/v1", "source_path": str(pdf), "math": math,
              "qwen": qwen, "sample_numbers": numbers[:limit] if not math_only else [],
              "sample_is_random": False, "sample_is_whole_file_review": False,
              "successful_inference_median_seconds": round(median(seconds), 3) if seconds else None,
              "seconds": round(time.perf_counter() - started, 3),
              "source_integrity": {"checked_files": len(before), "changed_files": changed},
              "bulk_decision": "NOT_READY_FOR_AUTOMATIC_GRADING_OR_UNATTENDED_FULL_CORPUS",
              "next_gate": "Improve OCR coverage and independently evaluate source/answer errors before scaling"}
    write_json(output / "report.json", report)
    build_view(output, audits, records, report)
    if changed:
        raise ValueError("SOURCE_INPUTS_CHANGED_DURING_TRIAL")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--questions", default="151,152,154,158,213,260,157,161")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--max-output-tokens", type=int, default=768)
    parser.add_argument("--math-only", action="store_true")
    args = parser.parse_args()
    report = run(args.pilot, args.pdf, args.output, [int(n.strip()) for n in args.questions.split(",")],
                 limit=args.limit, max_output_tokens=args.max_output_tokens, math_only=args.math_only)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
