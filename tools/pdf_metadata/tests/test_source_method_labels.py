import pytest

from pdfmeta.method_labels import DEFAULT_TAXONOMY, load_taxonomy, chapter_code, label_record
from pdfmeta.source_method_labels import document_contexts, native_document_contexts, heading_rows, read_heading


@pytest.fixture(scope='module')
def taxonomy():return load_taxonomy(DEFAULT_TAXONOMY)


def question(n=1,page=1,text=None):
    return {'question_id':f'source:q{n}','collection_number':n,'chapter_title':'file',
            'source':{'sha256':'a'*64},'question':{'markdown':text or f'Câu {n}. Nội dung câu hỏi.',
            'source_spans':[{'page_number':page}]}}


def page(n,text,native=''):
    return {'page_number':n,'native_text_from_this_pdf':native,'markdown':text}


def test_unknown_subject_uses_its_own_printed_tree(taxonomy):
    rows=[question()]
    pages=[page(1,'CHƯƠNG VIII: CHỦ ĐỀ HOÀN TOÀN MỚI\nBÀI 3\nKIẾN THỨC RIÊNG CỦA TÀI LIỆU\nDẠNG 1: PHƯƠNG PHÁP RIÊNG\nCâu 1. Nội dung câu hỏi.')]
    contexts,catalog=document_contexts(rows,pages,taxonomy,chapter_code)
    method=label_record(rows[0],{},taxonomy,contexts[rows[0]['question_id']])
    assert method['chapter']['name']=='CHỦ ĐỀ HOÀN TOÀN MỚI'
    assert method['lesson']['name']=='KIẾN THỨC RIÊNG CỦA TÀI LIỆU'
    assert method['exercise_type']['name']=='PHƯƠNG PHÁP RIÊNG'
    assert method['chapter']['canonical_code'] is None
    assert method['lesson']['source_number']=='3'
    assert len(catalog['labels'])==3


def test_same_type_number_has_separate_identity_under_different_lessons(taxonomy):
    rows=[question(1),question(2)]
    text='CHƯƠNG 1: CHƯƠNG MỚI\nBÀI 1: BÀI THỨ NHẤT\nDẠNG 1: CÁCH GIẢI CHUNG\nCâu 1. Nội dung.\nBÀI 2: BÀI THỨ HAI\nDẠNG 1: CÁCH GIẢI CHUNG\nCâu 2. Nội dung.'
    ctx,_=document_contexts(rows,[page(1,text)],taxonomy,chapter_code)
    a,b=[ctx[r['question_id']] for r in rows]
    assert a['exercise_type']['code']!=b['exercise_type']['code']
    assert a['lesson']['source_number']=='1' and b['lesson']['source_number']=='2'


def test_later_heading_does_not_label_earlier_question(taxonomy):
    rows=[question(1),question(2)]
    ctx,_=document_contexts(rows,[page(1,'DẠNG 1: CÁCH THỨ NHẤT\nCâu 1. Đề một.\nDẠNG 2: CÁCH THỨ HAI\nCâu 2. Đề hai.')],taxonomy,chapter_code)
    assert ctx[rows[0]['question_id']]['exercise_type']['source_number']=='1'
    assert ctx[rows[1]['question_id']]['exercise_type']['source_number']=='2'


def test_running_chapter_header_preserves_lesson_but_page_gap_resets_it(taxonomy):
    rows=[question(1,1),question(2,2),question(3,4)]
    pages=[page(1,'CHƯƠNG 1: XÁC SUẤT CÓ ĐIỀU KIỆN\nBÀI 2: CÔNG THỨC BAYES\nDẠNG 1: DÙNG BẢNG\nCâu 1. Nội dung.'),
           page(2,'Câu 2. Nội dung.','CHƯƠNG 1: XÁC SUẤT CÓ ĐIỀU KIỆN'),
           page(4,'Câu 3. Nội dung.')]
    ctx,_=document_contexts(rows,pages,taxonomy,chapter_code)
    assert ctx[rows[1]['question_id']]['lesson']['name']=='CÔNG THỨC BAYES'
    assert ctx[rows[2]['question_id']]=={}


def test_numbered_exercise_is_not_a_lesson(taxonomy):
    rows=[question(text='Bài 1. Cho hai biến cố A và B.')]
    ctx,catalog=document_contexts(rows,[page(1,'Bài 1. Cho hai biến cố A và B.')],taxonomy,chapter_code)
    assert ctx[rows[0]['question_id']]=={} and catalog['labels']==[]


def test_source_topic_context_bai_is_a_lesson_and_overrides_rules(taxonomy):
    q=question(page=3,text='Câu 1. Tìm cực trị của hàm số.')
    q['topic_context']={'chapter':{'label':'BÀI: XÁC SUẤT CÓ ĐIỀU KIỆN','page_number':1},
                        'exercise_type':{'label':'DẠNG 9. SỬ DỤNG PHƯƠNG PHÁP MỚI','page_number':2}}
    ctx,_=document_contexts([q],[page(3,q['question']['markdown'])],taxonomy,chapter_code)
    m=label_record(q,{},taxonomy,ctx[q['question_id']])
    assert m['lesson']['name']=='XÁC SUẤT CÓ ĐIỀU KIỆN'
    assert m['exercise_type']['source_number']=='9'
    assert m['review_required']


def test_new_document_chapter_does_not_reuse_previous_subject_rule_labels(taxonomy):
    q=question(text='Câu 1. Tìm cực trị của hàm số.')
    ctx,_=document_contexts([q],[page(1,'CHƯƠNG 7: KIẾN THỨC MỚI\n'+q['question']['markdown'])],taxonomy,chapter_code)
    old={1:{'code':'DERIVATIVE_APPLICATIONS','evidence':{'page_number':1,'text':'Old header'}}}
    m=label_record(q,old,taxonomy,ctx[q['question_id']])
    assert m['chapter']['name']=='KIẾN THỨC MỚI'
    assert m['lesson'] is None and m['exercise_type'] is None and m['candidates']==[]


def test_source_only_mode_does_not_apply_semantic_rules(taxonomy):
    q=question(text='Câu 1. Tìm cực trị của hàm số.')
    old={1:{'code':'DERIVATIVE_APPLICATIONS','evidence':{'page_number':1,'text':'Header'}}}
    m=label_record(q,old,taxonomy,labels_from='source')
    assert m['chapter'] and m['lesson'] is None and m['exercise_type'] is None


def test_contents_page_does_not_assign_its_last_chapter_to_questions(taxonomy):
    q=question(page=2)
    pages=[page(1,'MỤC LỤC\nCHƯƠNG 1: CHỦ ĐỀ THỨ NHẤT\nCHƯƠNG 2: CHỦ ĐỀ THỨ HAI'),
           page(2,q['question']['markdown'])]
    ctx,catalog=document_contexts([q],pages,taxonomy,chapter_code)
    assert ctx[q['question_id']]=={} and catalog['labels']==[]


def test_native_book_chapter_switch_clears_previous_lesson(taxonomy):
    rows=[question(1,1),question(2,2)]
    pages=[page(1,'BÀI 1: TÍNH ĐƠN ĐIỆU\nDẠNG 1: DÙNG ĐỒ THỊ\nCâu 1. Nội dung.',
                'ỨNG DỤNG ĐẠO HÀM VÀ ĐỒ THỊ HÀM SỐ Câu hỏi kèm lời giải'),
           page(2,'Câu 2. Tính tích phân.','NGUYÊN HÀM, TÍCH PHÂN VÀ ỨNG DỤNG Câu hỏi kèm lời giải')]
    ctx,_=document_contexts(rows,pages,taxonomy,chapter_code)
    second=ctx[rows[1]['question_id']]
    assert second['chapter']['canonical_code']=='INTEGRALS'
    assert 'lesson' not in second and 'exercise_type' not in second


def test_compiled_book_source_reference_change_clears_finer_labels(taxonomy):
    rows=[question(1,1),question(2,2)]
    pages=[page(1,'BÀI 1: TÍNH ĐƠN ĐIỆU\nDẠNG 1: DÙNG ĐỒ THỊ\nCâu 1. Nội dung.',
                'ỨNG DỤNG ĐẠO HÀM VÀ ĐỒ THỊ HÀM SỐ\nCâu 001 | TL aaaaaaaa | Trang nguồn 1'),
           page(2,'Câu 2. Nội dung.','ỨNG DỤNG ĐẠO HÀM VÀ ĐỒ THỊ HÀM SỐ\nCâu 002 | TL bbbbbbbb | Trang nguồn 2')]
    ctx,_=document_contexts(rows,pages,taxonomy,chapter_code)
    assert ctx[rows[0]['question_id']]['exercise_type']
    assert 'exercise_type' not in ctx[rows[1]['question_id']]


def test_native_title_type_is_not_mistaken_for_running_chapter_header(taxonomy):
    q=question(page=2)
    pages=[page(1,'CHƯƠNG 1: NGUYÊN HÀM VÀ TÍCH PHÂN\nBÀI 1: TÍCH PHÂN'),
           page(2,q['question']['markdown'],'TÍNH TÍCH PHÂN BẰNG PHƯƠNG PHÁP ĐỔI BIẾN')]
    ctx,_=document_contexts([q],pages,taxonomy,chapter_code)
    assert ctx[q['question_id']]['exercise_type']['name']=='TÍNH TÍCH PHÂN BẰNG PHƯƠNG PHÁP ĐỔI BIẾN'


def test_custom_taxonomy_with_different_lessons_does_not_force_builtin_types(taxonomy):
    custom=dict(taxonomy,topics={},problem_types={})
    q=question(text='Câu 1. Tìm cực trị của hàm số.')
    source={1:{'code':'DERIVATIVE_APPLICATIONS','evidence':{'page_number':1,'text':'Header'}}}
    m=label_record(q,source,custom)
    assert m['chapter'] and not m['lesson'] and not m['exercise_type']
    assert 'FALLBACK_RULE_NOT_IN_SELECTED_TAXONOMY' in m['flags']


def test_native_positions_stop_at_questions_and_mark_heading_records(tmp_path,monkeypatch,taxonomy):
    import pypdfium2 as pdfium
    import pdfmeta.pdf_text_layout as layout
    path=tmp_path/'native.pdf'
    with pdfium.PdfDocument.new() as doc:
        doc.new_page(600,800).close();doc.save(path)
    def b(text,top):
        return {'text_raw':text,'block_id':str(top),'bbox':[20,top,550,top+12],'is_margin':False}
    profile={1:{'blocks':[b('CHƯƠNG 1: CHỦ ĐỀ MỚI',5),b('BÀI 1,2: KIẾN THỨC CHUNG',25),
                         b('DẠNG 1: CÁCH THỨ NHẤT',80),b('PHẦN IV. Câu tự luận. Mỗi câu trình bày cách giải.',160)]}}
    monkeypatch.setattr(layout,'inspect_document',lambda doc:profile)
    rows=[question(1,text='BÀI 1,2: KIẾN THỨC CHUNG'),question(2),question(3),question(4)]
    for q,top in zip(rows,[25,45,120,200]):q['question']['source_spans'][0]['bbox']=[20,top,550,top+15]
    ctx,catalog,kinds=native_document_contexts(rows,path,taxonomy,chapter_code)
    assert kinds=={rows[0]['question_id']:'SOURCE_HEADING_NOT_EXERCISE'}
    assert 'exercise_type' not in ctx[rows[1]['question_id']]
    assert ctx[rows[2]['question_id']]['exercise_type']['source_number']=='1'
    assert 'exercise_type' not in ctx[rows[3]['question_id']]
    assert ctx[rows[3]['question_id']]['lesson']['source_number']=='1,2'


def test_fragmented_pdf_heading_runs_join_without_corrupting_vietnamese():
    parts=[]
    for i,(text,x0,x1,top) in enumerate([('D',40,49,46),('ẠNG',49.3,77,45.8),('5',81,88,46),
                                        ('. CÁC BÀI TOÁN THỰC TẾ',89,320,43.2)]):
        parts.append({'block_id':str(i),'text_raw':text,'bbox':[x0,top,x1,top+12]})
    merged=heading_rows(parts)
    assert len(merged)==1
    found=read_heading([merged[0]['text_raw']],0)
    assert found['role']=='exercise_type' and found['source_number']=='5'
    assert found['name']=='CÁC BÀI TOÁN THỰC TẾ'


def test_short_wrapped_heading_continuation_is_preserved():
    h=read_heading(['DẠNG 4. CÔNG THỨC XÁC SUẤT TOÀN','PHẦN.'],0)
    assert h['name']=='CÔNG THỨC XÁC SUẤT TOÀN PHẦN.'
