import json
from pathlib import Path

import httpx
import pytest

from pdfmeta.local_client import LocalClient, LocalConfig
from pdfmeta.qwen_review import run, validate_result
from pdfmeta.storage import file_hash, read_json, write_json, write_jsonl


def make_job(tmp_path, *, flags=None, long=False):
    job=tmp_path/'job';root=job/'versions'/'test-version'
    root.mkdir(parents=True)
    (job/'input.pdf').write_bytes(b'read-only source PDF fixture')
    (root/'stem.png').write_bytes(b'image provenance only; not sent to model')
    digest=file_hash(job/'input.pdf')
    items=[]
    for n in (1,2):
        items.append({'schema_version':'pdf-content/v1','question_id':f'{digest}:q1:n{n}',
            'source_number':1,'source':{'pdf_sha256':digest,'spans':[]},
            'student_view':{'stem_text_lossy':'Compute derivative of x^2.'+('x'*2000 if long else ''),'assets':['stem.png']},
            'source_answer':'2x','reference_solution':{'raw_text':"f'(x)=2x",'tables':[],
                'math_audit':{'steps':[{'step_id':f's{n}','kind':'DERIVATIVE_CALCULATION',
                                      'text_candidate':"f(x)=x^2, f'(x)=2x",'formula_groups':[]}]}},
            'quality_flags':flags or [],'academic_review':'PENDING','grading_support':'NOT_ASSESSED','publishable':False})
    write_jsonl(root/'metadata/questions.jsonl',items)
    write_json(job/'latest.json',{'output_directory':str(root),'report':{'source_sha256':digest}})
    (job/'review.html').write_text('original source viewer')
    return job,root


def client(tmp_path, result=None, *, offline=False):
    seen=[]
    result=result or {'status':'NO_ISSUE_FOUND','issues':[],'changes':[]}
    def handle(request):
        if offline:return httpx.Response(503)
        if request.method=='GET':return httpx.Response(200,json={'data':[{'id':'qwen3-vl-2b-instruct'}]})
        body=json.loads(request.content)
        seen.append(body)
        assert all(p['type']=='text' for p in body['messages'][1]['content'])
        assert 'x-goog-api-key' not in request.headers
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}],
                                            'usage':{'total_tokens':55}})
    instance=LocalClient(LocalConfig(runtime=tmp_path,input_mode='metadata',max_output_tokens=512),
                         tmp_path/'usage.jsonl',transport=httpx.MockTransport(handle))
    return instance,seen


def test_review_reuses_model_results_preserves_sources_and_does_not_approve_grading(tmp_path):
    job,root=make_job(tmp_path)
    before=file_hash(root/'metadata/questions.jsonl')
    c,seen=client(tmp_path)
    try:
        first=run(job,tmp_path,client=c,event=lambda x:None)
        second=run(job,tmp_path,client=c,event=lambda x:None)
        assert first['status_counts']=={'MACHINE_CLEARED':2}
        assert second['cache_hits']==2 and len(seen)==2
        assert file_hash(root/'metadata/questions.jsonl')==before
        rows=read_json(Path(second['output_directory'])/'questions.qwen-reviewed.pretty.json')
        assert len({r['question_id'] for r in rows})==2
        assert all(r['academic_review']=='PENDING' and not r['publishable'] and not r['changes_applied'] for r in rows)
        assert second['grading_ready_count']==0 and second['cloud_api_calls']==0
    finally:c.close()


@pytest.mark.parametrize('flags,long,expected',[
    (['PRIVATE_USE_GLYPHS'],False,'PRIVATE_USE_GLYPHS'),
    ([],True,'COMPACT_INPUT_TRUNCATED_REVIEW_REQUIRED')])
def test_model_no_issue_cannot_override_source_conflicts_or_truncated_input(tmp_path,flags,long,expected):
    job,_=make_job(tmp_path,flags=flags,long=long)
    c,_=client(tmp_path)
    try:
        report=run(job,tmp_path,client=c,event=lambda x:None)
        rows=read_json(Path(report['output_directory'])/'questions.qwen-reviewed.pretty.json')
        assert all(r['status']=='MACHINE_FLAGGED' and expected in r['reasons'] for r in rows)
    finally:c.close()


def test_partial_limit_resumes_by_question_id_without_duplicate_inference(tmp_path):
    job,_=make_job(tmp_path)
    c,seen=client(tmp_path)
    try:
        first=run(job,tmp_path,limit=1,client=c,event=lambda x:None)
        assert first['status']=='PARTIAL' and first['status_counts']['DEFERRED']==1
        second=run(job,tmp_path,client=c,event=lambda x:None)
        assert second['status']=='COMPLETE' and second['cache_hits']==1 and len(seen)==2
    finally:c.close()


def test_invalid_model_step_reference_is_deferred_and_raw_response_retained(tmp_path):
    job,_=make_job(tmp_path)
    c,_=client(tmp_path,{'status':'ISSUES_FOUND','issues':[{'code':'STEP_BOUNDARY','step_numbers':[99],'note':'invalid reference'}],'changes':[]})
    try:
        report=run(job,tmp_path,client=c,event=lambda x:None)
        assert report['status_counts']=={'DEFERRED':2}
        assert len(list(Path(report['output_directory']).glob('jobs/*/response.json')))==2
    finally:c.close()


def test_offline_server_exports_deferred_queue_without_inference_or_source_changes(tmp_path):
    job,root=make_job(tmp_path)
    before=file_hash(root/'metadata/questions.jsonl')
    c,seen=client(tmp_path,offline=True)
    try:
        report=run(job,tmp_path,client=c,event=lambda x:None)
        assert report['status']=='PARTIAL' and report['status_counts']=={'DEFERRED':2}
        assert not seen and file_hash(root/'metadata/questions.jsonl')==before
        assert (job/'qwen-review.html').is_file()
    finally:c.close()


def test_reviewer_rejects_mismatched_source_before_contacting_model(tmp_path):
    job,_=make_job(tmp_path)
    (job/'input.pdf').write_bytes(b'changed PDF')
    c,seen=client(tmp_path)
    try:
        with pytest.raises(ValueError,match='SOURCE_MISMATCH'):run(job,tmp_path,client=c)
        assert not seen
    finally:c.close()


def test_model_cannot_merge_nonadjacent_steps_or_produce_unbounded_notes():
    result={'status':'ISSUES_FOUND','issues':[],
            'changes':[{'action':'MERGE','step_numbers':[1,3],'reason':'two separate steps'}]}
    with pytest.raises(ValueError,match='CONSECUTIVE'):validate_result(result,3,False)
    from jsonschema import ValidationError
    result={'status':'ISSUES_FOUND','issues':[{'code':'OTHER','step_numbers':[],'note':'x'*101}],'changes':[]}
    with pytest.raises(ValidationError):validate_result(result,1,False)
