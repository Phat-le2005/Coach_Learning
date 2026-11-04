import json
from pathlib import Path
import zipfile

import pytest
from jsonschema import ValidationError,Draft202012Validator
import pypdfium2 as pdfium

from pdfmeta.readiness.visual import comparable,classify,regions,run as visual_run
from pdfmeta.readiness.core import bounded,export,check,SCHEMA
from pdfmeta.readiness.batch import discover,run as batch_run
from pdfmeta.readiness.evaluation import evaluate
from pdfmeta.storage import file_hash,read_json,write_json,write_jsonl
from pdfmeta.assemble import is_contents_page,assemble


def blank_pdf(path):
    doc=pdfium.PdfDocument.new();page=doc.new_page(600,800);page.close();doc.save(path);doc.close()


def job_fixture(tmp_path,latex='y=x^2',status='NORMALIZED'):
    job=tmp_path/'jobs'/('a'*24);job.mkdir(parents=True);blank_pdf(job/'input.pdf')
    pdf_hash=file_hash(job/'input.pdf')
    step={'step_id':'q1:reasoning:1','kind_candidate':'MODEL_SETUP','text_candidate':latex,
          'source_spans':[{'page_number':1,'bbox':[40,40,200,65]}]}
    row={'question_id':'q1','source_metadata':{'source_number':1,'source':{'pdf_sha256':pdf_hash},
          'reference_solution':{'steps':[step]}},'latex_normalization':[
        {'candidate_id':'c1','question_id':'q1','text_id':step['step_id'],'origin':'GEOMETRY_OR_OCR',
         'raw_text':latex,'latex':latex if status=='NORMALIZED' else None,'status':status,
         'evidence':{'page_number':1,'bbox':[40,40,200,65]}}]}
    final=job/'final/versions/v1/questions.final.jsonl';write_jsonl(final,[row])
    write_json(job/'final.json',{'final_jsonl':str(final),'question_count':1})
    return job,row,final


@pytest.mark.parametrize('a,b,expected',[
 ('y=x^2','y=x^{2}',True),('y=x^2','y=x^3',False),('y=x/x','y=1',False),
 ("f'(x)=2x",'f(x)=2x',False),('y=x2','y=x^2',None),
 ('y=x^2','y=x*x',False),('y=x; x>0','y=x',None)])
def test_image_agreement_preserves_structure_numbers_and_domain(a,b,expected):
    assert comparable(a,b) is expected


def test_image_agreement_never_overrides_source_structure_guard():
    group={'candidates':[{'candidate_id':'x','latex':'y=x^2','raw_text':'y=x^2','status':'SOURCE_LAYOUT_UNRESOLVED'}]}
    assert classify(group,'y=x^2')[0]=='SOURCE_STRUCTURE_BLOCKED'


def test_text_spans_are_not_misrepresented_as_precise_formula_regions():
    rows=[{'question_id':'q','latex_normalization':[{'source_spans':[{'bbox':[0,0,600,800]}]}]}]
    found,unlocated=regions(rows)
    assert not found and unlocated==1


def test_contents_page_is_not_misread_as_five_exercises():
    page={'page_number':1,'blocks':[{'block_id':str(i),'text_raw':t} for i,t in enumerate(
        ['Muåc luåc','Bài 1. Hàm số 1','Bài 2. Đạo hàm 10','Bài 3. Tích phân 20'])]}
    assert is_contents_page(page)
    rows,orphans=assemble([page],'a'*64)
    assert not rows and len(orphans)==4
    assert {o['reason'] for o in orphans}=={'TABLE_OF_CONTENTS_PAGE_EXCLUDED'}
    page['blocks'][0]['text_raw']='Bài 1. Hàm số'
    assert not is_contents_page(page)


def test_image_response_cache_and_final_are_immutable(tmp_path):
    job,_,final=job_fixture(tmp_path);before=file_hash(final)
    class Reader:
        identity={'model':'test-only-stub','weights':'v1'}
        calls=0
        def __call__(self,path):self.calls+=1;return {'rec_formula':'y=x^2'}
    reader=Reader()
    first=visual_run(job,tmp_path/'runtime',limit=1,reader=reader)
    second=visual_run(job,tmp_path/'runtime',limit=1,reader=reader)
    assert reader.calls==1 and first['inference_calls']==1 and second['cache_hits']==1
    assert first['source_verified_count']==0 and first['grading_ready_count']==0
    assert file_hash(final)==before
    reader.identity={'model':'test-only-stub','weights':'v2'}
    assert visual_run(job,tmp_path/'runtime',limit=1,reader=reader)['inference_calls']==1


def test_failed_image_read_is_retained_and_only_explicitly_retried(tmp_path):
    job,_,_=job_fixture(tmp_path)
    class Reader:
        identity={'stub':'failure'}
        calls=0
        def __call__(self,path):self.calls+=1;raise ValueError('unreadable')
    reader=Reader()
    assert visual_run(job,tmp_path/'runtime',reader=reader)['status_counts']=={'IMAGE_OCR_FAILED':1}
    visual_run(job,tmp_path/'runtime',reader=reader)
    assert reader.calls==1
    visual_run(job,tmp_path/'runtime',reader=reader,retry_failed=True)
    assert reader.calls==2


def test_core_contract_is_provisional_and_no_model_can_set_score(tmp_path):
    job,_,_=job_fixture(tmp_path)
    report=export(job)
    assert report['provisional_checkers']==1 and report['grading_ready_count']==0
    result=check(job,{'step_id':'q1:reasoning:1','candidate_latex':'y=x*x'})
    assert result['status']=='CANDIDATE_MATCH' and result['score'] is None and not result['production_grade']
    assert check(job,{'step_id':'q1:reasoning:1','candidate_latex':'y=x^3'})['status']=='CANDIDATE_MISMATCH'
    with pytest.raises(ValueError,match='UNEXPECTED'):
        check(job,{'step_id':'q1:reasoning:1','candidate_latex':'y=x^2','expected_latex':'y=x^2'})
    rows=[json.loads(s) for s in Path(report['package']).read_text(encoding='utf-8').splitlines()]
    rows[0]['publishable']=True
    with pytest.raises(ValidationError):Draft202012Validator(SCHEMA).validate(rows[0])


def test_core_checks_lost_denominator_domain_and_explicit_exclusion(tmp_path):
    job,_,_=job_fixture(tmp_path,'y=x/x');export(job)
    request={'step_id':'q1:reasoning:1','candidate_latex':'y=1'}
    assert check(job,request)['reason']=='DOMAIN_MISMATCH'
    assert check(job,{**request,'declared_excluded':['0']})['status']=='CANDIDATE_MATCH'


@pytest.mark.parametrize('value',['y=sin(x)','y=x^9','y=x+y','y=x; x>0','y=__import__(x)'])
def test_core_does_not_guess_unsupported_symbolic_cases(value):
    with pytest.raises(ValueError):bounded(value)


def test_core_blocks_ambiguous_reference_and_unknown_step(tmp_path):
    job,_,_=job_fixture(tmp_path,'y=x2','UNRESOLVED');export(job)
    assert check(job,{'step_id':'q1:reasoning:1','candidate_latex':'y=x^2'})['status']=='NOT_ASSESSED'
    with pytest.raises(ValueError,match='UNKNOWN'):check(job,{'step_id':'other','candidate_latex':'y=x'})


def test_core_rejects_mutated_or_stale_package(tmp_path):
    job,_,final=job_fixture(tmp_path);report=export(job)
    final.write_text(final.read_text(encoding='utf-8')+'\n',encoding='utf-8')
    with pytest.raises(ValueError,match='STALE'):check(job,{'step_id':'q1:reasoning:1','candidate_latex':'y=x^2'})
    export(job);package=Path(read_json(job/'core-package.json')['package']);package.write_text('{}')
    with pytest.raises(ValueError,match='CHANGED'):check(job,{'step_id':'q1:reasoning:1','candidate_latex':'y=x^2'})


def test_archive_discovery_deduplicates_and_never_extracts_member_paths(tmp_path):
    pdf=tmp_path/'a.pdf';blank_pdf(pdf);archive=tmp_path/'data.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('../../escape.pdf',pdf.read_bytes());z.writestr('nested/copy.pdf',pdf.read_bytes())
    items=discover([archive,pdf],tmp_path/'cache')
    assert len(items)==1 and not (tmp_path/'escape.pdf').exists()
    cache=next((tmp_path/'cache').rglob('*.pdf'));original=cache.read_bytes()
    cache.write_bytes(b'x'*len(original));discover([archive],tmp_path/'cache')
    assert cache.read_bytes()==original


def test_queue_is_sequential_budgeted_resumable_and_retries_failed_explicitly(tmp_path):
    # Windows repository temp roots stay on E; no model or external command in this test.
    folder=tmp_path/'inputs';folder.mkdir();blank_pdf(folder/'one.pdf')
    two=folder/'two.pdf';blank_pdf(two);two.write_bytes(two.read_bytes()+b'\n')
    calls=[]
    def worker(item,**kwargs):
        calls.append(item['job_id']);job=tmp_path/'storage/pdf-jobs'/item['job_id'];job.mkdir(parents=True,exist_ok=True)
        for name in ['final.json','image-check.json','core-package.json']:write_json(job/name,{'stub':True})
        return {'job':str(job),'final':str(job/'final.json')}
    args=dict(repo=Path(__file__).parents[3],storage=tmp_path/'storage',executor=worker,max_pages=1)
    first=batch_run([folder],**args);assert first['counts']=={'COMPLETED':1,'PENDING':1} and len(calls)==1
    second=batch_run([folder],**args);assert second['counts']=={'COMPLETED':2} and len(calls)==2
    batch_run([folder],**args);assert len(calls)==2
    queue=read_json(Path(second['queue']));entry=queue['items'][0]
    assert entry['seconds'] is not None and entry['started_at'] and entry['finished_at']
    Path(entry['result']['final']).write_text('{}')
    batch_run([folder],**args);assert len(calls)==3


def test_failed_queue_item_does_not_loop_automatically(tmp_path):
    pdf=tmp_path/'a.pdf';blank_pdf(pdf);calls=[]
    def worker(*args,**kwargs):calls.append(1);raise TimeoutError('bounded')
    args=dict(repo=Path(__file__).parents[3],storage=tmp_path/'storage',executor=worker)
    assert batch_run([pdf],**args)['status']=='PARTIAL'
    batch_run([pdf],**args);assert len(calls)==1
    batch_run([pdf],**args,retry_failed=True);assert len(calls)==2


def test_oversize_document_runs_whole_or_is_explicitly_deferred(tmp_path):
    pdf=tmp_path/'large.pdf'
    document=pdfium.PdfDocument.new()
    for _ in range(2):document.new_page(600,800).close()
    document.save(pdf);document.close()
    calls=[]
    def worker(item,**kwargs):
        calls.append(item['job_id']);job=tmp_path/'storage/pdf-jobs'/item['job_id'];job.mkdir(parents=True,exist_ok=True)
        for name in ['final.json','image-check.json','core-package.json']:write_json(job/name,{'stub':True})
        return {'job':str(job),'final':str(job/'final.json')}
    args=dict(repo=Path(__file__).parents[3],storage=tmp_path/'storage',executor=worker,max_pages=1)
    deferred=batch_run([pdf],**args,oversize_policy='defer')
    queue=read_json(Path(deferred['queue']))
    assert not calls and queue['items'][0]['defer_reason']=='DOCUMENT_EXCEEDS_PAGE_BUDGET'
    completed=batch_run([pdf],**args,oversize_policy='run')
    queue=read_json(Path(completed['queue']))
    assert len(calls)==1 and completed['status']=='COMPLETED'
    assert queue['items'][0]['pages']==2 and queue['items'][0]['budget_overrun_pages']==1


def test_evaluation_does_not_mix_new_artifacts_with_an_old_queue(tmp_path):
    artifact=tmp_path/'result.json';write_json(artifact,{'v':1})
    queue=tmp_path/'queue.json'
    write_json(queue,{'items':[{'pdf':'sample.pdf','status':'COMPLETED','result_hashes':{str(artifact):file_hash(artifact)}}]})
    write_json(artifact,{'v':2})
    report=evaluate(queue)
    assert report['documents'][0]['status']=='STALE_RESULT'
    assert report['production_ready'] is False
