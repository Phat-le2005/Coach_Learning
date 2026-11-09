from pathlib import Path

from pdfmeta.direct_pdf_content import publish_pages
from pdfmeta.direct_pdf_boundaries import crop_context, guard_tail
from pdfmeta.direct_pdf_regions import plan_visual_regions
from pdfmeta.storage import read_json


def export(tmp_path, pages):
    rows=[]
    for number, texts in pages:
        blocks=[dict(kind='TEXT',bbox=[0,0,200,100],source_image='assets/source.png',
                     source_image_sha256='b'*64,status='OK',markdown=text) for text in texts]
        rows.append(dict(page_number=number,regions=[dict(region_number=1,blocks=blocks)],
                         native_text_from_this_pdf='',markdown='\n\n'.join(texts)))
    publish_pages(tmp_path,rows,dict(name='input.pdf',sha256='a'*64))
    return read_json(tmp_path/'content.draft.pretty.json')


def test_answer_in_solution_does_not_consume_explanatory_steps(tmp_path):
    rows=export(tmp_path,[(1,['Câu 1. Tính tọa độ.\nLời giải\nĐáp án: 16,5\nPhương trình tọa độ là:\n$x(t)=t^3+2t^2+C$.\nCâu 2. Câu tiếp theo.'])])
    assert len(rows)==2
    assert rows[0]['answer']['markdown']=='Đáp án: 16,5'
    assert 'Phương trình tọa độ' in rows[0]['solution']['markdown']
    assert '$x(t)=t^3+2t^2+C$' in rows[0]['solution']['markdown']
    assert rows[1]['solution']['markdown']==''


def test_solution_resumes_across_crops_and_consecutive_pages_without_new_question(tmp_path):
    rows=export(tmp_path,[(1,['Câu 1. Nội dung đầu', 'tiếp tục đề.\nLời giải\nĐáp án: 2']),
                          (2,['Tính nguyên hàm để được $x=2$.', 'Câu 2. Nội dung mới'])])
    assert len(rows)==2 and 'tiếp tục đề' in rows[0]['question']['markdown']
    assert rows[0]['answer']['markdown']=='Đáp án: 2'
    assert 'Tính nguyên hàm' in rows[0]['solution']['markdown']
    assert [r['source_number'] for r in rows]==[1,2]


def test_answer_keys_stay_together_and_no_solution_is_invented(tmp_path):
    rows=export(tmp_path,[(1,['Câu 1. Xét đúng sai.\nGiải\nĐáp án: a) Đúng',
                            'b) Sai\nc) Đúng\nd) Sai\n\nGiải thích theo nguồn.',
                            'Câu 2. Chọn đáp án.\nĐáp án: A'])])
    assert 'd) Sai' in rows[0]['answer']['markdown']
    assert 'Giải thích theo nguồn' in rows[0]['solution']['markdown']
    assert rows[1]['solution']['markdown']==''


def test_page_gap_does_not_reuse_solution_context(tmp_path):
    rows=export(tmp_path,[(1,['Câu 1. Đề.\nGiải\nĐáp án: A']),
                          (3,['Không có nhãn câu.\nCâu 2. Đề mới.'])])
    assert len(rows)==2 and 'Không có nhãn' not in rows[0]['solution']['markdown']


def test_crop_planner_keeps_a_question_paragraph_together():
    from PIL import Image,ImageDraw
    image=Image.new('RGB',(400,700),'white');draw=ImageDraw.Draw(image)
    for y in range(10,690,20):draw.rectangle((10,y,380,y+6),fill='black')
    bands=[[0,250,400,450]]
    nodes=plan_visual_regions(image,[],72,question_bands=bands)
    assert len(nodes)>1
    assert all(not (250<n['bbox'][1]<450 or 250<n['bbox'][3]<450) for n in nodes)


def test_visible_prose_tail_removes_invented_completion_but_retains_raw_text():
    profile={'blocks':[dict(bbox=[0,20,100,30],text_raw='quãng đường đi được của vật đều')]}
    context=crop_context(profile,[0,0,110,32])
    raw='Câu 2. Quãng đường đi được của vật đều bằng 0. Tính trong t∈[0,2].'
    row=guard_tail(dict(markdown=raw,raw_markdown=raw,flags=[],errors=[],uncertain=False),context)
    assert row['markdown'].endswith('của vật đều')
    assert row['raw_markdown']==raw and row['status']=='REVIEW_REQUIRED'
    assert row['boundary_audit']['status']=='UNSUPPORTED_CONTINUATION_REMOVED'


def test_unalignable_or_formula_tail_is_not_rewritten():
    base=dict(markdown='Visible $x^2$ and text.',flags=[],errors=[],uncertain=False)
    context={'tail_anchor':'bốn từ nguồn không khớp','tail_anchor_bbox':[0,0,1,1]}
    assert guard_tail(base,context)['markdown']==base['markdown']
    assert 'SOURCE_CROP_TAIL_REVIEW_REQUIRED' in guard_tail(base,context)['flags']
    formula={'blocks':[dict(bbox=[0,0,100,10],text_raw='x(t) = 2t + C')]}
    assert 'tail_anchor' not in crop_context(formula,[0,0,100,11])


def test_performance_logs_distinguish_cache_and_measure_full_request_latency(tmp_path):
    from pdfmeta.direct_pdf_metrics import PerformanceLog
    with PerformanceLog(tmp_path,Path('unused'),sample=False) as metrics:
        with metrics.stage('export'):
            pass
        metrics.request('text',lambda:dict(status='RESPONSE_RECEIVED',usage=dict(promptTokenCount=30,candidatesTokenCount=10)))
        result=metrics.finish(counts={'processed_pages':2,'questions':4,'cache_hits_this_run':1})
    assert result['model_requests']==1 and result['output_tokens']==10
    assert result['execution_mode']=='INFERENCE' and result['pages_per_minute']>0
    assert result['resources']['gpu_peak_utilization_percent'] is None
    assert read_json(tmp_path/'ocr-performance.json')['run_id']==result['run_id']
    with PerformanceLog(tmp_path,Path('unused'),sample=False) as metrics:
        cached=metrics.finish(counts={'processed_pages':2,'questions':4,'cache_hits_this_run':2})
    assert cached['execution_mode']=='CACHE_OR_NO_INFERENCE' and cached['model_requests']==0
    assert cached['output_tokens_per_request_second'] is None


def test_failed_request_preserves_a_failed_run_log_without_unknown_token_rate(tmp_path):
    import pytest
    from pdfmeta.direct_pdf_metrics import PerformanceLog
    def fail():
        raise RuntimeError('fixture request failed')
    with pytest.raises(RuntimeError):
        with PerformanceLog(tmp_path,Path('unused'),sample=False) as metrics:
            with metrics.stage('region'):
                metrics.request('text',fail)
    report=read_json(tmp_path/'ocr-performance.json')
    assert report['status']=='FAILED' and report['model_requests']==1
    assert report['requests_with_token_usage']==0 and report['output_tokens_per_request_second'] is None
