import pytest

from pdfmeta.method_labels import load_taxonomy, DEFAULT_TAXONOMY, page_chapters, label_record, run
from pdfmeta.storage import write_json, read_json, file_hash
from pdfmeta.metadata_contract import project, METADATA_VERSION


@pytest.fixture(scope='module')
def taxonomy():return load_taxonomy(DEFAULT_TAXONOMY)


def row(text, pn=2):
    return {'question_id':'source:q1','collection_number':1,'chapter_title':'Toan12',
            'source':{'sha256':'a'*64},'question':{'markdown':text,'source_spans':[{'page_number':pn}]},
            'solution':{'markdown':'Lời giải nguồn'},'publishable':False}


def contexts(code='DERIVATIVE_APPLICATIONS'):
    return {2:{'code':code,'evidence':{'page_number':2,'text':'Source chapter','basis':'SOURCE_NATIVE_PAGE_HEADER'}}}


def test_source_header_propagates_only_over_consecutive_pages():
    pages=[{'page_number':2,'native_text_from_this_pdf':'ỨNG DỤNG ĐẠO HÀM VÀ ĐỒ THỊ HÀM SỐ Câu hỏi kèm lời giải'},
           {'page_number':3,'native_text_from_this_pdf':''}, {'page_number':5,'native_text_from_this_pdf':''},
           {'page_number':6,'native_text_from_this_pdf':'NGUYÊN HÀM, TÍCH PHÂN VÀ ỨNG DỤNG Câu hỏi kèm lời giải'}]
    result=page_chapters(pages)
    assert result[2]['code']==result[3]['code']=='DERIVATIVE_APPLICATIONS'
    assert result[3]['evidence']['page_number']==2
    assert 5 not in result
    assert result[6]['code']=='INTEGRALS'


@pytest.mark.parametrize('text,lesson,kind',[
    ('Tìm các khoảng đơn điệu của hàm số có đồ thị cho ở hình bên.', 'MONOTONICITY_TOPIC','MONOTONICITY_FROM_GRAPH'),
    ('Cho bảng biến thiên của đạo hàm f\'(x). Tìm khoảng đồng biến của hàm số f(x).', 'MONOTONICITY_TOPIC','MONOTONICITY_FROM_DERIVATIVE_SIGN'),
    ('Tìm cực trị của hàm số có bảng biến thiên như sau.', 'EXTREMA_TOPIC','EXTREMA_FROM_VARIATION_TABLE'),
    ('Tìm tham số m để hàm số đồng biến trên R.', 'MONOTONICITY_TOPIC','PARAMETER_MONOTONICITY'),
    ('Tìm giá trị lớn nhất của hàm số trên đoạn [1;2].', 'GLOBAL_EXTREMA_TOPIC','GLOBAL_EXTREMA_DERIVATIVE_INTERVAL'),
    ('Tìm tập hợp các giá trị để hàm số đạt giá trị lớn nhất trên đoạn [1;2].', 'GLOBAL_EXTREMA_TOPIC','GLOBAL_EXTREMA_DERIVATIVE_INTERVAL'),
    ('Tìm lợi nhuận lớn nhất của công ty.', 'DERIVATIVE_APPLICATION_TOPIC','REAL_WORLD_DERIVATIVE_OPTIMIZATION'),
    ('Đường cong trong hình là đồ thị của hàm số nào dưới đây?', 'FUNCTION_ANALYSIS_TOPIC','GRAPH_IDENTIFICATION_FROM_FEATURES'),
])
def test_derivative_problem_labels_follow_requested_goal(taxonomy,text,lesson,kind):
    m=label_record(row(text),contexts(),taxonomy)
    assert m['lesson']['code']==lesson and m['exercise_type']['code']==kind
    assert m['review_required'] and m['status']=='DRAFT_CANDIDATE'


def test_options_do_not_classify_the_stem_and_multiple_goals_remain_candidates(taxonomy):
    m=label_record(row('Tìm cực trị của hàm số.\nA. Hàm số đồng biến trên R.\nB. Giá trị lớn nhất bằng 5.'),contexts(),taxonomy)
    assert m['lesson']['code']=='EXTREMA_TOPIC'
    multiple=label_record(row('Tìm khoảng đồng biến và các điểm cực trị của hàm số.'),contexts(),taxonomy)
    assert multiple['lesson'] is None and multiple['exercise_type'] is None
    assert len(multiple['candidates'])==2 and 'MULTIPLE_LESSON_CANDIDATES' in multiple['flags']


@pytest.mark.parametrize('text,lesson,kind',[
    ('Tìm nguyên hàm của hàm số f(x).', 'ANTIDERIVATIVE_TOPIC','CALCULATE_ANTIDERIVATIVE'),
    ('Tìm nguyên hàm F(x) biết F(0)=1.', 'ANTIDERIVATIVE_TOPIC','ANTIDERIVATIVE_WITH_CONDITION'),
    ('Tính diện tích hình phẳng giới hạn bởi hai đường cong.', 'INTEGRAL_GEOMETRIC_APPLICATION_TOPIC','AREA_BY_INTEGRAL'),
    ('Tính thể tích khối tròn xoay.', 'INTEGRAL_GEOMETRIC_APPLICATION_TOPIC','VOLUME_BY_INTEGRAL'),
    ('Tính thể tích vật thể có thiết diện với diện tích S(x).', 'INTEGRAL_GEOMETRIC_APPLICATION_TOPIC','VOLUME_BY_CROSS_SECTION'),
    ('Vật chuyển động có vận tốc v(t). Tính quãng đường đi được.', 'INTEGRAL_PRACTICAL_APPLICATION_TOPIC','PRACTICAL_ACCUMULATION'),
])
def test_integral_problem_labels(taxonomy,text,lesson,kind):
    m=label_record(row(text),contexts('INTEGRALS'),taxonomy)
    assert m['lesson']['code']==lesson and m['exercise_type']['code']==kind


def test_missing_and_conflicting_chapters_do_not_get_guessed(taxonomy):
    missing=label_record(row('Tìm cực trị của hàm số.'),{},taxonomy)
    assert missing['status']=='UNCLASSIFIED' and not missing['chapter']
    q=row('Tính tích phân.');q['chapter_title']='Nguyên hàm và tích phân'
    conflict=label_record(q,contexts(),taxonomy)
    assert conflict['chapter'] is None and 'CONFLICTING_SOURCE_CHAPTERS' in conflict['flags']


def test_export_preserves_every_existing_field_and_binds_source_hashes(tmp_path):
    q=row('Tìm cực trị của hàm số có đồ thị cho ở hình bên.')
    source=tmp_path/'input.json';pages=tmp_path/'pages.json'
    write_json(source,[q]);write_json(pages,[{'page_number':2,'native_text_from_this_pdf':'ỨNG DỤNG ĐẠO HÀM VÀ ĐỒ THỊ HÀM SỐ'}])
    before=file_hash(source)
    report=run(source,pages,tmp_path/'labeled')
    result=read_json(tmp_path/'labeled/content.method.pretty.json')[0]
    method=result['method']
    assert project(result,q)==q and file_hash(source)==before
    assert result['schema_version']==METADATA_VERSION
    assert report['input_sha256']==before and report['questions']==1
    assert method['exercise_type']['code']=='EXTREMA_FROM_GRAPH'
    with pytest.raises(ValueError,match='SEPARATE_OUTPUT'):run(source,pages,tmp_path)


def test_mismatched_page_export_is_rejected(tmp_path):
    source=tmp_path/'input.json';pages=tmp_path/'pages.json'
    write_json(source,[row('Tìm cực trị của hàm số.')])
    write_json(pages,[{'page_number':2,'native_text_from_this_pdf':'ỨNG DỤNG ĐẠO HÀM'}])
    write_json(tmp_path/'run-identity.json',{'input_sha256':'b'*64})
    with pytest.raises(ValueError,match='SOURCE_HASH_MISMATCH'):run(source,pages,tmp_path/'out')


def test_labeling_strategies_export_identical_contracts_and_matching_overlays(tmp_path):
    q=row('Tìm cực trị của hàm số có đồ thị cho ở hình bên.')
    source=tmp_path/'input.json';pages=tmp_path/'pages.json'
    write_json(source,[q])
    write_json(pages,[{'page_number':2,'native_text_from_this_pdf':'ỨNG DỤNG ĐẠO HÀM VÀ ĐỒ THỊ HÀM SỐ'}])
    exported=[]
    for policy in ('source','source-and-rules'):
        folder=tmp_path/policy
        run(source,pages,folder,labels_from=policy)
        result=read_json(folder/'content.method.pretty.json')[0]
        overlay=read_json(folder/'methods.pretty.json')[0]
        assert overlay['method']==result['method']
        assert read_json(folder/'schema-validation.json')['valid']
        exported.append(result)
    a,b=exported
    assert a.keys()==b.keys()
    assert a['method'].keys()==b['method'].keys()
    assert a['method']['chapter'].keys()==b['method']['chapter'].keys()
    assert a['method']['exercise_type'] is None
    assert b['method']['exercise_type']['code']=='EXTREMA_FROM_GRAPH'


def test_statistics_rules_keep_multi_measure_and_variance_sd_candidates(taxonomy):
    ctx=contexts('GROUPED_DATA_DISPERSION')
    m=label_record(row('Tính khoảng biến thiên và khoảng tứ phân vị của mẫu ghép nhóm.'),ctx,taxonomy)
    assert m['exercise_type']['code']=='MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS'
    m=label_record(row('Tính phương sai và độ lệch chuẩn của mẫu số liệu ghép nhóm.'),ctx,taxonomy)
    assert m['lesson']['code']=='GROUPED_VARIANCE_SD_TOPIC'
    assert m['exercise_type'] is None and len(m['candidates'])==2


def test_wrong_source_pdf_is_rejected_before_reading_its_pages(tmp_path):
    source=tmp_path/'input.json';pages=tmp_path/'pages.json';pdf=tmp_path/'wrong.pdf'
    write_json(source,[row('Tính phương sai.')]);write_json(pages,[]);pdf.write_bytes(b'other source')
    with pytest.raises(ValueError,match='ORIGINAL_PDF_HASH_MISMATCH'):
        run(source,pages,tmp_path/'out',source_pdf=pdf)


def test_named_probability_method_in_source_solution_keeps_its_provenance(taxonomy):
    q=row('Tính xác suất để sản phẩm do nhà máy thứ nhất sản xuất.')
    q['solution']['markdown']='Áp dụng công thức Bayes, ta có kết quả.'
    m=label_record(q,contexts('PROBABILITY_CHAPTER'),taxonomy)
    assert m['exercise_type']['code']=='BAYES_POSTERIOR'
    assert m['candidates'][0]['evidence']['field']=='solution.markdown'
    assert m['review_required']
