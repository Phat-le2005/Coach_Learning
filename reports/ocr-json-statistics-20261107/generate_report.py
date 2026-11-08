"""Count the published OCR JSON labels without reclassifying source records."""

import argparse
import csv
import hashlib
import json
from pathlib import Path


JOBS = (
    "ocr-direct-full - Copy",
    "ocr-direct-grouped_statistics",
    "ocr-direct-probability",
)
MISSING = "Chưa có nhãn chính"


def label_key(label):
    return (label or {}).get("code")


def label_name(label):
    return (label or {}).get("name") or MISSING


def type_candidates(method):
    labels = {}
    for label in method.get("exercise_type_candidates", []):
        if label and label.get("code"):
            labels[label["code"]] = label
    for field in ("candidates", "inference_candidates"):
        for candidate in method.get(field, []):
            label = candidate.get("exercise_type")
            code = candidate.get("exercise_type_code") or label_key(label)
            if code:
                labels.setdefault(code, label or {"code": code, "name": code})
    return labels


def bucket(mapping, label, child_field):
    return mapping.setdefault(
        label_key(label),
        {"label": label, "questions": 0, "primary_type": 0,
         "candidate_type_only": 0, "no_type_evidence": 0, child_field: {}},
    )


def increment(node, method):
    node["questions"] += 1
    if method.get("exercise_type"):
        node["primary_type"] += 1
    elif type_candidates(method):
        node["candidate_type_only"] += 1
    else:
        node["no_type_evidence"] += 1


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    return ["| " + " | ".join(map(cell, headers)) + " |",
            "| " + " | ".join("---" for _ in headers) + " |"] + [
        "| " + " | ".join(map(cell, row)) + " |" for row in rows
    ]


def write_csv(path, headers, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path("C:/CoachLearningPdf"))
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        "snapshot_date": "2026-11-07",
        "counting_unit": "One EXERCISE JSON record; subquestions are not split.",
        "grouping": "Exact primary label codes within each chapter and lesson; no relabeling.",
        "candidate_counting": "Deduplicated per record and type code; non-additive across types.",
        "sources": [], "chapters": [],
    }
    detail_rows, candidate_rows, chapters, candidates = [], [], {}, {}
    all_ids = set()
    for job in JOBS:
        path = args.source_root / job / "content.method.pretty.json"
        payload = path.read_bytes()
        records = json.loads(payload)
        draft_path = path.with_name("content.draft.pretty.json")
        draft_payload = draft_path.read_bytes()
        draft = json.loads(draft_payload)
        ids = [record["question_id"] for record in records]
        assert len(ids) == len(set(ids)), f"Duplicate IDs in {job}"
        assert not all_ids.intersection(ids), f"Duplicate IDs across sources: {job}"
        all_ids.update(ids)
        assert ids == [record["question_id"] for record in draft], job
        excluded = []
        pages = []
        for record in records:
            method = record["method"]
            if method["record_kind"] != "EXERCISE":
                assert method["record_kind"] == "SOURCE_HEADING_NOT_EXERCISE"
                excluded.append({"question_id": record["question_id"],
                                 "collection_number": record["collection_number"],
                                 "record_kind": method["record_kind"],
                                 "lesson": method.get("lesson")})
                continue
            chapter_label, lesson_label, type_label = (
                method.get(field) for field in ("chapter", "lesson", "exercise_type")
            )
            chapter = bucket(chapters, chapter_label, "lessons")
            chapter["source_job"] = job
            lesson = bucket(chapter["lessons"], lesson_label, "types")
            increment(chapter, method)
            increment(lesson, method)
            type_node = lesson["types"].setdefault(label_key(type_label),
                                                  {"label": type_label, "questions": 0})
            type_node["questions"] += 1
            for code, candidate_label in type_candidates(method).items():
                key = (label_key(chapter_label), label_key(lesson_label), code)
                node = candidates.setdefault(key, {
                    "chapter": chapter_label, "lesson": lesson_label,
                    "type": candidate_label, "mentions": 0, "without_primary_type": 0,
                })
                node["mentions"] += 1
                node["without_primary_type"] += int(not type_label)
            pages.extend(span["page_number"] for span in record["question"]["source_spans"])
        report["sources"].append({
            "job": job, "path": str(path.resolve()),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "draft_sha256": hashlib.sha256(draft_payload).hexdigest(),
            "records": len(records), "questions": len(records) - len(excluded),
            "excluded_headings": excluded, "draft_question_ids_match": True,
            "question_page_min": min(pages), "question_page_max": max(pages),
            "declared_source_page_counts": sorted({r["source"]["page_count"] for r in records}),
        })
        assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(payload).digest()

    for chapter in chapters.values():
        assert sum(lesson["questions"] for lesson in chapter["lessons"].values()) == chapter["questions"]
        for lesson in chapter["lessons"].values():
            assert sum(t["questions"] for t in lesson["types"].values()) == lesson["questions"]
            for type_node in lesson["types"].values():
                labels = (chapter["label"], lesson["label"], type_node["label"])
                detail_rows.append([chapter["source_job"]] + [
                    value for label in labels for value in (label_key(label), label_name(label))
                ] + [type_node["questions"]])
            assert sum(lesson[key] for key in ("primary_type", "candidate_type_only", "no_type_evidence")) == lesson["questions"]
            lesson["types"] = list(lesson["types"].values())
        chapter["lessons"] = list(chapter["lessons"].values())
        report["chapters"].append(chapter)
    report["totals"] = {
        "records": sum(source["records"] for source in report["sources"]),
        "excluded_headings": sum(len(source["excluded_headings"]) for source in report["sources"]),
        **{key: sum(chapter[key] for chapter in report["chapters"])
           for key in ("questions", "primary_type", "candidate_type_only", "no_type_evidence")},
        "missing_primary_lesson": sum(lesson["questions"] for chapter in report["chapters"]
                                      for lesson in chapter["lessons"] if not lesson["label"]),
    }
    assert report["totals"]["records"] == report["totals"]["questions"] + report["totals"]["excluded_headings"]
    for node in candidates.values():
        candidate_rows.append([value for label in (node["chapter"], node["lesson"], node["type"])
                               for value in (label_key(label), label_name(label))]
                              + [node["mentions"], node["without_primary_type"]])

    lines = ["# Thống kê câu hỏi trong ba JSON OCR — 07/11/2026", "",
             "Đếm trực tiếp `content.method.pretty.json` đang có ở `C:/CoachLearningPdf/`.", "",
             "- Một bản ghi `EXERCISE` được tính là một câu; không tách các ý a/b/c/d.",
             "- Loại các bản ghi `SOURCE_HEADING_NOT_EXERCISE` khỏi số câu hỏi.",
             "- Phân nhóm theo `method.chapter`, `method.lesson`, `method.exercise_type`; giữ nguyên mã và tên nhãn chính.",
             "- Nhãn ứng viên không cộng vào bảng dạng chính. Bảng ứng viên ở file CSV riêng, mỗi câu chỉ được tính một lần cho mỗi mã dạng; một câu có thể thuộc nhiều ứng viên.",
             "- Nhãn hiện tại đều cần duyệt; đây là thống kê metadata, không phải xác nhận phân loại học thuật.",
             "- Bản `ocr-direct-full - Copy` mới là phần xuất của 1.800 trang đầu trong PDF 2.947 trang; không coi là toàn bộ sách.",
             "- Phần thống kê có các mã bài từ nguồn và mã suy luận tên gần giống nhau; giữ riêng. Nhãn bài ghép “1,2” cũng giữ riêng vì chưa có căn cứ tách 63 câu cho từng bài.", "",
             "## Tổng theo chương", ""]
    lines += table(["Chương", "Số câu", "Có dạng chính", "Chỉ có ứng viên dạng", "Chưa có căn cứ dạng"],
                   [[label_name(c["label"]), c["questions"], c["primary_type"],
                     c["candidate_type_only"], c["no_type_evidence"]] for c in report["chapters"]]
                   + [["TỔNG", *[report["totals"][key] for key in
                                  ("questions", "primary_type", "candidate_type_only", "no_type_evidence")]]])
    lines += ["", f"Tổng {report['totals']['records']:,} bản ghi JSON, gồm {report['totals']['questions']:,} câu hỏi và {report['totals']['excluded_headings']} tiêu đề bài. Có {report['totals']['missing_primary_lesson']} câu chưa có bài chính.", ""]
    for i, chapter in enumerate(report["chapters"], 1):
        lines += [f"## {i}. {label_name(chapter['label'])} — {chapter['questions']} câu", "",
                  f"Nguồn: `{chapter['source_job']}/content.method.pretty.json`.", ""]
        lines += table(["Bài / chủ đề theo nhãn chính", "Mã bài", "Số câu", "Có dạng chính", "Chưa có dạng chính"],
                       [[label_name(l["label"]), label_key(l["label"]) or "—", l["questions"],
                         l["primary_type"], l["questions"] - l["primary_type"]] for l in chapter["lessons"]])
        for lesson in chapter["lessons"]:
            lines += ["", f"### {label_name(lesson['label'])} — {lesson['questions']} câu", ""]
            lines += table(["Dạng theo nhãn chính", "Mã dạng", "Số câu"],
                           [[label_name(t["label"]), label_key(t["label"]) or "—", t["questions"]]
                            for t in lesson["types"]])
            if lesson["questions"] != lesson["primary_type"]:
                lines += ["", f"Trong số chưa có dạng chính: {lesson['candidate_type_only']} câu có ứng viên dạng; {lesson['no_type_evidence']} câu chưa có căn cứ dạng."]
        lines += [""]
    lines += ["## Đối chiếu nguồn", ""]
    lines += table(["Nguồn", "Bản ghi", "Câu hỏi", "Tiêu đề loại ra", "Trang chứa câu hỏi", "Số trang PDF khai báo"],
                   [[s["job"], s["records"], s["questions"], len(s["excluded_headings"]),
                     f"{s['question_page_min']}–{s['question_page_max']}",
                     ", ".join(map(str, s["declared_source_page_counts"]))] for s in report["sources"]])
    lines += ["", "Đã đối chiếu số lượng, thứ tự và ID với `content.draft.pretty.json`; ID không trùng trong/giữa ba file. Tổng các dạng bằng tổng bài; tổng các bài bằng tổng chương. SHA-256 từng file được lưu trong `summary.json`.", "",
              "Các file kèm theo: `primary-detail.csv` (đếm cộng được theo nhãn chính), `candidate-detail.csv` (số lượt gợi ý, không cộng thành tổng câu), `summary.json` (cây thống kê và thông tin kiểm chứng).", ""]
    (args.output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (args.output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(args.output / "primary-detail.csv",
              ["source", "chapter_code", "chapter", "lesson_code", "lesson", "type_code", "type", "questions"], detail_rows)
    write_csv(args.output / "candidate-detail.csv",
              ["chapter_code", "chapter", "primary_lesson_code", "primary_lesson", "candidate_type_code", "candidate_type", "question_mentions", "without_primary_type"], candidate_rows)
    print(json.dumps(report["totals"], ensure_ascii=False, indent=2))
    for chapter in report["chapters"]:
        print(label_name(chapter["label"]), chapter["questions"], chapter["primary_type"], chapter["candidate_type_only"], chapter["no_type_evidence"])
    print(f"Report: {args.output / 'report.md'}")


if __name__ == "__main__":
    main()
