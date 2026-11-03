"""Evaluate operational coverage separately from source-transcription accuracy."""
from collections import Counter
from html import escape
import json
from pathlib import Path

from ..storage import file_hash,read_json,write_json


def evaluate(queue_path,*,manifest=None):
    queue_path=Path(queue_path).resolve();queue=read_json(queue_path);results=[]
    expected=read_json(Path(manifest)) if manifest else {};labels={r['sha256']:r for r in expected.get('documents',[])}
    for entry in queue['items']:
        if entry['status']!='COMPLETED':
            results.append({'source':Path(entry['pdf']).name,'status':entry['status'],'error':entry.get('error')});continue
        hashes=entry.get('result_hashes',{})
        if not hashes or any(not Path(p).is_file() or file_hash(Path(p))!=h for p,h in hashes.items()):
            results.append({'source':Path(entry['pdf']).name,'status':'STALE_RESULT','error':'A later run changed the referenced reports; evaluate its queue instead.'});continue
        job=Path(entry['result']['job']);latest=read_json(job/'latest.json');final=read_json(job/'final.json')
        rows=[json.loads(s) for s in Path(final['final_jsonl']).read_text(encoding='utf-8').splitlines() if s.strip()]
        core=read_json(job/'core-package.json');image=read_json(job/'image-check.json')
        numbers=[r['source_metadata']['source_number'] for r in rows]
        steps=[s for r in rows for s in r['source_metadata']['reference_solution']['steps']]
        label=labels.get(entry['sha256'],{});gold=label.get('expected_source_numbers')
        coverage={'expected':len(gold),'found':len(set(gold)&set(numbers)),'missing':sorted(set(gold)-set(numbers)),
                  'extra':sorted(set(numbers)-set(gold))} if gold is not None else None
        results.append({'source':Path(entry['pdf']).name,'sha256':entry['sha256'],'job':str(job),
            'input_pages':entry['pages'],'processed_pages':latest['report']['page_count'],
            'routes':latest['report']['routes'],'questions':len(rows),'steps':len(steps),
            'status':final['status'],'question_ids_unique':len({r['question_id'] for r in rows})==len(rows),
            'source_unchanged':file_hash(Path(entry['pdf']))==entry['sha256'],
            'candidate_flag_counts':dict(Counter(f for r in rows for f in r['source_metadata'].get('quality_flags',[]))),
            'image_status_counts':image['status_counts'],'image_scope':[image['selected_regions'],image['regions_found']],
            'provisional_checkers':core['provisional_checkers'],'grading_ready_count':core['grading_ready_count'],
            'question_marker_coverage':coverage,'transcription_accuracy':None,'seconds':entry.get('seconds'),
            'sampled_peak_ram_mb':entry['result'].get('sampled_peak_ram_mb'),
            'evaluation_kind':label.get('kind','UNLABELLED_OPERATIONAL_SMOKE')})
    report={'schema_version':'pdf-diversity-evaluation/v1','queue':str(queue_path),'documents':results,
        'documents_attempted':sum(r.get('status')!='PENDING' for r in results),
        'operational_failures':sum(r['status'] in {'FAILED','INTERRUPTED'} for r in results),
        'all_completed_sources_unchanged':all(r.get('source_unchanged',True) for r in results),
        'scope':'STRUCTURAL_COVERAGE_AND_RESOURCE_SMOKE_NOT_WHOLE_CORPUS_GRADING_ACCURACY',
        'production_ready':False}
    target=queue_path.parent/'evaluation.json';write_json(target,report)
    e=lambda s:escape(str(s),quote=True)
    cards=''.join('<tr>'+''.join('<td>'+e(r.get(k,'—'))+'</td>' for k in ['source','evaluation_kind','status','processed_pages','questions','steps','seconds','sampled_peak_ram_mb'])+'</tr>' for r in results)
    (queue_path.parent/'evaluation.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đánh giá đa tài liệu</title><style>body{font:14px/1.6 system-ui;background:#f3f7f6;color:#183641;padding:24px}table{border-collapse:collapse;width:100%;background:white}td,th{border:1px solid #d5e3dc;padding:12px;text-align:left;overflow-wrap:anywhere}td:first-child{max-width:340px}</style><h1>Kiểm tra trên nhiều PDF</h1><p>Đây là đo khả năng vận hành, tách câu/bước và tài nguyên. Chỉ số chính xác nhận dạng cần nhãn nguồn độc lập; không lấy số công thức parse được làm độ chính xác.</p><table><tr><th>Tài liệu</th><th>Loại mẫu</th><th>Trạng thái</th><th>Trang</th><th>Câu</th><th>Bước</th><th>Giây</th><th>RAM đỉnh lấy mẫu MB</th></tr>'+cards+'</table>',encoding='utf-8')
    return {'report':str(target),'review':str(queue_path.parent/'evaluation.html'),**report}
