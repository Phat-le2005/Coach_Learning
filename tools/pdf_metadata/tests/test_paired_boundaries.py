from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

from pdfmeta.assemble import assemble
from pdfmeta.paired.boundaries import detach
from pdfmeta.paired.collection import collect
from pdfmeta.paired.probability import endpoint, event_guard, native_events
from pdfmeta.paired.viewer import render
from pdfmeta.storage import read_json, write_json
from test_paired_dataset import page, payload


def test_following_section_is_detached_with_every_original_block_preserved():
    pages=[page(1,['Câu 1. Đề.', 'Lời giải', 'Giải thứ nhất.', 'DẠNG 2. Bài kế tiếp.', 'Phương pháp mới.'])]
    original,orphans=assemble(pages,'a'*64);before=deepcopy(original)
    fixed,context,audit=detach(original,pages,orphans)
    assert original==before
    assert fixed[0]['question_id']==original[0]['question_id']
    assert fixed[0]['solution']['text_raw']=='Giải thứ nhất.\n'
    assert [b['text_raw'] for b in context]==['DẠNG 2. Bài kế tiếp.','Phương pháp mới.']
    assert audit[0]['original_solution']==original[0]['solution']
    assert {b for s in original[0]['solution']['source_spans'] for b in s['block_ids']}==(
        {b for s in fixed[0]['solution']['source_spans'] for b in s['block_ids']}|{b['block_id'] for b in context})


def test_normal_solution_wording_is_not_a_section_boundary():
    pages=[page(1,['Câu 1. Đề.', 'Lời giải', 'Bài toán này dùng xác suất.', 'Dạng của biểu thức cần tìm là 2.'])]
    original,orphans=assemble(pages,'a'*64)
    fixed,_,audit=detach(original,pages,orphans)
    assert not audit and fixed==original


def test_chapter_title_before_lesson_label_is_not_left_in_previous_solution():
    first=page(1,['Câu 1. Đề.', 'Lời giải', 'Kết luận của bài trước.'])
    second=page(2,['CHƯƠNG MỚI', 'BÀI: CÔNG THỨC MỚI', 'Lý thuyết.'])
    second['blocks'][0]['glyphs']=[{'size':28}]
    items,orphans=assemble([first,second],'a'*64)
    fixed,context,audit=detach(items,[first,second],orphans)
    assert fixed[0]['solution']['text_raw']=='Kết luận của bài trước.\n'
    assert len(context)==3 and audit[0]['page_number']==2


def test_standalone_giai_label_is_a_real_solution_boundary():
    items,_=assemble([page(1,['Câu 1. Đề.', 'Giải', 'Nội dung giải.'])],'a'*64)
    assert items[0]['solution']['text_raw']=='Nội dung giải.\n'


def test_separate_collection_physically_excludes_unpaired_questions_and_images(tmp_path):
    data=payload(tmp_path);job=tmp_path/'job';job.mkdir()
    native=job/'native/pages';native.mkdir(parents=True)
    write_json(native/'page-001.json',{**page(1,[]),'image_path':'pages/page-001.png'})
    Image.new('RGB',(600,800),'white').save(native/'page-001.png')
    html=tmp_path/'source.html';render(html,data)
    write_json(job/'paired.json',{'single_file_html':str(html),'structural_errors':[]})
    result=collect(job,tmp_path/'filtered')
    filtered=read_json(Path(result['metadata_json']))
    assert len(filtered['questions'])==1 and not filtered['unpaired_questions']
    assert filtered['questions'][0]['collection_number']==1
    assert result['excluded_unpaired_occurrences']==1
    assert 'Câu ở mục khác' not in Path(result['standalone_html']).read_text(encoding='utf-8')
    assert filtered['questions'][0]['publishable'] is False


def test_source_overline_and_vertical_conditional_bar_are_guarded():
    coords=[('P',[0,10,7,22]),('(',[9,8,13,23]),('A',[15,10,22,22]),('B',[29,10,36,22]),(')',[38,8,42,23])]
    p=page(1,[]);p['blocks']=[{'block_id':'b1','glyphs':[{'text':t,'bbox':b,'size':12,'font':'Times'} for t,b in coords]}]
    p['vectors']=[{'kind':'line','bbox':[29,7,36,7]},{'kind':'line','bbox':[25,8,25,23]}]
    atoms,issues=native_events(p,[-1,0,50,30])
    assert not issues and [a['canonical'] for a in atoms]==['P(A|!B)']
    assert event_guard(r'P\left(A\mid\overline{B}\right)',atoms,issues)=='EVENT_SYMBOLS_AGREE_NOT_SOURCE_APPROVAL'
    assert event_guard('P(A|B)',atoms,issues)=='SOURCE_EVENT_SYMBOL_CONFLICT'


@pytest.mark.parametrize('latex,expected',[(r'P(A)=\frac{3}{10}','3/10'),('P(B)=0,8','4/5'),(r'P(A)\approx53\%','53/100')])
def test_last_endpoint_is_typed_without_claiming_complete_answer(latex,expected):
    result=endpoint(latex)
    assert result['canonical_value']==expected
    assert result['scope']=='LAST_NUMERIC_ENDPOINT_ONLY_NOT_COMPLETE_MULTIPART_ANSWER'


@pytest.mark.parametrize('latex',['P(A)=x','P(A)=1e999999','P(A)=__import__(x)'])
def test_unknown_or_unsafe_endpoints_are_not_accepted(latex):
    with pytest.raises(ValueError):endpoint(latex)
