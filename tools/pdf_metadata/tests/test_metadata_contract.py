from copy import deepcopy

import pytest

from pdfmeta.metadata_contract import (normalize_record, normalize_method, validate_records,
                                      migrate, project, METADATA_VERSION, METHOD_VERSION)
from pdfmeta.storage import write_json,read_json,file_hash


def legacy():
    return {'question_id':'q1','collection_number':1,'chapter_title':'Toan12',
            'source':{'sha256':'a'*64},'question':{'markdown':'Đề bài $P(A)=0,5$'},
            'solution':{'markdown':'Lời giải nguyên bản.'},'answer':{'markdown':''},
            'method':{'schema_version':'question-method-candidates/v1',
                      'chapter':{'code':'C1','name':'Chương một'},
                      'lesson':{'code':'L1','name':'Bài một'},'exercise_type':None,
                      'candidates':[],'status':'DRAFT_CANDIDATE','review_required':True}}


def test_source_and_inferred_labels_share_exact_keys_and_evidence_array():
    a=legacy();b=deepcopy(a)
    b['method']['schema_version']='question-method-candidates/v2'
    b['method']['lesson']={'code':'DOC_LESSON_1','name':'Bài nguồn','canonical_code':None,
        'source_number':'II','source_label':'BÀI II. Bài nguồn','parent_code':'C1',
        'basis':'PRINTED_DOCUMENT_HEADING','evidence':{'page_number':3,'bbox':[0,10,100,20],'text':'Bài nguồn'}}
    rows=[normalize_record(a),normalize_record(b)]
    assert validate_records(rows)['valid']
    assert rows[0].keys()==rows[1].keys()
    assert rows[0]['method'].keys()==rows[1]['method'].keys()
    assert rows[0]['method']['lesson'].keys()==rows[1]['method']['lesson'].keys()
    assert rows[0]['method']['lesson']['evidence']==[]
    assert isinstance(rows[1]['method']['lesson']['evidence'],list)
    assert rows[0]['source_number'] is None
    assert rows[0]['topic_context']['exercise_type'] is None
    assert rows[0]['method']['inference_candidates']==[]


def test_schema_version_is_fixed_and_pipeline_version_is_separate():
    q=normalize_record(legacy())
    assert q['schema_version']==METADATA_VERSION
    assert q['method']['schema_version']==METHOD_VERSION
    assert q['method']['pipeline_version']=='question-method-candidates/v1'
    assert normalize_record(q)==q


def test_unknown_fields_are_retained_only_in_explicit_extensions():
    old=legacy();old['custom_source_tag']={'name':'kept'}
    old['method']['lesson']['new_optional_field']='kept label data'
    q=normalize_record(old)
    assert validate_records([q])['valid']
    assert q['extensions']['custom_source_tag']=={'name':'kept'}
    assert q['method']['lesson']['extensions']['new_optional_field']=='kept label data'
    assert 'new_optional_field' not in q['method']['lesson']


@pytest.mark.parametrize('change', ['missing_key','unexpected_key','wrong_evidence_type','wrong_method_version'])
def test_export_gate_rejects_schema_drift(change):
    q=normalize_record(legacy())
    if change=='missing_key':q['method'].pop('inference_candidates')
    elif change=='unexpected_key':q['method']['lesson']['surprise']='value'
    elif change=='wrong_evidence_type':q['method']['lesson']['evidence']={}
    else:q['method']['schema_version']='question-method/v999'
    with pytest.raises(ValueError,match='METADATA_SCHEMA_INVALID'):validate_records([q])


def test_migration_preserves_text_labels_and_input_bytes(tmp_path):
    old=legacy();path=tmp_path/'old.json';output=tmp_path/'new.json'
    write_json(path,[old]);before=file_hash(path)
    report=migrate(path,output)
    q=read_json(output)[0]
    assert report['valid'] and file_hash(path)==before
    assert project(q['question'],old['question'])==old['question']
    assert q['method']['lesson']['code']=='L1' and q['method']['lesson']['name']=='Bài một'
    assert q['method']['exercise_type'] is None
    assert q['method']['document_labels']=={'chapter':None,'lesson':None,'exercise_type':None,'extensions':{}}


def test_fragment_optional_fields_are_always_present_and_visual_payload_is_preserved():
    q=legacy()
    q['question']['fragments']=[{'markdown':'Ảnh nguồn','blocks':[{'kind':'VISUAL','markdown':'Ảnh','asset_id':'asset-1'}],
                                 'custom_provenance':{'crop':1}}]
    out=normalize_record(q)
    f=out['question']['fragments'][0]
    assert f['quality_audit'] is None
    assert f['blocks'][0]['asset_id']=='asset-1'
    assert f['extensions']['custom_provenance']=={'crop':1}
    assert validate_records([out])['valid']
