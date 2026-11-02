"""Layout-grounded reasoning-step proposals, separate from raw acquisition and grading."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import time

from jsonschema import Draft202012Validator

from .storage import file_hash, read_json, write_json, write_jsonl
from .text_cleanup import is_suspicious, normalize_block, overlap


VERSION = "layout-reasoning/v2"
TITLES = {
    "MODEL_SETUP": "Lập quan hệ / mô hình",
    "DERIVATIVE_CALCULATION": "Tính đạo hàm",
    "ROOT_FINDING": "Giải phương trình / tìm điểm tới hạn",
    "SIGN_TABLE": "Lập bảng xét dấu / biến thiên",
    "CONCLUSION": "Rút ra kết luận",
    "ASSUMPTION": "Xác định điều kiện",
    "UNCLASSIFIED": "Đoạn cần phân loại",
}
PROSE = re.compile(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", re.I)
PRIME = r"(?:[′'’]+|\^\{?\\prime\}?)"
DERIVATIVE = re.compile(r"[A-Za-z]\s*" + PRIME)
DERIVATIVE_EQUATION = re.compile(r"[A-Za-z]\s*" + PRIME + r"\s*(?:\([^)]*\))?\s*=")
ROOT = re.compile(r"[A-Za-z]\s*" + PRIME + r"\s*(?:\([^)]*\))?\s*=\s*0(?![\d.,])")
NEW_IDEA = re.compile(
    r"^\s*(?:ta có|xét |gọi |đặt |khi |thời gian|vận tốc|năng lượng|doanh thu|lợi nhuận|"
    r"chi phí|diện tích|thể tích|quãng đường|gia tốc|tính |giải |điều kiện|miền xác định|"
    r"tập xác định|vậy|do đó|suy ra|kết luận|từ bảng|có bảng|bảng biến thiên|bảng xét dấu)", re.I)


def classify(text: str) -> str:
    low = text.strip().casefold()
    if re.match(r"^(?:(?:ta\s+)?có\s+)?bảng\s+(?:biến thiên|xét dấu)", low):
        return "SIGN_TABLE"
    if re.match(r"^(?:vậy|do đó|suy ra|kết luận|từ bảng)", low):
        return "CONCLUSION"
    if re.match(r"^(?:điều kiện|miền xác định|tập xác định)", low):
        return "ASSUMPTION"
    if ROOT.search(text) or (low.startswith("giải ") and "=" in text):
        return "ROOT_FINDING"
    if DERIVATIVE_EQUATION.search(text) or "đạo hàm" in low:
        return "DERIVATIVE_CALCULATION"
    if re.match(r"^(?:ta có|xét |gọi |đặt |khi |thời gian|vận tốc|năng lượng|doanh thu|"
                r"lợi nhuận|chi phí|diện tích|thể tích|quãng đường)", low):
        return "MODEL_SETUP"
    return "UNCLASSIFIED"


def title_for(kind: str, text: str) -> str:
    if kind == "MODEL_SETUP":
        for token, title in (("thời gian", "Xác định thời gian"), ("năng lượng", "Lập hàm năng lượng"),
                             ("vận tốc", "Xác định vận tốc"), ("doanh thu", "Lập hàm doanh thu"),
                             ("lợi nhuận", "Lập hàm lợi nhuận")):
            if token in text.casefold():
                return title
    return TITLES[kind]


def split_reasoning(text: str) -> list[tuple[int, int]]:
    """Split only an explicit new root-finding statement after a top-level separator.

    In particular, never split an interval (a;b), a cases environment, or decimals.
    Offsets refer to the normalized string, not raw glyph indices.
    """
    cuts, stack = [0], []
    for i, char in enumerate(text):
        if char in "([{":
            stack.append(char)
        elif char in ")]}":
            if stack:
                stack.pop()
        elif char in ";." and not stack:
            rest = text[i + 1:]
            if ROOT.match(rest.lstrip()) and classify(text[cuts[-1]:i]) == "DERIVATIVE_CALCULATION":
                cuts.append(i + 1)
    return [(a, b) for a, b in zip(cuts, cuts[1:] + [len(text)]) if text[a:b].strip(" ;.")]


def _union(boxes: list[list[float]]) -> list[float]:
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _units(source: dict, pages: dict[int, dict]) -> tuple[list[dict], list[str]]:
    wanted = {(s["page_number"], bid) for s in source["solution"]["source_spans"] for bid in s["block_ids"]}
    blocks, flags = [], []
    for number, page in sorted(pages.items()):
        for block in page["blocks"]:
            if (number, block["block_id"]) not in wanted:
                continue
            text, quality = normalize_block(block)
            blocks.append({"page_number": number, "block": block, "text": text, "quality": quality})
    found = {(b["page_number"], b["block"]["block_id"]) for b in blocks}
    if wanted - found:
        flags.append("MISSING_SOURCE_BLOCKS")
    if not blocks:
        flags.append("NO_GROUNDED_SOLUTION_BLOCKS")
    units = []
    for number in sorted({b["page_number"] for b in blocks}):
        local = [b for b in blocks if b["page_number"] == number]
        left = min(b["block"]["bbox"][0] for b in local)
        anchors = [b for b in local if
                   (PROSE.search(b["text"]) and len(b["text"].split()) >= 3)
                   or (b["block"]["bbox"][0] <= left + 35 and
                       (re.search(r"[=⇒⇔]", b["text"]) or NEW_IDEA.match(b["text"])))]
        if not anchors:
            # Unsupported math-only/table regions are retained, never silently discarded.
            anchors = local[:1]
        by_id = {b["block"]["block_id"]: {"anchor": b, "parts": [b], "page_number": number} for b in anchors}
        for fragment in local:
            if fragment["block"]["block_id"] in by_id:
                continue
            box = fragment["block"]["bbox"]
            scored = []
            for anchor in anchors:
                ab = anchor["block"]["bbox"]
                vertical = max(0, min(box[3], ab[3]) - max(box[1], ab[1]))
                horizontal = max(0, min(box[2], ab[2]) - max(box[0], ab[0]))
                distance = abs((box[1] + box[3] - ab[1] - ab[3]) / 2)
                # Raised numerator/denominator belongs to the overlapping baseline,
                # even when its extraction order comes before that baseline.
                scored.append(((bool(vertical and horizontal), vertical if horizontal else 0, -distance), anchor))
            scored.sort(key=lambda pair: pair[0], reverse=True)
            owner = scored[0][1]
            by_id[owner["block"]["block_id"]]["parts"].append(fragment)
            if not scored[0][0][0]:
                flags.append("FRAGMENT_ATTACHMENT_NEEDS_REVIEW")
        for unit in by_id.values():
            unit["parts"].sort(key=lambda part: (part["block"]["bbox"][1], part["block"]["bbox"][0]))
            unit["bbox"] = _union([p["block"]["bbox"] for p in unit["parts"]])
            units.append(unit)
    return sorted(units, key=lambda u: (u["page_number"], u["anchor"]["block"]["bbox"][1])), flags


def _latex(source: dict, unit: dict, kind: str, corrections: list[dict]) -> list[dict]:
    edits = {c["block_id"]: c["latex"] for c in corrections}
    candidates = []
    # Match the baseline, not a raised fragment that may overlap a nearby formula.
    for block in source.get("ocr_evidence", []):
        if block["page_number"] != unit["page_number"] or not overlap(unit["anchor"]["block"]["bbox"], block["bbox"]):
            continue
        if block["block_type"] in {"formula", "display_formula", "inline_formula"}:
            expressions = [edits.get(block["block_id"], block["text_raw"]).strip().strip("$").strip()]
        elif block["block_type"] == "text":
            expressions = [m[0] or m[1] for m in re.findall(r"\$\$([\s\S]*?)\$\$|\$([^$\n]+)\$", block["text_raw"])]
        else:
            continue
        for expression in expressions:
            chunks = [expression[a:b].strip(" ;.") for a, b in split_reasoning(expression)]
            for chunk in chunks:
                if any(is_suspicious(c) for c in chunk):
                    continue
                if len(chunks) > 1 and classify(chunk) != kind:
                    continue
                rank = 0 if block["block_id"] in edits else 1 if block["parser_id"].endswith("-M") else 2
                candidates.append((rank, {"block_id": block["block_id"], "parser_id": block["parser_id"],
                    "page_number": block["page_number"], "bbox": block["bbox"], "latex": chunk,
                    "status": "EDITORIAL_CANDIDATE" if rank == 0 else "OCR_CANDIDATE_NOT_VERIFIED"}))
    candidates.sort(key=lambda pair: pair[0])
    seen, result = set(), []
    for _, candidate in candidates:
        key = re.sub(r"\s+", "", candidate["latex"])
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result[:3]


def propose_steps(source: dict, pages: dict[int, dict], corrections: list[dict] | None = None) -> dict:
    units, flags = _units(source, pages)
    steps = []
    for unit in units:
        anchor = unit["anchor"]
        ranges = split_reasoning(anchor["text"])
        for part_index, (start, end) in enumerate(ranges):
            anchor_text = anchor["text"][start:end].strip(" ;.")
            kind = classify(anchor_text)
            # Once a table heading is seen, the next prose baseline is a new
            # interpretation/conclusion, even if it lacks 'Vậy' on the next page.
            if steps and steps[-1]["kind_candidate"] == "SIGN_TABLE" and kind != "SIGN_TABLE":
                kind = "CONCLUSION"
            # A wrapped sentence is a continuation, not a fresh 'Khi...' setup.
            wrapped = (bool(steps) and anchor_text[:1].islower()
                       and not re.search(r"[=⇒⇔]", anchor_text))
            if wrapped:
                kind = "UNCLASSIFIED"
            new = (not steps or len(ranges) > 1 or kind != "UNCLASSIFIED" or NEW_IDEA.match(anchor_text))
            if wrapped:
                new = False
            if not new:
                step = steps[-1]
            else:
                step = {"step_id": f"{source['question_id']}:reasoning:{len(steps) + 1}", "kind_candidate": kind,
                        "title": title_for(kind, anchor_text), "text_candidate": "", "text_slices": [], "source_spans": [],
                        "context_spans": [], "latex_candidates": [], "conditions_candidate": [],
                        "boundary_reasons": [], "review_flags": ["STEP_MEANING_NOT_VERIFIED"],
                        "status": "PROPOSED_NEEDS_REVIEW", "math_expression": None, "checker": None, "rubric_weight": None}
                steps.append(step)
            if len(ranges) > 1:
                step["boundary_reasons"].append("EXPLICIT_INLINE_REASONING_SEPARATOR")
                step["review_flags"].append("SHARED_SOURCE_LINE_SPLIT")
            else:
                step["boundary_reasons"].append("LAYOUT_AND_LANGUAGE_CUE" if new else "CONTINUATION")
            selected = []
            for p in unit["parts"]:
                is_anchor = p is anchor
                if not is_anchor and len(ranges) > 1:
                    # Fractions are attached to the calculation, never repeated as
                    # text in its inline root-finding statement. Shared image stays explicit.
                    if part_index != 0:
                        continue
                text = anchor_text if is_anchor else p["text"]
                selected.append(text)
                step["text_slices"].append({"page_number": p["page_number"], "block_id": p["block"]["block_id"],
                    "normalized_start": start if is_anchor else 0,
                    "normalized_end": end if is_anchor else len(p["text"])})
                step["source_spans"].append({"page_number": p["page_number"], "bbox": p["block"]["bbox"],
                                              "block_ids": [p["block"]["block_id"]]})
                if p["quality"]["unresolved_glyph_count"]:
                    step["review_flags"].append("UNRESOLVED_FONT_GLYPHS")
            step["text_candidate"] += ("\n" if step["text_candidate"] else "") + "\n".join(selected)
            step["latex_candidates"].extend(_latex(source, unit, kind, corrections or []))
            for match in re.finditer(r"\([^()]*[<>≤≥][^()]*\)", anchor_text):
                step["conditions_candidate"].append({"text": match[0], "source_block_id": anchor["block"]["block_id"],
                                                     "status": "EXPLICIT_SOURCE_TEXT_NOT_VERIFIED"})
    # Context follows the actual solution region, including graphic-only gaps and
    # table continuation above the first text line on a subsequent page.
    for index, step in enumerate(steps):
        own = step["source_spans"]
        first = min((s["page_number"], s["bbox"][1]) for s in own)
        following = steps[index + 1]["source_spans"] if index + 1 < len(steps) else []
        stop = min(((s["page_number"], s["bbox"][1]) for s in following), default=(float("inf"), 0))
        for region in source["solution"]["source_spans"]:
            page_number = region["page_number"]
            if page_number < first[0] or page_number > stop[0]:
                continue
            y0 = max(region["bbox"][1], first[1] - 2) if page_number == first[0] else region["bbox"][1]
            y1 = min(region["bbox"][3], stop[1] - 1) if page_number == stop[0] else region["bbox"][3]
            here = [s["bbox"] for s in own if s["page_number"] == page_number]
            if here:
                y0 = min(y0, min(b[1] for b in here))
                y1 = max(y1, max(b[3] for b in here))
            if y0 < region["bbox"][1] or y1 > region["bbox"][3]:
                step["review_flags"].append("SOURCE_GLYPH_EXTENDS_REGION")
                y0, y1 = max(y0, region["bbox"][1]), min(y1, region["bbox"][3])
            if y1 > y0:
                x0, x1 = region["bbox"][0], region["bbox"][2]
                if here and step["kind_candidate"] != "SIGN_TABLE":
                    x0, x1 = max(x0, min(b[0] for b in here) - 8), min(x1, max(b[2] for b in here) + 8)
                step["context_spans"].append({"page_number": page_number,
                    "bbox": [x0, y0, x1, y1],
                    "block_ids": [bid for s in own if s["page_number"] == page_number for bid in s["block_ids"]]})
        step["previous_step_id"] = steps[index - 1]["step_id"] if index else None
        step["dependency_status"] = "ORDER_ONLY_NOT_LOGICAL_PROOF"
        step["review_flags"] = sorted(set(step["review_flags"] + ["NATIVE_MATH_LAYOUT_LOSSY"]))
        if len({(s["page_number"], s["block_id"]) for s in step["text_slices"]}) > 8 or len(step["text_candidate"]) > 800:
            step["review_flags"].append("LONG_STEP_REQUIRES_SPLIT_REVIEW")
        if step["kind_candidate"] == "UNCLASSIFIED":
            step["review_flags"].append("STEP_KIND_UNRESOLVED")
        if step["kind_candidate"] == "SIGN_TABLE":
            step["review_flags"].append("TABLE_CONTENT_AND_ASSUMPTIONS_NEED_REVIEW")
        step["latex_candidates"] = list({json.dumps(c, sort_keys=True): c for c in step["latex_candidates"]}.values())
        flags.extend(f for f in step["review_flags"] if f in {
            "LONG_STEP_REQUIRES_SPLIT_REVIEW", "STEP_KIND_UNRESOLVED", "SOURCE_GLYPH_EXTENDS_REGION", "UNRESOLVED_FONT_GLYPHS"})
    return {"schema_version": "solution-step-proposals/v1", "algorithm": VERSION,
            "question_id": source["question_id"], "source_number": source["source_number"],
            "source_sha256": source["source_sha256"], "legacy_group_count": len(source["reference_steps"]),
            "steps": steps, "review_flags": sorted(set(flags)), "source_review_notes": [], "academic_review": "PENDING",
            "grading_support": "NOT_ASSESSED", "publishable": False}


def validate_grounding(record: dict, source: dict, pages: dict[int, dict]) -> None:
    """Every available source character belongs to one proposal slice, exactly once.

    Full-line images can overlap for inline splits; normalized text ranges cannot.
    A missing native block is an explicit extraction flag, not fabricated evidence.
    """
    lookup = {(n, b["block_id"]): b for n, p in pages.items() for b in p["blocks"]}
    expected = {(s["page_number"], bid) for s in source["solution"]["source_spans"] for bid in s["block_ids"]}
    coverage = {}
    seen_ids = set()
    for index, step in enumerate(record["steps"]):
        if step["step_id"] in seen_ids or step["previous_step_id"] != (record["steps"][index - 1]["step_id"] if index else None):
            raise ValueError("Invalid proposal sequence")
        seen_ids.add(step["step_id"])
        for sliced in step["text_slices"]:
            key = sliced["page_number"], sliced["block_id"]
            if key not in expected or key not in lookup:
                raise ValueError("Proposal refers to another question's source block")
            text = normalize_block(lookup[key])[0]
            start, end = sliced["normalized_start"], sliced["normalized_end"]
            if not 0 <= start < end <= len(text):
                raise ValueError("Invalid normalized source range")
            used = coverage.setdefault(key, set())
            chars = set(range(start, end))
            if chars & used:
                raise ValueError("Duplicate source text between proposed steps")
            used.update(chars)
        for span in step["context_spans"]:
            b = span["bbox"]
            if not any(span["page_number"] == s["page_number"] and
                       s["bbox"][0] <= b[0] < b[2] <= s["bbox"][2] and
                       s["bbox"][1] <= b[1] < b[3] <= s["bbox"][3] for s in source["solution"]["source_spans"]):
                raise ValueError("Context extends outside this question's solution")
    for key in expected & lookup.keys():
        if coverage.get(key, set()) != set(range(len(normalize_block(lookup[key])[0]))):
            raise ValueError("Source text lost during step segmentation")


def run(pilot: Path) -> dict:
    started = time.perf_counter()
    candidate_path = pilot / "questions.enriched.candidates.jsonl"
    generation = file_hash(candidate_path)
    manifest = read_json(pilot / "manifest.json")
    sources = [json.loads(line) for line in candidate_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    pages = {p["page_number"]: p for p in (read_json(path) for path in (pilot / "pages").glob("*.json"))}
    if any(s["source_sha256"] != manifest["source_sha256"] for s in sources) or any(
            p.get("source_sha256", manifest["source_sha256"]) != manifest["source_sha256"] for p in pages.values()):
        raise ValueError("Step sources do not match the manifest")
    state_path = pilot / "reviews" / "state.json"
    state = read_json(state_path) if state_path.exists() else {}
    curation_path = pilot / "curation.json"
    curation = read_json(curation_path) if curation_path.exists() else {}
    notes = {i["number"]: i.get("issues", []) for i in curation.get("items", [])} if curation.get("source_sha256") == manifest["source_sha256"] else {}
    records = []
    for source in sources:
        saved = state.get("reviews", {}).get(source["question_id"], {})
        corrections = saved.get("fields", {}).get("formula_corrections", []) if saved.get("base_generation") == generation else []
        record = propose_steps(source, pages, corrections)
        record["candidate_generation"] = generation
        record["review_document_revision"] = state.get("document_revision", 0)
        record["source_review_notes"] = notes.get(source["source_number"], [])
        validate_grounding(record, source, pages)
        records.append(record)
    validator = Draft202012Validator(read_json(Path(__file__).parents[1] / "schemas" / "solution-step-proposals.v1.schema.json"))
    for record in records:
        validator.validate(record)
    report = {"schema_version": "step-segmentation-report/v1", "algorithm": VERSION,
              "source_sha256": manifest["source_sha256"], "candidate_generation": generation,
              "question_count": len(records), "legacy_group_count": sum(r["legacy_group_count"] for r in records),
              "proposed_step_count": sum(len(r["steps"]) for r in records),
              "kind_counts": dict(Counter(s["kind_candidate"] for r in records for s in r["steps"])),
              "flagged_question_count": sum(bool(r["review_flags"]) for r in records),
              "long_step_count": sum("LONG_STEP_REQUIRES_SPLIT_REVIEW" in s["review_flags"] for r in records for s in r["steps"]),
              "grounding_check": "PASS", "model_inference_runs": 0,
              "processing_seconds": round(time.perf_counter() - started, 3),
              "academic_approved_count": 0, "grading_ready_count": 0, "publishable_count": 0}
    directory = pilot / "steps"
    write_jsonl(directory / "questions.steps.jsonl", records)
    write_json(directory / "questions.steps.pretty.json", records)
    write_json(directory / "report.json", report)
    payload = json.dumps({"records": records, "report": report,
        "page_sizes": {str(n): [p["width"], p["height"]] for n, p in pages.items()}}, ensure_ascii=False).replace("<", "\\u003c")
    template = Path(__file__).with_name("steps_review.html").read_text(encoding="utf-8")
    (pilot / "steps.html").write_text(template.replace("__PAYLOAD__", payload), encoding="utf-8")
    from .review import build_review
    report_path = pilot / "enrichment-report.json"
    build_review(sources, read_json(report_path if report_path.exists() else pilot / "report.json"), pilot)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.pilot), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
