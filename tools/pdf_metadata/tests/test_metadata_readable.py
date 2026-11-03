import hashlib
import json
from pathlib import Path

import pytest

from pdfmeta.paired.metadata_readable import export, has_unmapped_glyphs


def question(qid='source:q1:n1'):
    return {'schema_version':'paired-question/v1','question_id':qid,'collection_number':1,
        'chapter_id':'integrals','chapter_title':'Nguyên hàm, tích phân','source_label':'Câu 1.',
        'source':{'name':'nguon.pdf','sha256':'a'*64},
        'question':{'text_lossy':'Tính \\frac{1}{x}.\nKý hiệu nguồn: \uf0a2',
            'source_spans':[{'page_number':3,'bbox':[0,12.345678,100,200],'block_ids':['p3-b1']}]},
        'solution':{'text_lossy':'Lời giải nguồn, giữ nguyên dấu và xuống dòng.\nDòng thứ hai.',
            'source_spans':[{'page_number':4,'bbox':[0,1,100,201],'block_ids':['p4-b2']}]},
        'answer':{'text_raw':None,'source_spans':[],'status':'NOT_EXPLICITLY_LABELLED'},
        'academic_review':'PENDING','grading_support':'NOT_ASSESSED','publishable':False,
        'quality_flags':['SOURCE_MATH_NOT_VERIFIED'],'collection_pdf_pages':[2,3],
        'collection_source_spans':[{'page_number':3,'asset_path':'assets/original.png'}]}


def make_source(root,records):
    p=root/'metadata.jsonl'
    p.write_text(''.join(json.dumps(q,ensure_ascii=False)+'\n' for q in records),encoding='utf-8')
    return p


def test_pretty_json_and_individual_files_preserve_all_values_and_review_states(tmp_path):
    q=question();source=make_source(tmp_path,[q]);original=source.read_bytes()
    result=export(source)
    pretty=Path(result['pretty_json']).read_text(encoding='utf-8')
    assert json.loads(pretty)==[q] and '\n    "question": {' in pretty
    assert pretty.index('"question":')<pretty.index('"question_id":')
    assert source.read_bytes()==original
    catalog=json.loads((tmp_path/'metadata-catalog.json').read_text(encoding='utf-8'))
    entry=catalog['questions'][0]
    assert entry['source_pages']==[3,4] and entry['pdf_pages']==[2,3]
    assert json.loads((tmp_path/entry['record']).read_text(encoding='utf-8'))==q
    assert result['source_sha256']==hashlib.sha256(original).hexdigest()
    assert result['inference_calls']==0
    assert entry['damaged_text_roles']==['question']


@pytest.mark.parametrize('text,damaged', [('x² + 1',False),(r'\frac{1}{x}',False),('\uf028',True),('\ufffd',True),('\U000f0010',True)])
def test_damaged_encoding_is_detected_without_rewriting_math(text,damaged):
    assert has_unmapped_glyphs(text) is damaged


def test_unsafe_source_ids_are_only_used_as_text_not_filesystem_names(tmp_path):
    q=question('../outside/<img src=x onerror=alert(1)>');source=make_source(tmp_path,[q])
    export(source)
    catalog=json.loads((tmp_path/'metadata-catalog.json').read_text(encoding='utf-8'))
    record=(tmp_path/catalog['questions'][0]['record']).resolve()
    assert record.is_relative_to(tmp_path) and '<img' not in record.name
    assert json.loads(record.read_text(encoding='utf-8'))['question_id']==q['question_id']
    assert q['question_id'] not in (tmp_path/'metadata.html').read_text(encoding='utf-8')


def test_duplicate_id_refuses_to_publish_a_pretty_array_or_catalog(tmp_path):
    q=question();source=make_source(tmp_path,[q,q]);before=source.read_bytes()
    with pytest.raises(ValueError,match='DUPLICATE_QUESTION_ID'):export(source)
    assert source.read_bytes()==before and not (tmp_path/'metadata.pretty.json').exists()
    assert not (tmp_path/'metadata-catalog.json').exists()


def test_matching_catalog_keeps_zero_selected_source_visible(tmp_path):
    source=make_source(tmp_path,[question()])
    (tmp_path/'index-data.json').write_text(json.dumps({'questions':[{'question_id':'source:q1:n1'}],
        'documents':[{'source_pdf_sha256':'b'*64,'label':'integrals/question-only.pdf'}]}),encoding='utf-8')
    export(source)
    catalog=json.loads((tmp_path/'metadata-catalog.json').read_text(encoding='utf-8'))
    assert len(catalog['documents'])==2 and catalog['documents'][1]['count']==0


def test_unrelated_catalog_cannot_add_foreign_documents(tmp_path):
    source=make_source(tmp_path,[question()])
    (tmp_path/'index-data.json').write_text(json.dumps({'questions':[{'question_id':'other'}],
        'documents':[{'source_pdf_sha256':'b'*64,'label':'foreign.pdf'}]}),encoding='utf-8')
    export(source)
    assert json.loads((tmp_path/'metadata-catalog.json').read_text(encoding='utf-8'))['documents']==[
        {'id':'a'*64,'name':'nguon.pdf','count':1}]
