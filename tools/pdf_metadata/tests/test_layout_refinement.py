from copy import deepcopy

from PIL import Image, ImageDraw, ImageFont
import pytest

from pdfmeta.native_math import recover_slice, candidates_for_step
from pdfmeta.safe_math import UnsupportedMath, assignment
from pdfmeta.sign_table import analyze, structure, check, symbol, scalar, unstyle
from pdfmeta.step_segmentation import classify
from pdfmeta.math_audit import audit_question


def glyph_block(text="y=x2", raised=True):
    glyphs = []
    for i,char in enumerate(text):
        high = char == "2" and raised
        glyphs.append(dict(text=char,font="TimesNewRomanPSMT",size=6 if high else 10,
                           bbox=[i*6,2 if high else 4,i*6+5,8 if high else 14]))
    return dict(block_id="b",text_raw=text,glyphs=glyphs,bbox=[0,2,len(text)*6,14])


def test_superscript_requires_both_size_and_vertical_evidence():
    formula,_,evidence = recover_slice(glyph_block(),0,4)
    assert formula == "y=x^{2}" and len(evidence)==1
    assert recover_slice(glyph_block(raised=False),0,4)[0] == "y=x2"
    with pytest.raises(UnsupportedMath,match="LOST_SUPERSCRIPT"):
        assignment("y=x2")


def test_lower_small_glyph_and_adjacent_fraction_are_never_dropped():
    block = glyph_block()
    block['glyphs'][-1]['bbox'] = [18,10,23,16]
    with pytest.raises(UnsupportedMath,match="SUBSCRIPT_OR_AMBIGUOUS"):
        recover_slice(block,0,4)
    with pytest.raises(UnsupportedMath,match="FRACTION_BAR"):
        recover_slice(glyph_block(),0,4,[dict(kind="line",bbox=[25,10,42,10])])


def test_native_slices_do_not_copy_root_finding_into_derivative_formula():
    block = glyph_block()
    step = dict(kind_candidate="ROOT_FINDING",text_slices=[dict(page_number=1,block_id="b",normalized_start=0,normalized_end=4)])
    assert candidates_for_step(step,{1:dict(blocks=[block],vectors=[])}) == ([],[])


def test_domain_suffix_is_preserved_without_mistaking_decimal_comma():
    parsed = assignment(r"R'(x)=50(1-0,01x^2)/(0,01x^2+1)^2,0\leq x\leq20")
    assert parsed['conditions_raw'] == r"0\leq x\leq20"
    assert parsed['expression'].subs({'x':0}) == 50
    assert assignment("G(x)=0,025x^2(30-x),x>0")['conditions_raw'] == "x>0"


def test_style_wrappers_do_not_change_axis_or_number_content():
    assert unstyle(r"\pmb{x}")=='x'
    assert scalar(r"\mathbf{10}")=='10'
    with pytest.raises(UnsupportedMath):
        scalar(r"\phantom{10}")


@pytest.mark.parametrize("heading", ["Có bảng xét dấu:","Ta có bảng biến thiên:","Bảng biến thiên:"])
def test_table_headings_with_introductory_words_start_a_table_step(heading):
    assert classify(heading) == "SIGN_TABLE"


def simple_table():
    image = Image.new('L',(300,100),255)
    draw = ImageDraw.Draw(image)
    draw.line((0,50,299,50),fill=0,width=2)
    draw.line((50,0,50,99),fill=0,width=2)
    font = ImageFont.load_default(size=18)
    draw.text((15,12),'x',fill=0,font=font)
    draw.text((15,65),'R',fill=0,font=font)
    for x,text in [(65,'0'),(170,'10'),(260,'20')]:
        draw.text((x,12),text,fill=0,font=font)
    draw.line((110,75,130,75),fill=0,width=2)
    draw.line((120,65,120,85),fill=0,width=1)
    draw.text((175,65),'0',fill=0,font=font)
    draw.line((220,75,240,75),fill=0,width=2)
    return image


def test_raster_plus_includes_a_one_pixel_vertical_stroke():
    geometry = analyze(simple_table())
    assert [s['pixel_symbol'] for s in geometry['body']] == ['+','OTHER','-']
    points = [(x,10) for x in range(5,20)]+[(12,y) for y in range(2,19)]
    assert symbol(points) == '+'


def test_table_structure_and_rational_sign_check_do_not_rewrite_source():
    values = iter(['0','10','20','x',"R'(x)",'0'])
    table = structure(simple_table(),lambda _:next(values))
    assert [i['source_sign'] for i in table['intervals']] == ['+','-']
    formula = assignment("R'(x)=50(1-0,01x^2)/(0,01x^2+1)^2")
    result = check(table,formula)
    assert result['status'] == 'PASS' and len(result['findings']) == 3
    wrong = deepcopy(table);wrong['intervals'][0]['source_sign'] = '-'
    assert check(wrong,formula)['status'] == 'FAIL'
    assert table['intervals'][0]['source_sign'] == '+'
    assert table['publishable'] is False


def test_sign_check_refuses_unsplit_roots_and_preserves_canceled_poles():
    table=dict(axis='x',function_label='f',intervals=[dict(left='-1',right='1',source_sign='+')],point_values=[])
    assert check(table,assignment("f'(x)=x^2"))['reason'] == 'UNRECORDED_ROOT_OR_POLE_INSIDE_INTERVAL'
    assert check(table,assignment("f'(x)=x/x"))['reason'] == 'UNRECORDED_ROOT_OR_POLE_INSIDE_INTERVAL'


def test_unsupported_multiline_variation_table_is_rejected_before_ocr():
    image = simple_table();draw=ImageDraw.Draw(image);draw.line((0,90,299,90),fill=0,width=2)
    with pytest.raises(UnsupportedMath,match='ONLY_TWO_ROW'):
        structure(image,lambda _:pytest.fail('Complex table must not call OCR'))
