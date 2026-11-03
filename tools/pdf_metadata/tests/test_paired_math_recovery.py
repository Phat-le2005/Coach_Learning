import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pdfmeta.paired.math_recovery import FormulaReader, compare, regions, run


def source_fixture():
    return json.loads((Path(__file__).parent / 'fixtures/paired-integral-source-glyphs.json').read_text(encoding='utf-8'))


def test_original_font_geometry_retains_powers_and_the_constant_C_in_each_choice():
    fixture = source_fixture()
    found, rejected = regions(fixture['page'], fixture['question_span'])
    assert not rejected and len(found) == 5
    assert [r['label'] for r in found] == [None, 'A', 'B', 'C', 'D']
    assert compare(found[0]['native_candidate'], r'f(x)=x\left(4x^{2}+2\right)') == 'NATIVE_OCR_NOTATION_AGREEMENT'
    expected = [r'F(x)=x^{4}+2x^{2}+C', r'F(x)=4x^{4}+x^{2}+C', r'F(x)=x^{4}+x^{2}+C']
    for region, latex in zip(found[2:], expected):
        assert compare(region['native_candidate'], latex) == 'NATIVE_OCR_NOTATION_AGREEMENT'
    # The choices in the original source are alternatives. Do not fix the wrong
    # alternatives into the correct antiderivative during transcription.
    assert found[2]['native_candidate'] != found[4]['native_candidate']


def test_stacked_fraction_keeps_floating_glyphs_and_cannot_be_native_auto_approved():
    fixture = source_fixture()
    found, _ = regions(fixture['page'], fixture['question_span'])
    a = found[1]
    assert a['native_candidate'] is None
    assert a['native_rejection'] == 'MULTILINE_FORMULA_REQUIRES_IMAGE_READING'
    assert a['bbox'][1] < 360 and a['bbox'][3] > 390
    assert len({key.split(':')[0] for key in a['source_glyph_keys']}) == 3
    assert compare(None, r'F(x)=\frac{x^{2}}{2}(\frac{4x^{3}}{3}+2x)+C') == 'OCR_ONLY_REQUIRES_SOURCE_CHECK'


def test_region_ownership_excludes_adjacent_choices_and_next_question():
    fixture = source_fixture()
    question, _ = regions(fixture['page'], fixture['question_span'])
    solution, _ = regions(fixture['page'], fixture['solution_span'])
    assert len(solution) == 1 and solution[0]['bbox'][3] < 448
    seen = set()
    for region in question + solution:
        keys = set(region['source_glyph_keys'])
        assert not keys & seen
        seen |= keys
        assert region['bbox'][1] > 334 and region['bbox'][3] < 448


@pytest.mark.parametrize('native,ocr,result', [
    ('y=x^{2}', 'y=x^{3}', 'NATIVE_OCR_CONFLICT'),
    ('y=x^{2}', 'y=x2', 'UNSUPPORTED_COMPARISON_REQUIRES_SOURCE_CHECK'),
    ('y=x+x', 'y=2x', 'EQUIVALENT_SUPPORTED_EXPRESSION_REQUIRES_SOURCE_CHECK'),
    (None, '', 'EMPTY_MODEL_OUTPUT'),
    (None, 'x^{2}', 'OCR_ONLY_REQUIRES_SOURCE_CHECK'),
    (r'∫f(x)dx', r'\int f(x)\mathrm{d}x', 'NATIVE_OCR_NOTATION_AGREEMENT'),
])
def test_comparison_does_not_turn_model_output_or_algebra_into_source_approval(native, ocr, result):
    assert compare(native, ocr) == result


def test_ocr_cache_binds_image_model_weights_packages_and_adapter(tmp_path, monkeypatch):
    import pdfmeta.paired.math_recovery as module
    monkeypatch.setattr(module, 'inference_versions', lambda: {'test': '1'})
    weights = tmp_path / 'runtime/paddlex/official_models/PP-FormulaNet_plus-M/inference.pdiparams'
    weights.parent.mkdir(parents=True); weights.write_bytes(b'weights-v1')
    image = tmp_path / 'source.png'; image.write_bytes(b'original-source-image')
    class Model:
        def predict(self, path, batch_size):
            return [SimpleNamespace(json={'res': {'rec_formula': 'y=x^{2}'}})]
    reader = FormulaReader(tmp_path / 'runtime', tmp_path / 'output', 'PP-FormulaNet_plus-M')
    reader.instance = Model()
    assert reader.read(image) == reader.read(image) == 'y=x^{2}'
    assert (reader.calls, reader.hits) == (1, 1)
    image.write_bytes(b'changed-source-image')
    reader.read(image)
    assert reader.calls == 2
    weights.write_bytes(b'weights-v2')
    newer = FormulaReader(tmp_path / 'runtime', tmp_path / 'output', 'PP-FormulaNet_plus-M')
    newer.instance = Model(); newer.read(image)
    assert (newer.calls, newer.hits) == (1, 0)


def test_trial_refuses_missing_records_and_canonical_output_directory(tmp_path):
    source = tmp_path / 'metadata.jsonl'; source.write_text('{}\n', encoding='utf-8')
    with pytest.raises(ValueError, match='SEPARATE_OUTPUT_DIRECTORY'):
        run(source, tmp_path / 'plan.json', tmp_path, tmp_path / 'runtime', [1])
    with pytest.raises(ValueError, match='SELECT_1_TO_40_RECORDS'):
        run(source, tmp_path / 'plan.json', tmp_path / 'trial', tmp_path / 'runtime', [])
