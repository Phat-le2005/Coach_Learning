from pathlib import Path
import json

import pytest
import sympy as sp

from pdfmeta.math_value import record,compare,expression
from pdfmeta.pdf_workflow import Checkpoints,local_lock
from pdfmeta.storage import write_json,read_json
from pdfmeta.auto_ocr import needs_text_ocr
from pdfmeta.safe_math import UnsupportedMath


@pytest.mark.parametrize('source,canonical,kind',[(r'\ln 5','log(5)','CONSTANT_EXPRESSION'),
    (r'\sqrt{2}','sqrt(2)','CONSTANT_EXPRESSION'),('1/2','1/2','NUMBER'),
    ('m+1','m + 1','SYMBOLIC_EXPRESSION'),(r'+\infty','+inf','INFINITY')])
def test_math_values_preserve_expression_separately_from_approximation(source,canonical,kind):
    value=record(source)
    assert value['source_expression']==source and value['canonical_expression']==canonical
    assert value['kind']==kind
    if kind in {'SYMBOLIC_EXPRESSION','INFINITY'}:assert value['approximate_value'] is None
    else:assert value['approximate_value'] is not None


def test_symbolic_endpoint_order_requires_assumptions_instead_of_a_float_guess():
    assert compare('m','m+1')=='LT'
    assert compare('m','0')=='UNKNOWN'
    assert compare(r'\ln5',r'+\infty')=='LT'
    assert compare('0',r'\sqrt{2}')=='LT'


@pytest.mark.parametrize('value',[r'\phantom{0}','1e9999999','__import__(x)','sqrt(-1)'])
def test_value_parser_cannot_execute_or_accept_ambiguous_domain(value):
    with pytest.raises(UnsupportedMath):expression(value)


def test_completed_stage_is_reused_but_modified_output_is_recomputed(tmp_path):
    calls=[]
    def task():
        calls.append(1);path=tmp_path/'output.json';write_json(path,{'generation':len(calls)})
        return {'generation':len(calls)},[path]
    c=Checkpoints(tmp_path,lambda *args:None)
    assert c.run('extract',{'source':'one'},task)['generation']==1
    assert c.run('extract',{'source':'one'},task)['generation']==1
    assert c.hits==1
    write_json(tmp_path/'output.json',{'modified':True})
    assert c.run('extract',{'source':'one'},task)['generation']==2
    assert c.run('extract',{'source':'two'},task)['generation']==3


def test_interrupted_local_stage_is_resumable_without_claiming_completion(tmp_path):
    c=Checkpoints(tmp_path,lambda *args:None)
    with pytest.raises(KeyboardInterrupt):
        c.run('local',{},lambda:(_ for _ in ()).throw(KeyboardInterrupt()))
    assert read_json(tmp_path/'state.json')['stages']['local']['status']=='INTERRUPTED'
    target=tmp_path/'done.json'
    def succeed():write_json(target,{'ok':True});return {},[target]
    c.run('local',{},succeed)
    assert read_json(tmp_path/'state.json')['stages']['local']['status']=='COMPLETE'


def test_job_lock_does_not_delete_an_active_owner(tmp_path):
    with local_lock(tmp_path):
        with pytest.raises(ValueError,match='ALREADY_RUNNING'):
            with local_lock(tmp_path):pytest.fail('Must not enter')
    assert not (tmp_path/'.workflow.lock').exists()


def test_job_lock_recovers_a_dead_local_owner(tmp_path):
    import psutil
    dead=max(psutil.pids())+100000
    write_json(tmp_path/'.workflow.lock',{'pid':dead,'created':0})
    with local_lock(tmp_path):assert read_json(tmp_path/'.workflow.lock')['pid']!=dead


def test_image_page_with_only_a_header_gets_ocr_but_digital_page_does_not():
    base={'width':600,'height':800,'images':[{'bbox':[0,0,600,800]}],
          'blocks':[{'text_raw':'Scanned page 1','is_margin':False}]}
    assert needs_text_ocr(base)
    assert not needs_text_ocr({**base,'images':[],'blocks':[{'text_raw':'Câu 1. Một đề bài đủ dài. '*30,'is_margin':False}]})


def test_source_book_captions_do_not_hide_image_only_exercises():
    page={'width':600,'height':800,'images':[{'bbox':[40,100,560,350]}],
          'blocks':[{'text_raw':'Printed source caption. '*14,'is_margin':False}]}
    assert needs_text_ocr(page)
    assert not needs_text_ocr({**page,'images':[]})
    assert not needs_text_ocr({**page,'blocks':[{'text_raw':'Actual native exercise text. '*30}]})


def test_expression_endpoint_is_checked_exactly_without_approving_the_source():
    from pdfmeta.sign_table import check
    from pdfmeta.safe_math import assignment
    table={'axis':'x','function_label':'f','intervals':[{'left':'0','right':'log(5)','source_sign':'+'}],
           'point_values':[]}
    assert check(table,assignment("f'(x)=x+1"))['status']=='PASS'
    table['intervals'][0]['right']='m'
    assert check(table,assignment("f'(x)=x+1"))['status']=='NOT_ASSESSED'


def small_pdf(path,lines):
    def literal(text):return text.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
    stream=('BT /F1 12 Tf 40 750 Td '+' 0 -24 Td '.join('('+literal(s)+') Tj' for s in lines)+' ET').encode('cp1252')
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
        b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    result=b'%PDF-1.4\n';offsets=[0]
    for n,obj in enumerate(objects,1):offsets.append(len(result));result+=f'{n} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref=len(result);result+=f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
    result+=b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets[1:])
    result+=f'trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
    path.write_bytes(result)


def fake_ocr(monkeypatch):
    import pdfmeta.pdf_workflow as workflow
    class Adapter:
        def __init__(self,runtime,output,event):
            self.output=output;self.calls=0;self.cache_hits=0;self.packages={'unit_test_adapter':True}
        def weights(self,names):return {}
        def imported_formulas(self,*args):return []
        def formula_page(self,page,*args):
            self.calls+=1
            return dict(page_number=page['page_number'],parser_id='PP-FormulaNet_plus-S',blocks=[])
    monkeypatch.setattr(workflow,'LocalOCR',Adapter)
    return workflow


def test_new_pdf_and_renamed_copy_share_a_job_and_resume_without_model_calls(tmp_path,monkeypatch):
    workflow=fake_ocr(monkeypatch)
    pdf=tmp_path/'new.pdf';small_pdf(pdf,['Câu 7. Compute the derivative of a simple function for this local test.',
        'Solution','Answer: 2',"f(x)=x^2", "f'(x)=2x"])
    kwargs=dict(repo=tmp_path,output_root=tmp_path/'outputs',runtime=tmp_path/'runtime')
    first=workflow.run(pdf,**kwargs)
    renamed=tmp_path/'renamed.pdf';renamed.write_bytes(pdf.read_bytes())
    second=workflow.run(renamed,**kwargs)
    assert first['job_directory']==second['job_directory']
    assert first['question_count']==1 and second['stage_cache_hits']==5
    assert second['local_inference_calls']==0 and second['cloud_api_calls']==0
    assert Path(first['job_directory'],'input.pdf').read_bytes()==pdf.read_bytes()


def test_repeated_question_numbers_keep_unique_ids_and_student_preview_private(tmp_path,monkeypatch):
    workflow=fake_ocr(monkeypatch)
    pdf=tmp_path/'chapters.pdf';small_pdf(pdf,['Câu 1. First independent question with enough printed text.',
        'Solution','Answer: 2','The first explanation is deliberately separate.',
        'Câu 1. Another chapter restarts its question numbering here.',
        'Solution','Answer: 3','The second explanation is deliberately separate.'])
    report=workflow.run(pdf,repo=tmp_path,output_root=tmp_path/'jobs',runtime=tmp_path/'runtime')
    root=Path(report['output_directory']);items=[json.loads(s) for s in (root/'metadata/questions.jsonl').read_text().splitlines()]
    assert len(items)==2 and len({i['question_id'] for i in items})==2
    previews=[json.loads(s) for s in (root/'metadata/student-preview.jsonl').read_text().splitlines()]
    assert all('source_answer' not in p and 'reference_solution' not in p for p in previews)
    assert all(i['grading_support']=='NOT_ASSESSED' and i['publishable'] is False for i in items)


def test_document_without_question_markers_retains_page_metadata(tmp_path,monkeypatch):
    workflow=fake_ocr(monkeypatch)
    pdf=tmp_path/'theory.pdf';small_pdf(pdf,['A reference chapter with prose and no numbered question markers.',
                                          'All text remains accessible as source-grounded page metadata.'])
    report=workflow.run(pdf,repo=tmp_path,output_root=tmp_path/'jobs',runtime=tmp_path/'runtime')
    assert report['status']=='PAGE_METADATA_ONLY' and report['question_count']==0
    assert Path(report['output_directory'],'metadata/pages.jsonl').is_file()


def test_complete_document_workflow_keeps_source_book_inner_label_in_one_question(tmp_path,monkeypatch):
    workflow=fake_ocr(monkeypatch)
    pdf=tmp_path/'book.pdf';small_pdf(pdf,['Cau 007','Bai 25 | TL a2878305 | Trang nguon 19, 20',
        'Bai 25. A printed exercise with enough native text to skip text OCR.',
        'Giai','The full printed proof belongs to this source-book entry.'])
    result=workflow.run(pdf,repo=tmp_path,output_root=tmp_path/'jobs',runtime=tmp_path/'runtime')
    assert result['question_count']==1
    item=json.loads(Path(result['artifacts']['metadata_jsonl']).read_text(encoding='utf-8'))
    assert item['source_number']==7
    assert 'Bai 25.' in item['student_view']['stem_text_lossy']
    assert 'full printed proof' in item['reference_solution']['raw_text']


@pytest.mark.parametrize('raw,kind',[('Li gii','SOLUTION'),('Li giái','SOLUTION'),('Lời giải','SOLUTION'),('Trá li','RESPONSE'),
    ('Giài','SOLUTION'),('Giåi','SOLUTION'),('Gii','SOLUTION'),('Giải','SOLUTION')])
def test_ocr_whole_line_section_hints_keep_the_original_wording(raw,kind):
    from pdfmeta.section_markers import hint
    assert hint(raw)['kind']==kind
    assert hint(raw)['status']=='OCR_SECTION_HINT_REQUIRES_SOURCE_REVIEW'


@pytest.mark.parametrize('raw',['x = 1','lời giải của bài toán này','tôi giải','f(x)','gain','gai','gii = 2'])
def test_section_hint_is_not_inferred_from_math_or_prose(raw):
    from pdfmeta.section_markers import hint
    assert hint(raw) is None


@pytest.mark.parametrize('label',['Li gii','Giài','Giåi','Gii'])
def test_scanned_solution_marker_never_moves_the_solution_into_the_stem(label):
    from copy import deepcopy
    from pdfmeta.auto_ocr import apply_section_hints
    from pdfmeta.assemble import assemble
    texts=['Câu 901. Tính đạo hàm của hàm số này.',label,'Đáp án: 2x',"Ta có y' = 2x"]
    page={'page_number':1,'width':600,'height':800,'content_bounds':[0,0,600,800],
          'blocks':[{'block_id':str(i),'text_raw':t,'bbox':[20,50+i*30,550,65+i*30],
                     'review_flags':['OCR_TEXT_NOT_SOURCE_VERIFIED'],'glyphs':[]} for i,t in enumerate(texts)]}
    original=deepcopy(page)
    items,_=assemble([apply_section_hints(page)],'a'*64)
    assert "y' = 2x" not in items[0]['stem']['text_raw']
    assert "y' = 2x" in items[0]['solution']['text_raw']
    assert 'OCR_SECTION_MARKER_INFERRED' in items[0]['review_flags']
    assert page==original
