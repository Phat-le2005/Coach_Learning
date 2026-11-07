import re

QUESTION_RE = re.compile(
    r"(?im)^\s*(?:Câu|Bài|Question|Exercise)\s*([0-9]+[a-zA-Z]?)\s*[.:)]?\s*"
)
SOLUTION_RE = re.compile(
    r"(?im)^\s*(?:Lời giải|Hướng dẫn giải|Đáp án|Solution|Answer)\s*[:.]?\s*"
)

def parse_document(pages: list[dict]) -> list[dict]:
    # Parse the complete document so solutions spanning page boundaries stay
    # attached to the question that started on the previous page.
    blocks = []
    document_parts = []
    page_ranges = []
    cursor = 0
    for page in pages:
        # Some text extractors/fixtures preserve escaped line breaks.
        text = page["text"].replace("\\n", "\n")
        start = cursor
        document_parts.append(text)
        cursor += len(text)
        page_ranges.append((start, cursor, page["page"]))
        document_parts.append("\n")
        cursor += 1

    text = "".join(document_parts)
    matches = list(QUESTION_RE.finditer(text))

    def pages_for(start: int, end: int) -> list[int]:
        return [
            page_number
            for page_start, page_end, page_number in page_ranges
            if start < page_end and end > page_start
        ]

    if matches:
        first_start = matches[0].start()
        if text[:first_start].strip():
            blocks.append({
                "question_id": f"page-{pages[0]['page']}-unsegmented",
                "question_text": text[:first_start].strip(),
                "solution_text": "",
                "pages": pages_for(0, first_start),
                "needs_review": True,
            })

        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section = text[start:end].strip()
            body = section[match.end() - start:].strip()

            sol_match = SOLUTION_RE.search(body)
            if sol_match:
                question_text = body[:sol_match.start()].strip()
                solution_text = body[sol_match.end():].strip()
            else:
                question_text, solution_text = body, ""

            blocks.append({
                "question_id": f"q-{match.group(1)}-p{pages_for(start, start + 1)[0]}",
                "question_text": question_text,
                "solution_text": solution_text,
                "pages": pages_for(start, end),
                "needs_review": not bool(question_text) or not bool(solution_text),
            })
    elif text.strip():
        blocks.append({
            "question_id": f"page-{pages[0]['page']}-unsegmented",
            "question_text": text.strip(),
            "solution_text": "",
            "pages": pages_for(0, len(text)),
            "needs_review": True,
        })

    return blocks
