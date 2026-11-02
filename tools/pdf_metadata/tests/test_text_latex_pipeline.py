import json
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator,ValidationError

from pdfmeta.document_pipeline import run as complete,FINAL_SCHEMA
from pdfmeta.latex_stage import normalize_formula,proposal_row,validate_proposals
from pdfmeta.local_client import LocalClient,LocalConfig
from pdfmeta.safe_math import UnsupportedMath,assignment,equivalent
from pdfmeta.storage import file_hash,read_json,write_json,write_jsonl


@pytest.mark.parametrize('raw,expected',[
    ('y=x²-3x+2',r'y=x^{2}-3\cdot x+2'),
    ('y=x/x',r'y=\frac{x}{x}'),
    ('y=sqrt(x+1)',r'y=\sqrt{x+1}'),
    ('y=sin(x)',r'y=\sin\left(x\right)'),
    ('y=1,5x',r'y=1{,}5\cdot x'),
    (r'y=\frac{x}{x-1}',r'y=\frac{x}{x-1}')])
def test_text_latex_formats_without_simplifying_or_dropping_domain(raw,expected):
    assert normalize_formula(raw)==expected
    if raw=='y=x/x':assert assignment(expected)['denominators']


@pytest.mark.parametrize('raw',['y=x2','y=1/2x','y=a/bc','y=x; x>0',
    'y=x, x>0',r'y=x\quad x>0','y=1=2','y=g(x)','y=\uf0b4x','y=[chưa chuẩn hóa U+F123]',
    r'y=\input{evil}','y=__import__(x)','y=x⇒x=0'])
def test_uncertain_text_is_not_repaired_by_guessing(raw):
    with pytest.raises((UnsupportedMath,ValueError)):normalize_formula(raw)


def test_model_can_only_reference_code_owned_source_fragments():
    fragments={'f1':{'raw_text':'y=x2'}}
    result={'status':'CANDIDATES','candidates':[{'fragment_id':'f1','latex':'y=x^2','ambiguous':False}]}
    validate_proposals(result,fragments)
    result['candidates'].append(dict(result['candidates'][0]))
    with pytest.raises(ValueError,match='DUPLICATE'):validate_proposals(result,fragments)
    result['candidates']=[{'fragment_id':'invented','latex':'y=x^2','ambiguous':False}]
    with pytest.raises(ValueError,match='UNKNOWN_FRAGMENT_ID'):validate_proposals(result,fragments)


@pytest.mark.parametrize('raw,latex,accepted',[
    ('y=x2','y=x^2',False),('y=x/x','y=1',False),('y=2*x','y=x+x',False),
    ('y=x/(x-1)',r'y=\frac{x}{x-1}',True)])
def test_model_cannot_change_numbers_infer_lost_powers_or_cancel_domain(raw,latex,accepted):
    units=[{'text_id':'stem','text':raw,'source_spans':[{'page_number':1}]}]
    result=proposal_row({'question_id':'q1'},dict(text_id='stem',source_text=raw,latex=latex,ambiguous=False),units)
    assert (result['status']=='NORMALIZED') is accepted
    assert result['raw_text']==raw and not result['source_verified']
    assert result['normalized_text_offsets']==[0,len(raw)]


def make_job(tmp_path):
    job=tmp_path/'job';root=job/'versions/original'
    root.mkdir(parents=True);(job/'input.pdf').write_bytes(b'fixed test source')
    digest=file_hash(job/'input.pdf');items=[]
    for n in (1,2):
        text='y=x2' if n==1 else "y'=2*x"
        items.append({'schema_version':'pdf-content/v1','question_id':f'{digest}:q{n}',
            'source_number':n,'source':{'pdf_sha256':digest,'spans':[]},
            'student_view':{'stem_text_lossy':'Find derivative: '+text,'assets':[]},'source_answer':'2x',
            'reference_solution':{'raw_text':text,'steps':[], 'tables':[],
                'math_audit':{'source_definitions':[],'steps':[{'step_id':f's{n}','number':1,'kind':'DERIVATIVE_CALCULATION',
                    'text_candidate':text,'source_spans':[],'formula_groups':[]}]}},
            'quality_flags':[],'academic_review':'PENDING','grading_support':'NOT_ASSESSED','publishable':False})
    write_jsonl(root/'metadata/questions.jsonl',items)
    write_json(job/'latest.json',{'output_directory':str(root),'report':{'source_sha256':digest}})
    (job/'review.html').write_text('source viewer')
    return job,root


def fake_client(tmp_path):
    seen=[]
    def handle(request):
        if request.method=='GET':return httpx.Response(200,json={'data':[{'id':'qwen3-vl-2b-instruct'}]})
        body=json.loads(request.content);seen.append(body)
        assert all(p['type']=='text' for p in body['messages'][1]['content'])
        data=json.loads(body['messages'][1]['content'][0]['text'])
        if data['scope']=='TEXT_TO_LATEX_ONLY':
            result={'status':'CANDIDATES','candidates':[{'fragment_id':'f1','latex':'y=x^{2}','ambiguous':True}]}
        else:result={'status':'NO_ISSUE_FOUND','issues':[],'changes':[]}
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}],
                                       'usage':{'total_tokens':80}})
    return LocalClient(LocalConfig(runtime=tmp_path,input_mode='metadata',max_calls=5),tmp_path/'usage.jsonl',
                       transport=httpx.MockTransport(handle)),seen


def test_complete_pipeline_shares_local_model_preserves_raw_and_resumes_both_stages(tmp_path):
    job,root=make_job(tmp_path);before=file_hash(root/'metadata/questions.jsonl')
    c,seen=fake_client(tmp_path)
    try:
        first=complete(job,tmp_path,repo=tmp_path,client=c)
        second=complete(job,tmp_path,repo=tmp_path,client=c)
        assert len(seen)==3
        assert second['latex']['cache_hits']==1 and second['qwen_review']['cache_hits']==2
        assert second['latex']['local_inference_calls']==second['qwen_review']['local_inference_calls']==0
        assert first['final_jsonl']==second['final_jsonl']
        assert file_hash(root/'metadata/questions.jsonl')==before
        rows=read_json(Path(second['final_pretty_json']))
        for row in rows:Draft202012Validator(FINAL_SCHEMA).validate(row)
        assert rows[0]['processing_status']=='MACHINE_FLAGGED'
        assert rows[1]['processing_status']=='MACHINE_CLEARED'
        assert all(not r['publishable'] and r['grading_support']=='NOT_ASSESSED' for r in rows)
        assert (job/'final.html').is_file()
        assert read_json(job/'result.json')['final_metadata_jsonl']==second['final_jsonl']
    finally:c.close()


def test_rules_only_still_exports_final_artifact_with_review_explicitly_deferred(tmp_path):
    job,root=make_job(tmp_path)
    report=complete(job,tmp_path,repo=tmp_path,rules_only=True)
    assert report['status']=='DRAFT_PARTIAL' and report['status_counts']=={'DEFERRED':2}
    assert report['latex']['local_inference_calls']==0 and report['cloud_api_calls']==0
    rows=read_json(Path(report['final_pretty_json']))
    rows[0]['publishable']=True
    with pytest.raises(ValidationError):Draft202012Validator(FINAL_SCHEMA).validate(rows[0])


def test_complete_pipeline_rejects_foreign_version_or_pdf(tmp_path):
    job,root=make_job(tmp_path)
    (job/'input.pdf').write_bytes(b'different file')
    with pytest.raises(ValueError,match='SOURCE_PDF_CHANGED'):complete(job,tmp_path,repo=tmp_path,rules_only=True)


def test_no_question_document_does_not_claim_completed_questions_or_contact_model(tmp_path):
    job,root=make_job(tmp_path)
    write_jsonl(root/'metadata/questions.jsonl',[])
    report=complete(job,tmp_path,repo=tmp_path)
    assert report['status']=='PAGE_METADATA_ONLY' and report['question_count']==0
    assert report['qwen_review']['status']=='SKIPPED'
    assert Path(report['final_jsonl']).read_text()==''
    assert 'cấu trúc câu hỏi' in (Path(report['output_directory'])/'review.html').read_text(encoding='utf-8')
