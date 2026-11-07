from __future__ import annotations

import re
import unicodedata


DECOR = r'[\s\uE000-\uF8FF☞☛◆►➤•✓✔»›→]*'
QUESTION = re.compile(r"^"+DECOR+r"(?:Câu|Cau|Bài|Bai|Ví dụ|Vi du|Question|Exercise|Example)\s+(\d+)(?:\.\d+)*\s*(?:[.:)]|$)", re.IGNORECASE)
SOLUTION = re.compile(r"^"+DECOR+r"(?:Lời giải|Loi giai|Giải|Giai|Solution|Hướng dẫn giải|Hướng dẫn)\s*[:.]?\s*$", re.IGNORECASE)
ANSWER = re.compile(r"^"+DECOR+r"(?:Đáp án|Đáp số|Dap an|Dap so|Answer)(?:\s*:\s*|\s+)(.*)$", re.IGNORECASE)
RESPONSE = re.compile(r"^"+DECOR+r"(?:Trả lời|Tra loi)\s*:", re.IGNORECASE)


def is_contents_page(page):
    """Require a contents heading plus list structure; do not drop lesson pages."""
    texts=[b['text_raw'].strip() for b in page['blocks']]
    plain=lambda s:''.join(c for c in unicodedata.normalize('NFKD',s) if not unicodedata.combining(c)).lower()
    heading=any(re.fullmatch(r'mu[a-z]{0,2}c\s+lu[a-z]{0,2}c|table of contents|contents',plain(s)) for s in texts[:12])
    leaders=sum(bool(re.search(r'(?:\.\s*){6,}',s)) for s in texts)
    lessons=sum(bool(re.match(r'^(?:Bài|Bai|Chapter|Chương)\s+\d+',s,re.I)) for s in texts)
    return heading and (leaders>=3 or lessons>=3)


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
        if is_contents_page(page):
            orphans.extend({'page_number':page['page_number'],'block_id':b['block_id'],
                            'text_raw':b['text_raw'],'reason':'TABLE_OF_CONTENTS_PAGE_EXCLUDED'} for b in page['blocks'])
            current=None
            continue
        blocks = [block for block in page["blocks"] if not block.get("is_margin")]
        starts = []
        for index, block in enumerate(blocks):
            if block.get('source_book_inner_label'):
                continue
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
                    "source_label": match.group(0).strip(),
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
                # A filled "Trả lời:" inside a solution is an answer, not a
                # student's empty response area. Keep the following proof lines.
                response_answer = RESPONSE.match(text) if section == "solution" else None
                if (RESPONSE.match(text) or marker=='RESPONSE') and section != "solution":
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
                response_value = RESPONSE.sub('', text).strip() if response_answer else ''
                if response_answer and re.fullmatch(r'[\s.…_]*', response_value):
                    response_value = ''
                if answer or response_value:
                    if current["answer"]["text_raw"] is not None:
                        current["review_flags"].append("MULTIPLE_ANSWER_MARKERS")
                    current["answer"]["text_raw"] = answer.group(1).strip() if answer else response_value
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
