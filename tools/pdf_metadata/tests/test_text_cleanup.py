from pdfmeta.text_cleanup import clean_steps, is_suspicious, normalize_block


def test_symbol_encoding_is_decoded_using_font_evidence():
    text = "G\uf028x\uf029\uf03d1\uf02dx \uf0db x\uf0ce A"
    glyphs = [{"text": c, "font": "ABCDEF+SymbolMT"} for c in text]
    result, quality = normalize_block({"text_raw": text, "glyphs": glyphs})
    assert result == "G(x)=1−x ⇔ x∈ A"
    assert quality["mapped_glyph_count"] == 6
    assert not any(is_suspicious(c) for c in result)


def test_same_code_in_another_math_font_is_not_guessed_as_prime():
    block = {"text_raw": "m\uf0a2", "glyphs": [{"text": "\uf0a2", "font": "ABC+MT-Extra"}]}
    result, quality = normalize_block(block)
    assert "U+F0A2" in result and "′" not in result
    assert quality["unresolved_glyph_count"] == 1


def test_adobe_bracket_pieces_use_assigned_unicode_not_private_use():
    block = {"text_raw": "\uf0ec\uf0ed\uf0ee\uf0ef", "glyphs": [
        {"text": c, "font": "SymbolMT"} for c in "\uf0ec\uf0ed\uf0ee\uf0ef"]}
    result, quality = normalize_block(block)
    assert result == "⎧⎨⎩⎪"
    assert quality["assembly_glyph_count"] == 4


def test_step_keeps_raw_reference_and_explicit_math_layout_warning():
    source = {"question_id": "q1", "reference_steps": [{"step_id": "s1", "kind_candidate": "UNCLASSIFIED",
              "text_raw": "x\uf03d2", "source_spans": [{"page_number": 1, "bbox": [0, 0, 10, 10], "block_ids": ["b1"]}]}],
              "ocr_evidence": []}
    pages = {1: {"blocks": [{"block_id": "b1", "text_raw": "x\uf03d2", "glyphs": [{"text": "\uf03d", "font": "SymbolMT"}]}]}}
    step = clean_steps(source, pages, [])[0]
    assert step["text_candidate"] == "x=2"
    assert "text_raw" not in step
    assert step["raw_reference"]["step_id"] == "s1"
    assert "MATHEMATICAL_LAYOUT_NOT_RECONSTRUCTED" in step["normalization"]["quality_flags"]
    assert step["math_expression"] is None
