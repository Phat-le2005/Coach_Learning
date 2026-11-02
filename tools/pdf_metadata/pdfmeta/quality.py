from __future__ import annotations

import re


def normalize_math_notation(text: str) -> str:
    """Normalize spelling variants only; never change a number or inequality."""
    text = text.replace("′", "'").replace("", "'")
    text = re.sub(r"\^\{\s*((?:\\prime|')+)\s*\}",
                  lambda m: "'" * (m.group(1).count("\\prime") + m.group(1).count("'")), text)
    text = re.sub(r"\^\s*\\prime\b", "'", text)
    return text.replace("{,}", ",").replace("{.}", ".").replace("\\,", " ")


def decimal_tokens(text: str) -> set[str]:
    cleaned = normalize_math_notation(text)
    # Whitespace/newlines between unrelated numbers must not join into a number.
    cleaned = re.sub(r"(?<=\d)\s*([,.])\s*(?=\d)", r"\1", cleaned)
    return {value.replace(",", ".") for value in re.findall(r"\d+[,.]\d+", cleaned)}


def compare_transcriptions(native: str, ocr: str) -> dict:
    """Conservative discrepancy detector, not a proof of OCR correctness."""
    flags = []
    native_decimals, ocr_decimals = decimal_tokens(native), decimal_tokens(ocr)
    if native_decimals and native_decimals != ocr_decimals:
        flags.append("OCR_DECIMAL_DISAGREEMENT")
    normalized_native = normalize_math_notation(native)
    normalized_ocr = normalize_math_notation(ocr)
    compact = re.sub(r"\s+", "", normalized_ocr)
    if re.search(r"\d+[,.]\d+[,.]\d+", compact):
        flags.append("OCR_MALFORMED_DECIMAL")
    if "\\nu" in ocr and re.search(r"\bv\b", native):
        flags.append("OCR_LATIN_V_GREEK_NU_DISAGREEMENT")
    if re.search(r"[A-Za-z]\s*'", normalized_native) and not re.search(r"[A-Za-z]\s*'", normalized_ocr):
        flags.append("OCR_DERIVATIVE_MARK_MISSING")
    native_relations = normalized_native.replace("", ">").replace("", "<")
    ocr_relations = compact.replace("\\geq", ">=").replace("\\leq", "<=").replace("\\nu", "v")
    for variable, operator, value in re.findall(r"([A-Za-z]'*)\s*([<>])\s*([+-]?\d+(?:[,.]\d+)?)", native_relations):
        if variable + operator + "=" + value in ocr_relations:
            flags.append("OCR_STRICT_BOUNDARY_CHANGED")
            break
    return {"flags": flags, "native_decimal_tokens": sorted(native_decimals),
            "ocr_decimal_tokens": sorted(ocr_decimals)}


def nearby_native_text(page: dict, bbox: list[float]) -> str:
    x0, y0, x1, y1 = bbox
    texts = []
    for block in page["blocks"]:
        if block.get("glyphs"):
            glyphs = [glyph for glyph in block["glyphs"]
                      if x0 <= (glyph["bbox"][0] + glyph["bbox"][2]) / 2 <= x1
                      and y0 <= (glyph["bbox"][1] + glyph["bbox"][3]) / 2 <= y1]
            if glyphs:
                texts.append("".join(glyph["text"] for glyph in sorted(glyphs, key=lambda g: g["bbox"][0])))
            continue
        bx0, by0, bx1, by1 = block["bbox"]
        overlap = max(0, min(x1, bx1) - max(x0, bx0)) * max(0, min(y1, by1) - max(y0, by0))
        if overlap / max((bx1 - bx0) * (by1 - by0), 0.001) >= 0.45:
            texts.append(block["text_raw"])
    return "\n".join(texts)
