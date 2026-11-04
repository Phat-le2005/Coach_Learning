import json
from copy import deepcopy
from pathlib import Path

import pytest

from pdfmeta.latex_stage import normalize_formula
from pdfmeta.safe_math import UnsupportedMath,assignment,equivalent
from pdfmeta.source_layout import resolve,text_candidate
from pdfmeta.document_pipeline import apply_source_guards


FIXTURES={r['case_id']:r for r in json.loads((Path(__file__).parent/'fixtures/source-layout-v1.json').read_text(encoding='utf-8'))}


@pytest.mark.parametrize('case_id,expected',[
    ('P10',r'C(x)=0.01x^2+20x+1000'),
    ('P17',r'y=sqrt(x^2-2x)'),
    ('P06',r"E'(v)=600cv^2*(v-9)/(v-6)^2")])
def test_source_replay_recovers_terms_and_vector_radical_without_corrupting_fraction(case_id,expected):
    item=FIXTURES[case_id];before=deepcopy(item)
    value,proof=resolve(item['page'],item['candidate'])
    assert equivalent(assignment(value),assignment(expected))
    assert proof['original_latex']==item['candidate']['latex']
    assert item==before
    assert normalize_formula(value)


@pytest.mark.parametrize('case_id,reason',[
    ('P11','SOURCE_OVERLINE_MISSING_FROM_TEXT'),
    ('P15','SOURCE_SUBSCRIPT_GLYPH_MISSING_FROM_TEXT'),
    ('P21','SOURCE_ABSOLUTE_BARS_MISSING_FROM_TEXT'),
    ('P22','SOURCE_ABSOLUTE_BARS_MISSING_FROM_TEXT')])
def test_parseable_but_source_incomplete_formulas_are_not_accepted(case_id,reason):
    item=FIXTURES[case_id]
    with pytest.raises(UnsupportedMath,match=reason):resolve(item['page'],item['candidate'])


def test_plain_text_cannot_bypass_the_same_source_absolute_value_guard():
    page=FIXTURES['P22']['page']
    with pytest.raises(UnsupportedMath,match='ABSOLUTE_BARS'):
        text_candidate('y = f x',[{'page_number':page['page_number']}],{page['page_number']:page})


def test_radical_roof_without_a_root_leg_is_deferred_instead_of_inventing_a_root():
    item=deepcopy(FIXTURES['P17'])
    item['page']['vectors']=[v for v in item['page']['vectors'] if v['kind']=='line' and v['bbox'][3]-v['bbox'][1]<.35]
    with pytest.raises(UnsupportedMath,match='TOP_BAR'):resolve(item['page'],item['candidate'])


def test_numeric_unit_suffix_cannot_be_interpreted_as_an_arithmetic_factor():
    with pytest.raises(UnsupportedMath,match='UNIT_SUFFIX'):normalize_formula('t=0(s)')


def test_qwen_cannot_bypass_a_source_layout_warning_by_reformatting_the_same_text():
    original={'question_id':'q','text_id':'stem','raw_text':'y = f x','origin':'TEXT',
              'status':'SOURCE_LAYOUT_UNRESOLVED','reason':'SOURCE_ABSOLUTE_BARS_MISSING_FROM_TEXT'}
    proposal={**original,'origin':'QWEN_TEXT_PROPOSAL','status':'NORMALIZED','latex':r'y=f\cdot x','reason':None}
    rows,count=apply_source_guards([original,proposal])
    assert count==1 and rows[1]['status']=='MODEL_PROPOSAL_NEEDS_SOURCE'
    assert rows[1]['reason']==original['reason'] and proposal['status']=='NORMALIZED'
