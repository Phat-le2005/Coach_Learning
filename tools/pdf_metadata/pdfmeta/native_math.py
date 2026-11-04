"""Recover simple, single-baseline math from PDF glyph geometry, without OCR.

Superscripts are inferred only from both smaller font size and raised baseline.
Stacked fractions, subscripts and unknown font mappings remain unsupported.
"""
from __future__ import annotations

import re
from statistics import median

from .safe_math import UnsupportedMath, assignment
from .text_cleanup import normalize_block


VERSION = "native-baseline-math/v1"
LHS = re.compile(r"(?<![A-Za-z])[A-Za-z]\s*[′'’]{0,2}\s*(?:\(\s*[A-Za-zν]\s*\))?\s*=")
VIETNAMESE = "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ"
# A prose word must not consume adjacent math such as +1000(nghìn đồng).
PROSE_WORD = re.compile(rf"[A-Za-z{VIETNAMESE}]*[{VIETNAMESE}][A-Za-z{VIETNAMESE}]*", re.I)
SUPER = str.maketrans({"²": "^{2}", "³": "^{3}"})


def glyph_positions(block):
    text, quality = normalize_block(block)
    if quality["unresolved_glyph_count"] or quality["assembly_glyph_count"]:
        raise UnsupportedMath("NATIVE_UNKNOWN_FONT_OR_ASSEMBLY")
    positions, cursor = [], 0
    for index, glyph in enumerate(block.get("glyphs", [])):
        if len(glyph.get("text", "")) != 1 or "bbox" not in glyph or "size" not in glyph:
            raise UnsupportedMath("NATIVE_GLYPH_GEOMETRY_MISSING")
        char = normalize_block({"text_raw": glyph["text"], "glyphs": [glyph]})[0]
        found = text.find(char, cursor)
        if found < 0 or len(char) != 1:
            raise UnsupportedMath("NATIVE_GLYPH_ALIGNMENT_AMBIGUOUS")
        positions.append({"offset": found, "glyph_index": index, **glyph})
        cursor = found + 1
    if not positions:
        raise UnsupportedMath("NATIVE_GLYPH_GEOMETRY_MISSING")
    return text, positions


def recover_slice(block, start, end, vectors=()):
    text, positions = glyph_positions(block)
    local = [g for g in positions if start <= g["offset"] < end]
    if not local or not 0 <= start < end <= len(text):
        raise UnsupportedMath("NATIVE_INVALID_TEXT_SLICE")
    baseline_size = median(g["size"] for g in local)
    if baseline_size <= 0:
        raise UnsupportedMath("NATIVE_INVALID_FONT_SIZE")
    normal = [g for g in local if g["size"] >= baseline_size * .82]
    bottom = median(g["bbox"][3] for g in normal)
    if max(g["bbox"][3] for g in normal) - min(g["bbox"][3] for g in normal) > baseline_size * .4:
        raise UnsupportedMath("NATIVE_MULTIPLE_BASELINES")
    box = [min(g["bbox"][0] for g in local), min(g["bbox"][1] for g in local),
           max(g["bbox"][2] for g in local), max(g["bbox"][3] for g in local)]
    for vector in vectors:
        b = vector["bbox"]
        if (vector["kind"] == "line" and b[2]-b[0] > 5 and b[3]-b[1] < 1
                and max(box[0], b[0]) < min(box[2]+2*baseline_size, b[2])
                and box[1]-2 < b[1] < box[3]+8):
            raise UnsupportedMath("NATIVE_FRACTION_BAR_REQUIRES_LAYOUT")
    raised = []
    for glyph in local:
        if glyph["size"] < baseline_size * .82:
            if bottom - glyph["bbox"][3] >= baseline_size * .23 and glyph["text"] in "0123456789+-":
                raised.append(glyph)
            else:
                raise UnsupportedMath("NATIVE_SUBSCRIPT_OR_AMBIGUOUS_SMALL_GLYPH")
    insertions, evidence = {}, []
    for glyph in raised:
        pos = glyph["offset"]
        # This bounded recognizer only reconstructs one/two-digit integer powers.
        if pos-1 in insertions and insertions[pos-1]["end"] == pos:
            previous = insertions.pop(pos-1)
            insertions[pos] = {**previous, "end": pos+1, "power": previous["power"]+glyph["text"]}
        else:
            previous = text[start:pos].rstrip()
            if not previous or not re.search(r"[A-Za-zν0-9)]$", previous):
                raise UnsupportedMath("NATIVE_SUPERSCRIPT_BASE_AMBIGUOUS")
            insertions[pos] = {"start": pos, "end": pos+1, "power": glyph["text"]}
        evidence.append({"glyph_index": glyph["glyph_index"], "bbox": glyph["bbox"],
                         "size": glyph["size"], "baseline_size": baseline_size, "baseline_bottom": bottom})
    # MathType may draw the radical entirely as vectors, absent from text.
    wrappers=[]
    for vector in vectors:
        roof=vector['bbox']
        if vector['kind']!='line' or roof[3]-roof[1]>.35 or roof[2]-roof[0]<baseline_size*.65:continue
        if not box[1]-baseline_size*.8<=roof[1]<=bottom-baseline_size*.65:continue
        legs=[v['bbox'] for v in vectors if v['kind']=='line'
              and abs(v['bbox'][2]-roof[0])<1 and abs(v['bbox'][1]-roof[1])<1
              and v['bbox'][3]-v['bbox'][1]>baseline_size*.65 and 1<v['bbox'][2]-v['bbox'][0]<baseline_size*.5]
        if not legs:continue
        operands=[g for g in local if roof[0]-1<=g['bbox'][0] and g['bbox'][2]<=roof[2]+1]
        if operands:
            wrappers.append((min(g['offset'] for g in operands),max(g['offset'] for g in operands)+1))
    prefixes={};suffixes={}
    for lo,hi in wrappers:
        prefixes[lo]=prefixes.get(lo,'')+r'\sqrt{';suffixes[hi]=suffixes.get(hi,'')+'}'
    replacements={e['start']:e for e in insertions.values()}
    pieces=[];index=start
    while index<end:
        pieces.append(suffixes.get(index,''));pieces.append(prefixes.get(index,''))
        if index in replacements:
            edit=replacements[index];pieces.append('^{'+edit['power']+'}');index=edit['end']
        else:pieces.append(text[index]);index+=1
    pieces.append(suffixes.get(end,''));result=''.join(pieces)
    return result.translate(SUPER), box, evidence


def candidates_for_step(step, pages):
    candidates, rejected = [], []
    # Root equations are not derivative formulas; table headers aren't functions.
    if step["kind_candidate"] not in {"MODEL_SETUP", "DERIVATIVE_CALCULATION", "UNCLASSIFIED"}:
        return candidates, rejected
    for section in step.get("text_slices", []):
        page = pages[section["page_number"]]
        block = next(b for b in page["blocks"] if b["block_id"] == section["block_id"])
        normalized = normalize_block(block)[0]
        lo, hi = section["normalized_start"], section["normalized_end"]
        part = normalized[lo:hi]
        matches = list(LHS.finditer(part))
        if not matches:
            continue
        # A second assignment can be an equality chain or another reasoning step.
        # Only the first function definition is considered; parser checks chains.
        match = matches[0]
        stop = re.search(r"[⇔⇒;<>≤≥]|\s+(?:với|do|nên|trong|và|cho|khi)\b", part[match.end():], re.I)
        end = match.end() + stop.start() if stop else len(part)
        prose = PROSE_WORD.search(part, match.end(), end)
        if prose:
            end = prose.start()
            # Drop the opening unit delimiter, preserving the numeric term before it.
            prefix=part[match.start():end].rstrip()
            if prefix.endswith('('):end=match.start()+len(prefix)-1
        # A comma before a trailing domain is not part of the polynomial.
        end_part = part[match.start():end].rstrip(" ,.;")
        end = match.start() + len(end_part)
        try:
            latex, bbox, powers = recover_slice(block, lo+match.start(), lo+end, page.get("vectors", []))
            expression = assignment(latex)
            if not expression["chain_consistent"]:
                raise UnsupportedMath("NATIVE_EQUALITY_CHAIN_INCONSISTENT")
        except (UnsupportedMath, ValueError, TypeError, NotImplementedError) as error:
            rejected.append({"block_id": block["block_id"], "page_number": page["page_number"], "reason": str(error)})
            continue
        candidates.append({"block_id": block["block_id"]+":native-geometry", "source_block_id": block["block_id"],
            "parser_id": VERSION, "page_number": page["page_number"], "bbox": bbox,
            "latex": latex, "status": "NATIVE_GEOMETRY_CANDIDATE_NOT_VERIFIED", "superscript_evidence": powers})
    return candidates, rejected
