from copy import deepcopy
import json
from pathlib import Path
import pytest

from pdfmeta.safe_math import UnsupportedMath
from pdfmeta.paired.transcription_v2.geometry import render
from pdfmeta.paired.transcription_v2.glyphs import canonical_char,canonical_page,glyph_lookup
from pdfmeta.paired.transcription_v2.tables import ink_edge,markdown
from pdfmeta.paired.transcription_v2.layout import prepare
from pdfmeta.paired.transcription_v2.vision import choose,validate_result
from pdfmeta.paired.transcription_v2.batch import raw_cache_index
from pdfmeta.storage import write_json,file_hash


def g(text,x,y=10,size=10,key=None):
    return {'text':text,'bbox':[x,y,x+5,y+size],'size':size,'font':'Times-Italic','key':key or text+str(x)+str(y)}


def test_source_crop_tolerates_pdfium_page_rounding_but_rejects_invalid_regions(tmp_path):
    import pdfplumber
    from test_one_pdf_workflow import small_pdf
    from pdfmeta.paired.transcription_v2.engine import source_crop
    pdf=tmp_path/'source.pdf';small_pdf(pdf,['Example 1. Source text.'])
    with pdfplumber.open(pdf) as doc:
        page=doc.pages[0]
        digest=source_crop(page,[0,100,page.width+.0004,200],tmp_path,'source.png',72)
        assert digest==file_hash(tmp_path/'source.png')
        with pytest.raises(ValueError,match='SOURCE_CROP_OUTSIDE_PAGE'):
            source_crop(page,[0,100,page.width+1,200],tmp_path,'invalid.png',72)


def test_superscript_and_subscript_are_distinct_source_nodes():
    text,ev=render([g('x',0),g('i',6,18,6),g('2',7,5,6)],[])
    assert text=='x_{i}^{2}'
    assert {e['kind'] for e in ev}=={'SUPERSCRIPT','SUBSCRIPT'}


def test_nested_fraction_preserves_all_digits():
    glyphs=[g('1',4,0,8),g('2',4,17,8),g('3',4,40,8)]
    vectors=[{'kind':'line','bbox':[0,13,15,13]}, {'kind':'line','bbox':[0,32,20,32]}]
    text,ev=render(glyphs,vectors)
    assert text==r'\frac{\frac{1}{2}}{3}'
    assert sum(e['kind']=='FRACTION' for e in ev)==2


def test_integral_limits_do_not_become_adjacent_baseline_digits():
    text,ev=render([g('∫',0,3,20),g('0',6,22,6),g('1',6,0,6),g('x',15),g('d',22),g('x',28)],[])
    assert text==r'\int_{0}^{1}xdx'


def test_deduplicated_combining_source_line_retains_image_flag():
    page={'blocks':[{'block_id':'b','text_raw':'í','glyphs':[g('i\u0301',0),g('i\u0301',0)]}]}
    out=canonical_page(page)
    assert out['blocks'][0]['alignment_error']
    assert set(glyph_lookup(out))=={'b:0','b:1'}


def test_multiline_system_is_not_flattened():
    with pytest.raises(UnsupportedMath):render([g('x',0),g('=',8),g('1',18),g('y',0,35),g('=',8,35),g('2',18,35)],[])


def test_unknown_source_and_orphan_script_reject():
    for glyphs in [[g('□',0)],[g('2',0,0,6),g('x',20)]]:
        with pytest.raises(UnsupportedMath):render(glyphs,[])


def test_overline_has_explicit_rule_and_glyph_ownership():
    text,ev=render([g('x',0)],[{'kind':'line','bbox':[0,8,5,8]}])
    assert text==r'\overline{x}'
    assert ev[0]['kind']=='OVERLINE' and ev[0]['glyph_keys']==['x010']


def test_adobe_direct_assembly_mapping_requires_actual_symbol_font():
    assert canonical_char({'text':'\uf8ee','font':'ABC+SymbolMT'})==('⎡','DIRECT_ADOBE_SYMBOL_ASSEMBLY')
    assert canonical_char({'text':'\uf8ee','font':'Times'})[1]=='UNMAPPED_SOURCE_GLYPH'


def test_canonicalization_keeps_original_glyph_keys_and_raw_text():
    page={'blocks':[{'block_id':'b','text_raw':'x \uf8ee','glyphs':[g('x',0),dict(g('\uf8ee',10),font='SymbolMT')]}]}
    before=deepcopy(page);out=canonical_page(page)
    assert page==before
    assert set(glyph_lookup(out))=={'b:0','b:1'}
    assert out['blocks'][0]['glyphs'][1]['original_text']=='\uf8ee'


def test_invisible_rectangles_cannot_create_table_cells():
    assert not ink_edge({'object_type':'rect','stroke':False,'non_stroking_color':(1,1,1),'width':70,'height':12})
    assert ink_edge({'object_type':'rect','stroke':False,'non_stroking_color':(0,0,0),'width':70,'height':.5})


def test_table_masks_fraction_seeds_and_keeps_cell_ownership():
    gs=[g('1',0,0),g('2',0,30)]
    page={'page_number':1,'blocks':[{'block_id':'b','text_raw':'12','glyphs':gs}],
          'vectors':[{'kind':'line','bbox':[0,20,10,20]}]}
    t={'bbox':[0,0,30,60],'source_glyph_keys':['b:0','b:1']}
    _,formulas,_,_,_=prepare(page,{'bbox':[0,0,50,80]},[t])
    assert formulas==[]
    assert page['blocks'][0]['text_raw']=='12'


def test_incomplete_table_uses_image_not_blank_cell():
    table={'rows':2,'columns':2,'asset_path':'assets/table.png','cells':[{'row':0,'column':0,'display_text':None}]}
    assert markdown(table).endswith('(assets/table.png)')


def test_unknown_table_header_can_use_its_own_source_image():
    table={'rows':1,'columns':1,'asset_path':'assets/full.png','cells':[{'row':0,'column':0,'display_text':None,'asset_path':'assets/cell.png'}]}
    assert '(assets/cell.png)' in markdown(table)


def test_empty_confident_vision_reading_is_rejected():
    assert not validate_result({'latex':'','uncertain':False,'note':''})
    assert validate_result({'latex':'','uncertain':True,'note':'unreadable'})
    assert not validate_result({'latex':'x','uncertain':'false','note':''})
    assert not validate_result({'latex':'x\ny','uncertain':False,'note':''})


def test_vision_diagnostic_sampling_has_an_explicit_region_boundary():
    common={'asset_path':'assets/a.png','asset_sha256':'hash','page_number':1,'crop_bbox':[0,0,10,10],'latex_candidate':'x'}
    q={'formula_candidates':[dict(common,formula_id='shown',display_latex='x'),dict(common,formula_id='held',display_latex=None)]}
    selected=choose(q)
    assert selected['region_id']=='held' and selected['kind']=='FORMULA'
    assert selected['bbox']==[0,0,10,10]


def test_tampered_ocr_cache_cannot_be_reused(tmp_path):
    p=tmp_path/'workers/one/ocr-cache/cache.json';write_json(p,{'identity':{'model':'local'},'latex':'x'})
    baseline={str(p.relative_to(tmp_path)):file_hash(p)}
    assert len(raw_cache_index(baseline,tmp_path))==1
    write_json(p,{'identity':{'model':'local'},'latex':'wrong'})
    with pytest.raises(ValueError,match='CACHE_CHANGED'):raw_cache_index(baseline,tmp_path)


def test_draft_contract_rejects_automatic_publication_or_grading_approval():
    from jsonschema import Draft202012Validator
    path=Path(__file__).parents[1]/'pdfmeta/paired/transcription_v2/record.schema.json'
    schema=json.loads(path.read_text(encoding='utf-8'));Draft202012Validator.check_schema(schema)
    for field,bad in [('publishable',True),('academic_review','APPROVED'),('grading_support','READY')]:
        sub={'type':'object','properties':{field:schema['properties'][field]}}
        assert list(Draft202012Validator(sub).iter_errors({field:bad}))
