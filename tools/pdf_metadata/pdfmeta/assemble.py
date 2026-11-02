from __future__ import annotations

import re


QUESTION = re.compile(r"^\s*(?:Câu|Cau|Bài|Bai|Question|Exercise)\s+(\d+)\s*[.:)]", re.IGNORECASE)
SOLUTION = re.compile(r"^\s*(?:Lời giải|Loi giai|Solution|Hướng dẫn giải|Hướng dẫn)\s*[:.]?\s*$", re.IGNORECASE)
ANSWER = re.compile(r"^\s*(?:Đáp án|Đáp số|Dap an|Dap so|Answer)(?:\s*:\s*|\s+)(.*)$", re.IGNORECASE)
RESPONSE = re.compile(r"^\s*(?:Trả lời|Tra loi)\s*:", re.IGNORECASE)


def span(page: dict, bbox: list[float], blocks: list[dict]) -> dict:
    return {"page_number": page["page_number"], "bbox": [round(x, 3) for x in bbox],
            "block_ids": [block["block_id"] for block in blocks]}


def classify_step(text: str) -> str:
    lowered = text.casefold()
    if "bảng biến thiên" in lowered or "bảng xét dấu" in lowered:
        return "SIGN_TABLE"
    if re.match(r"\s*(vậy|do đó|suy ra|kết luận|đáp số)", lowered):
        return "CONCLUSION"
    if "đạo hàm" in lowered or any(token in text for token in ("′", "", "'(")):
        return "DERIVATIVE_CALCULATION"
    if re.match(r"\s*(điều kiện|miền xác định|tập xác định)", lowered):
        return "ASSUMPTION"
    return "UNCLASSIFIED"


def assemble(pages: list[dict], source_hash: str) -> tuple[list[dict], list[dict]]:
    """Stateful across pages. No question count, answer or topic is hard-coded."""
    items: list[dict] = []
    orphans: list[dict] = []
    current = None
    section = "stem"
    for page in pages:
        blocks = [block for block in page["blocks"] if not block.get("is_margin")]
        starts = []
        for index, block in enumerate(blocks):
            match = QUESTION.match(block["text_raw"])
            if not match:
                continue
            cut = index
            # Inline fractions/superscripts can sort BEFORE their question heading.
            # Include short, overlapping math fragments in the new item's region.
            while cut > 0:
                previous = blocks[cut - 1]
                if (previous["bbox"][3] >= block["bbox"][1] - 0.5
                        and previous["bbox"][0] > block["bbox"][0] + 20
                        and len(previous["text_raw"]) < 40
                        and not QUESTION.match(previous["text_raw"])):
                    cut -= 1
                else:
                    break
            starts.append((cut, match))
        cursor = 0
        # Each region ends at the NEXT question heading, not at its final text line.
        # This retains drawings and variation tables with little or no text.
        regions = []
        for index, match in starts:
            if index > cursor:
                regions.append((cursor, index, None))
            regions.append((index, index, match))
            cursor = index
        if cursor < len(blocks):
            regions.append((cursor, len(blocks), None))
        # A heading event changes the active item; content events append to it.
        for begin, end, match in regions:
            if match:
                current = {
                    "schema_version": "math-question-candidate/v1",
                    "question_id": f"{source_hash[:16]}:q{match.group(1)}:n{len(items) + 1}",
                    "source_sha256": source_hash, "source_number": int(match.group(1)),
                    "question_type_candidate": "UNKNOWN",
                    "stem": {"text_raw": "", "source_spans": []},
                    "answer": {"text_raw": None, "source_spans": [], "verification": "UNREVIEWED"},
                    "solution": {"text_raw": "", "source_spans": []},
                    "source_regions": [], "reference_steps": [], "review_flags": [],
                    "academic_review": "PENDING", "grading_support": "NOT_ASSESSED",
                    "publishable": False, "_lines": {"stem": [], "solution": []},
                }
                items.append(current)
                section = "stem"
                continue
            region = blocks[begin:end]
            if not region:
                continue
            if current is None:
                orphans.extend([{"page_number": page["page_number"], "block_id": b["block_id"],
                                 "text_raw": b["text_raw"], "reason": "BEFORE_FIRST_QUESTION"} for b in region])
                continue
            top = max(page["content_bounds"][1], region[0]["bbox"][1] - 2)
            # Continuation begins at the content top, including tables above first text.
            if begin == 0 and not QUESTION.match(region[0]["text_raw"]):
                top = page["content_bounds"][1]
            bottom = blocks[end]["bbox"][1] - 2 if end < len(blocks) else page["content_bounds"][3]
            current["source_regions"].append(span(page, [0, top, page["width"], bottom], region))
            stem_top = top if section == "stem" else None
            solution_top = top if section == "solution" else None
            section_blocks = {"stem": [], "solution": []}
            for block in region:
                text = block["text_raw"]
                marker=block.get('section_marker_candidate',{}).get('kind')
                if marker:current['review_flags'].append('OCR_SECTION_MARKER_INFERRED')
                if RESPONSE.match(text) or marker=='RESPONSE':
                    current["question_type_candidate"] = "SHORT_ANSWER"
                    if stem_top is not None and block["bbox"][1] - 1 > stem_top:
                        current["stem"]["source_spans"].append(span(page, [0, stem_top, page["width"], block["bbox"][1] - 1], section_blocks["stem"]))
                    stem_top = None
                    section = "response"
                    continue
                if SOLUTION.match(text) or marker=='SOLUTION':
                    if stem_top is not None and block["bbox"][1] - 1 > stem_top:
                        current["stem"]["source_spans"].append(span(page, [0, stem_top, page["width"], block["bbox"][1] - 1], section_blocks["stem"]))
                    stem_top = None
                    section = "solution"
                    solution_top = block["bbox"][3] + 1
                    continue
                answer = ANSWER.match(text)
                if answer:
                    if current["answer"]["text_raw"] is not None:
                        current["review_flags"].append("MULTIPLE_ANSWER_MARKERS")
                    current["answer"]["text_raw"] = answer.group(1).strip()
                    current["answer"]["source_spans"].append(span(page, block["bbox"], [block]))
                    if section != "solution":
                        current["review_flags"].append("ANSWER_OUTSIDE_SOLUTION")
                        # Protect the stem even when OCR lost the solution label.
                        # The inferred boundary remains explicit and unapproved.
                        if stem_top is not None and block['bbox'][1]>stem_top:
                            current['stem']['source_spans'].append(span(page,[0,stem_top,page['width'],block['bbox'][1]-1],section_blocks['stem']))
                        stem_top=None;section='solution';solution_top=block['bbox'][3]+1
                        current['review_flags'].append('SOLUTION_BOUNDARY_INFERRED_FROM_ANSWER')
                    continue
                if section == "response":
                    # Preserve region source, do not silently insert answer-box content into stem.
                    current["review_flags"].append("CONTENT_BETWEEN_RESPONSE_AND_SOLUTION")
                    continue
                section_blocks[section].append(block)
                current["_lines"][section].append((page["page_number"], block))
                current[section]["text_raw"] += text + "\n"
                if block["review_flags"]:
                    current["review_flags"].extend(block["review_flags"])
            for name, y0 in (("stem", stem_top), ("solution", solution_top)):
                if y0 is not None and bottom > y0:
                    current[name]["source_spans"].append(span(page, [0, y0, page["width"], bottom], section_blocks[name]))

    for item in items:
        solution_lines = item.pop("_lines")["solution"]
        groups: list[list[tuple]] = []
        for page_number, block in solution_lines:
            kind = classify_step(block["text_raw"])
            if not groups or kind != "UNCLASSIFIED":
                groups.append([])
            groups[-1].append((page_number, block))
        for index, group in enumerate(groups, 1):
            text = "\n".join(block["text_raw"] for _, block in group)
            item["reference_steps"].append({
                "step_id": f"{item['question_id']}:s{index}",
                "kind_candidate": classify_step(group[0][1]["text_raw"]),
                "text_raw": text, "status": "SOURCE_EXCERPT_NEEDS_REVIEW",
                "source_spans": [{"page_number": number, "bbox": block["bbox"],
                                  "block_ids": [block["block_id"]]} for number, block in group],
                "math_expression": None, "checker": None, "rubric_weight": None,
            })
        if not item["answer"]["text_raw"]:
            item["review_flags"].append("MISSING_ANSWER")
        if not item["solution"]["text_raw"].strip():
            item["review_flags"].append("MISSING_SOLUTION")
        item["review_flags"].extend(["MATH_LAYOUT_NOT_VERIFIED", "REFERENCE_STEPS_NOT_VERIFIED"])
        item["review_flags"] = sorted(set(item["review_flags"]))
    return items, orphans
