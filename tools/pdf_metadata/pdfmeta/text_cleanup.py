"""Font-aware display normalization; it does not reconstruct mathematical layout."""
from __future__ import annotations

from collections import Counter, defaultdict
import re

from ._symbol_encoding import _symbol_encoding


SYMBOL_FONTS = {"symbol", "symbolmt", "symbolmt,italic", "euclidsymbol"}
# Adobe's original table predates the Unicode bracket assembly characters.
# These substitutions retain individual glyph pieces, not an inferred equation.
ASSEMBLY = {
    0xF8EB: "⎛", 0xF8EC: "⎜", 0xF8ED: "⎝", 0xF8F6: "⎞", 0xF8F7: "⎟", 0xF8F8: "⎠",
    0xF8EE: "⎡", 0xF8EF: "⎢", 0xF8F0: "⎣", 0xF8F9: "⎤", 0xF8FA: "⎥", 0xF8FB: "⎦",
    0xF8F1: "⎧", 0xF8F2: "⎨", 0xF8F3: "⎩", 0xF8F4: "⎪",
    0xF8FC: "⎫", 0xF8FD: "⎬", 0xF8FE: "⎭", 0xF8F5: "⎮",
}


def is_suspicious(char: str) -> bool:
    value = ord(char)
    return (0xE000 <= value <= 0xF8FF or 0xF0000 <= value <= 0xFFFFD
            or 0x100000 <= value <= 0x10FFFD or char == "\ufffd")


def normalize_block(block: dict) -> tuple[str, dict]:
    fonts = defaultdict(set)
    for glyph in block.get("glyphs", []):
        if len(glyph["text"]) == 1:
            fonts[glyph["text"]].add(glyph["font"].split("+")[-1].casefold())
    mapped, unresolved, pieces = Counter(), Counter(), 0
    result = []
    for char in block["text_raw"]:
        if not is_suspicious(char):
            result.append(char)
            continue
        replacement = None
        known_fonts = fonts.get(char, set())
        if 0xF020 <= ord(char) <= 0xF0FE and known_fonts and known_fonts.issubset(SYMBOL_FONTS):
            replacement = _symbol_encoding[ord(char) - 0xF000]
            if ord(replacement) in ASSEMBLY:
                replacement = ASSEMBLY[ord(replacement)]
                pieces += 1
            if is_suspicious(replacement) or ord(replacement) < 32:
                replacement = None
        if replacement is None:
            unresolved[f"U+{ord(char):04X}"] += 1
            result.append(f"[chưa chuẩn hóa U+{ord(char):04X}]")
        else:
            mapped[f"U+{ord(char):04X}"] += 1
            result.append(replacement)
    return "".join(result), {"mapped_glyph_count": sum(mapped.values()), "unresolved_glyph_count": sum(unresolved.values()),
                             "unresolved_codes": dict(unresolved), "assembly_glyph_count": pieces}


def overlap(a: list, b: list) -> bool:
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    smaller = min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1]))
    return intersection / max(smaller, 0.001) >= 0.35


def clean_steps(source: dict, pages: dict[int, dict], corrections: list[dict]) -> list[dict]:
    correction_map = {c["block_id"]: c["latex"] for c in corrections}
    steps = []
    for raw in source["reference_steps"]:
        text, count, unmapped, fragments, seen = [], 0, 0, 0, set()
        missing = False
        for span in raw["source_spans"]:
            page = pages.get(span["page_number"])
            blocks = {b["block_id"]: b for b in page["blocks"]} if page else {}
            for identifier in span["block_ids"]:
                key = span["page_number"], identifier
                if key in seen:
                    continue
                seen.add(key)
                if identifier not in blocks:
                    missing = True
                    continue
                normalized, quality = normalize_block(blocks[identifier])
                text.append(normalized)
                count += quality["mapped_glyph_count"]
                unmapped += quality["unresolved_glyph_count"]
                fragments += quality["assembly_glyph_count"]
        if missing or not text:
            normalized, quality = normalize_block({"text_raw": raw["text_raw"]})
            text = [normalized]
            unmapped += quality["unresolved_glyph_count"]
        candidates = []
        for block in source.get("ocr_evidence", []):
            if block["block_type"] not in {"formula", "inline_formula", "display_formula"}:
                continue
            if not any(s["page_number"] == block["page_number"] and overlap(s["bbox"], block["bbox"])
                       for s in raw["source_spans"]):
                continue
            latex = correction_map.get(block["block_id"], block["text_raw"])
            if any(is_suspicious(c) for c in latex):
                continue
            rank = 0 if block["block_id"] in correction_map else 1 if block["parser_id"].endswith("-M") else 2
            candidates.append((rank, {"block_id": block["block_id"], "page_number": block["page_number"],
                                      "bbox": block["bbox"], "latex": latex, "parser_id": block["parser_id"],
                                      "status": "EDITORIAL_CANDIDATE" if rank == 0 else "OCR_CANDIDATE_NOT_VERIFIED"}))
        candidates.sort(key=lambda pair: pair[0])
        unique, roots = [], set()
        for _, candidate in candidates:
            root = re.sub(r"-(?:fallback|control)-M$", "", candidate["block_id"])
            if root not in roots:
                roots.add(root)
                unique.append(candidate)
        flags = ["MATHEMATICAL_LAYOUT_NOT_RECONSTRUCTED"]
        if unmapped:
            flags.append("UNRESOLVED_FONT_GLYPHS")
        if fragments:
            flags.append("ASSEMBLY_GLYPHS_REQUIRE_SOURCE_IMAGE")
        steps.append({"step_id": raw["step_id"], "kind_candidate": raw["kind_candidate"],
                      "text_candidate": "\n".join(text), "text_format": "NORMALIZED_NATIVE_TEXT_LOSSY",
                      "latex_candidates": unique[:3], "source_spans": raw["source_spans"],
                      "raw_reference": {"file": "../questions.enriched.candidates.jsonl", "question_id": source["question_id"], "step_id": raw["step_id"]},
                      "normalization": {"method": "font-aware-symbol/v1", "mapped_glyph_count": count,
                                        "unresolved_glyph_count": unmapped, "quality_flags": flags},
                      "status": "SOURCE_EXCERPT_NEEDS_REVIEW", "math_expression": None, "checker": None, "rubric_weight": None})
    return steps
