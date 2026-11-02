from copy import deepcopy

from PIL import Image,ImageDraw,ImageFont
import pytest
import sympy as sp

from pdfmeta.fraction_layout import render,candidates_for_step
from pdfmeta.safe_math import UnsupportedMath,assignment
from pdfmeta.variation_table import boundary,arrow,geometry,structure,check,check_values


def glyph(char,x,y,*,size=10,key=None):
    return dict(text=char,bbox=[x,y,x+5,y+size],size=size,key=key or f'{char}:{x}:{y}')


def test_nested_fraction_tree_preserves_all_source_glyphs_and_bars():
    # x / (1 + 1/x), rather than a flattened x/1 + 1/x.
    glyphs=[glyph('x',20,10),glyph('1',4,40),glyph('+',11,40),glyph('1',25,34),glyph('x',25,51)]
    latex,evidence=render(glyphs,[[0,30,40,30],[23,48,32,48]])
    assert sp.cancel(assignment('y='+latex)['expression']-sp.Symbol('x')**2/(sp.Symbol('x')+1))==0
    assert len(evidence)==2
    consumed=set(evidence[0]['numerator_glyph_keys']+evidence[0]['denominator_glyph_keys'])
    assert consumed=={g['key'] for g in glyphs}


def test_fraction_does_not_discard_unowned_lower_baseline():
    glyphs=[glyph('x',12,0),glyph('1',12,20),glyph('+',35,20),glyph('x',45,40)]
    with pytest.raises(UnsupportedMath,match='UNCONSUMED_BASELINES'):
        render(glyphs,[[10,15,20,15]])


def test_fraction_requires_ink_on_both_sides_of_a_source_bar():
    with pytest.raises(UnsupportedMath):
        render([glyph('x',5,0),glyph('1',12,25)],[])
    latex,evidence=render([glyph('x',5,0)],[[0,15,20,15]])
    assert latex=='x' and evidence==[]


def test_unknown_function_call_cannot_become_implicit_multiplication():
    with pytest.raises(UnsupportedMath,match='UNDECLARED_FUNCTION'):
        assignment("y'=f(x)/(x-1)^2")
    assert assignment('y=x(x+1)')['expression']==sp.Symbol('x')*(sp.Symbol('x')+1)


def test_two_digit_superscript_is_one_power():
    expression,_=render([glyph('x',0,10),glyph('1',6,6,size=6),glyph('0',10,6,size=6)],[])
    assert expression=='x^{10}'


@pytest.mark.parametrize('text,result',[(r'+\infty','+inf'),(r'\infty','+inf'),('-∞','-inf'),('12','12'),(r'\mathbf{0}','0')])
def test_boundaries_keep_infinity_distinct_from_large_finite_numbers(text,result):
    assert boundary(text)==result


@pytest.mark.parametrize('text',[r'\phantom{0}',r'\hat{x}',r'\infty+1','1e99999999'])
def test_unreadable_boundary_is_not_replaced_by_expected_calculus_value(text):
    with pytest.raises(UnsupportedMath):
        boundary(text)


def variation_image():
    im=Image.new('L',(320,180),255);d=ImageDraw.Draw(im);font=ImageFont.load_default(size=18)
    d.line((0,42,319,42),fill=0,width=2);d.line((0,85,319,85),fill=0,width=2)
    d.line((55,0,55,179),fill=0,width=2)
    for xy,text in [((15,10),'x'),((10,53),"f'"),((15,125),'f'),((65,10),'0'),((175,10),'1'),((277,10),'99')]:
        d.text(xy,text,fill=0,font=font)
    d.line((110,65,128,65),fill=0,width=2);d.line((119,56,119,74),fill=0,width=2)
    d.text((175,53),'0',fill=0,font=font);d.line((232,65,250,65),fill=0,width=2)
    d.line((80,160,155,105),fill=0,width=2);d.polygon([(155,105),(144,108),(150,116)],fill=0)
    d.line((205,105,280,160),fill=0,width=2);d.polygon([(280,160),(268,157),(273,149)],fill=0)
    return im


def test_variation_extracts_arrows_signs_and_infinite_interval_without_filling_from_math():
    values=iter(['0','1',r'+\infty','x','f(x)',"f'(x)",'0'])
    table=structure(variation_image(),lambda _:next(values))
    assert [i['direction'] for i in table['intervals']]==['INCREASING','DECREASING']
    assert [i['source_sign'] for i in table['intervals']]==['+','-']
    assert table['intervals'][-1]['right']=='+inf'
    assert check(table,assignment("f'(x)=1-x"))['status']=='PASS'
    flipped=deepcopy(table);flipped['intervals'][0]['source_sign']='-'
    assert check(flipped,assignment("f'(x)=1-x"))['status']=='FAIL'
    assert table['publishable'] is False


def test_diagonal_without_arrowhead_is_not_a_variation_arrow():
    with pytest.raises(UnsupportedMath,match='ARROWHEAD'):
        arrow([(x,x//2) for x in range(40)])


def test_sign_checker_handles_infinity_but_refuses_a_hidden_root():
    from pdfmeta.sign_table import check as signs
    table=dict(axis='x',function_label='f',intervals=[dict(left='0',right='+inf',source_sign='+')],point_values=[])
    assert signs(table,assignment("f'(x)=x+1"))['status']=='PASS'
    assert signs(table,assignment("f'(x)=x-1000"))['reason']=='UNRECORDED_ROOT_OR_POLE_INSIDE_INTERVAL'


def test_outer_table_frame_does_not_become_a_header_glyph():
    image=variation_image();d=ImageDraw.Draw(image)
    d.rectangle((1,1,318,178),outline=0,width=1)
    values=iter(['0','1',r'+\infty','x','f(x)',"f'(x)",'0'])
    assert structure(image,lambda _:next(values))['boundaries'][1]['value']=='1'


def test_conflicting_valid_ocr_and_font_number_is_not_silently_resolved():
    values=iter(['0'])
    with pytest.raises(UnsupportedMath,match='OCR_FONT_BOUNDARY_CONFLICT'):
        structure(variation_image(),lambda _:next(values),boundary_reader=lambda _:dict(text='1'))


def test_font_matcher_reads_supported_boundary_symbols_and_retains_font_hashes():
    from pathlib import Path
    from pdfmeta.table_glyphs import BoundaryGlyphs
    fonts=[p for p in [Path(r'C:\Windows\Fonts\times.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf')] if p.exists()]
    if not fonts:
        pytest.skip('No local test font')
    matcher=BoundaryGlyphs(font_paths=[fonts[0]])
    font=ImageFont.truetype(str(fonts[0]),45)
    im=Image.new('L',(180,80),255);ImageDraw.Draw(im).text((10,10),'+∞',font=font,fill=0)
    record=matcher.read(im)
    assert record['text']=='+∞'
    assert len(record['font_files'][0]['sha256'])==64
    assert 'NOT_CALIBRATED' in record['status']


def test_variation_value_check_uses_source_value_without_replacing_a_wrong_one():
    table=dict(axis='I',function_label='P',function_values=[dict(at='12',value='72')])
    formula=assignment('P=12I-0,5I^2')
    assert check_values(table,formula)['status']=='PASS'
    table['function_values'][0]['value']='73'
    assert check_values(table,formula)['status']=='FAIL'
    assert table['function_values'][0]['value']=='73'


def test_later_transformed_base_is_used_before_an_unsubstituted_relation():
    from pdfmeta.math_audit import audit_question
    def step(n,kind,latex):
        return dict(step_id=str(n),kind_candidate=kind,title=kind,text_candidate='',source_spans=[],
                    latex_candidates=[dict(latex=latex,page_number=1,bbox=[0,n*20,100,n*20+12],block_id=str(n))])
    record=audit_question(dict(question_id='q',source_number=99,source_sha256='a'*64),dict(steps=[
        step(1,'MODEL_SETUP','E(v)=cv^3t'),step(2,'MODEL_SETUP','E(v)=300cv^3/(v-6)'),
        step(3,'DERIVATIVE_CALCULATION',"E'(v)=600cv^2(v-9)/(v-6)^2")]))
    assert [c['status'] for c in record['checks']]==['PASS']
    assert record['checks'][0]['base_step_number']==2


def test_view_supports_arrow_only_table_without_inventing_a_source_sign(tmp_path):
    from pdfmeta.layout_refinement import build_view
    table=dict(axis='I',function_label='P',row_label_latex='P',intervals=[dict(left='0',right='12',direction='INCREASING')],point_values=[])
    record=dict(source_number=1,status='STRUCTURED_CANDIDATE',page_number=1,asset_path='source.png',table=table,formula_checks=[])
    report=dict(math=dict(page_count=1,question_count=1,native_geometry_candidates=0,questions_with_supported_checks=0))
    build_view(tmp_path,report,[],[record])
    html=(tmp_path/'review.html').read_text(encoding='utf-8')
    assert 'Không ghi ở bảng' in html and '↗ Tăng' in html


def test_table_schema_accepts_generated_candidates_but_never_approved_content():
    import json
    from pathlib import Path
    from jsonschema import Draft202012Validator,ValidationError
    schema=json.loads((Path(__file__).parents[1]/'schemas/math-table-candidate.v1.schema.json').read_text())
    validator=Draft202012Validator(schema)
    values=iter(['0','1',r'+\infty','x','f(x)',"f'(x)",'0'])
    table=structure(variation_image(),lambda _:next(values))
    validator.validate(table)
    table['publishable']=True
    with pytest.raises(ValidationError):
        validator.validate(table)
