"""Offline, validation-only error review. No model execution or W&B run is created."""
import argparse
import base64
from collections import defaultdict
import csv
from datetime import datetime,timezone
import hashlib
import html
from io import StringIO
import json
from pathlib import Path
import zipfile


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def metadata_path(data):
    data=Path(data)
    paths=[data] if data.is_file() else sorted(data.rglob('metadata.json'))
    if len(paths)!=1:raise ValueError('Set --data to the exact dataset folder or metadata.json.')
    return paths[0].resolve()


def review(output,data=None,epoch=None,overwrite=False):
    output=Path(output).resolve()
    cfg=json.loads((output/'config.json').read_text(encoding='utf-8'))
    summary=json.loads((output/'summary.json').read_text(encoding='utf-8'))
    epoch=int(epoch if epoch is not None else summary['selected_best']['epoch'])
    if epoch<1:raise ValueError('Expected a completed training epoch.')
    stem=f'validation-review-e{epoch:03}'
    paths={suffix:output/(stem+'.'+suffix) for suffix in ('json','csv','html','zip')}
    if any(p.exists() for p in paths.values()) and not overwrite:
        raise FileExistsError('Review already exists. Open the saved files; --overwrite replaces manual CSV notes.')
    metadata=metadata_path(data or cfg['data'])
    audit=json.loads((output/'dataset-audit.json').read_text(encoding='utf-8'))
    if audit['metadata_sha256']!=digest(metadata):raise ValueError('REVIEW_DATASET_CHANGED')
    rows=json.loads(metadata.read_text(encoding='utf-8'))
    validation={r['id']:r for r in rows if r['split']=='validation'}
    predictions=json.loads((output/f'validation-{epoch:03}.json').read_text(encoding='utf-8'))
    preds=predictions['predictions'];ids=[p['id'] for p in preds]
    if not preds or len(ids)!=len(set(ids)) or not set(ids)<=set(validation):
        raise ValueError('REVIEW_EXPECTS_UNIQUE_VALIDATION_SAMPLES_ONLY')
    if not summary.get('qa_only') and set(ids)!=set(validation):raise ValueError('REVIEW_VALIDATION_INCOMPLETE')
    if predictions['metrics']['samples']!=len(preds):raise ValueError('REVIEW_SAMPLE_COUNT_MISMATCH')
    groups=defaultdict(lambda:{'samples':0,'correct':0})
    wrong=[]
    manifest={r['id']:r for r in json.loads((output/'dataset-manifest.json').read_text(encoding='utf-8'))}
    for pred in preds:
        row=validation[pred['id']]
        if pred['latex']!=row['latex']:raise ValueError('REVIEW_LABEL_CHANGED')
        if type(pred['exact']) is not bool:raise ValueError('REVIEW_EXACT_FLAG_INVALID')
        group=pred['group'];groups[group]['samples']+=1;groups[group]['correct']+=int(pred['exact'])
        if pred['exact']:continue
        relative=row['image_path'];image=(metadata.parent/relative).resolve()
        if Path(relative).is_absolute() or not image.is_relative_to(metadata.parent):raise ValueError('REVIEW_IMAGE_PATH_ESCAPE')
        if image.suffix.lower() not in ('.jpg','.jpeg'):raise ValueError('REVIEW_EXPECTS_ORIGINAL_JPEG')
        raw=image.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=manifest[pred['id']]['image_sha256']:raise ValueError('REVIEW_IMAGE_CHANGED')
        wrong.append({**pred,'image_path':relative,'_image_bytes':raw})
    correct=sum(int(p['exact']) for p in preds)
    if abs(correct/len(preds)-predictions['metrics']['exp_rate'])>1e-8:raise ValueError('REVIEW_METRIC_MISMATCH')
    wrong.sort(key=lambda p:(-p['cer'],-p['token_edits'],p['id']))
    details=dict(epoch=epoch,qa_only=summary.get('qa_only',False),split='validation',samples=len(preds),
        correct=correct,incorrect=len(wrong),metrics=predictions['metrics'],groups=dict(groups),
        dataset_fingerprint=audit['fingerprint'],metadata_sha256=audit['metadata_sha256'],
        checkpoint_sha256=digest(output/'best.pt') if epoch==summary['selected_best']['epoch'] and (output/'best.pt').exists() else None,
        source_predictions=f'validation-{epoch:03}.json',created_utc=datetime.now(timezone.utc).isoformat(),
        note='Review causes manually. This report does not assert mathematical equivalence or change labels/checkpoints.')
    columns=['id','group','image_path','latex','prediction','cer','character_edits','token_edits','review_category','review_note']
    buffer=StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=columns);writer.writeheader()
    for pred in wrong:writer.writerow({k:pred.get(k,'') for k in columns})
    group_rows=''.join(f'<tr><td>{html.escape(g)}</td><td>{v["samples"]}</td><td>{v["correct"]}</td>'
        f'<td>{v["samples"]-v["correct"]}</td></tr>' for g,v in sorted(groups.items()))
    cards=[]
    for i,pred in enumerate(wrong,1):
        image=base64.b64encode(pred['_image_bytes']).decode('ascii')
        cards.append(f'<article><h2>{i:02}. {html.escape(pred["id"])} · {html.escape(pred["group"])}</h2>'
            f'<img alt="Original JPEG {html.escape(pred["id"],quote=True)}" src="data:image/jpeg;base64,{image}">'
            f'<div class="pair"><div><b>Nhãn gốc</b><pre>{html.escape(pred["latex"])}</pre></div>'
            f'<div><b>Dự đoán</b><pre>{html.escape(pred["prediction"])}</pre></div></div>'
            f'<p>CER: {pred["cer"]:.4f} · Character edits: {pred["character_edits"]} · Token edits: {pred["token_edits"]}</p>'
            '<p class="hint">Phân loại trong CSV: symbol / latex_format / label_check / crop_quality / other. '
            'Đối chiếu ảnh trước khi kết luận nguyên nhân.</p></article>')
    qa=' · QA ONLY' if details['qa_only'] else ''
    document='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Coach Learning · Validation review</title><style>
body{font:16px/1.5 system-ui,sans-serif;background:#f1f5f9;color:#172033;margin:0}main{max-width:1100px;margin:32px auto;padding:0 20px}
header,article{background:white;padding:24px;border-radius:12px;margin-bottom:20px;border:1px solid #d8e1eb}
h1{font-size:25px;margin-top:0}h2{font-size:18px}table{border-collapse:collapse;width:100%;margin-top:16px}
td,th{padding:9px;text-align:left;border-bottom:1px solid #d8e1eb}th{background:#eef4fa}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}
img{max-width:100%;max-height:340px;object-fit:contain;display:block;margin:18px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6fa;padding:12px;border-radius:6px}
.hint{color:#526174;font-size:14px}@media(max-width:650px){.pair{grid-template-columns:1fr}header,article{padding:16px}}
</style><main>'''
    document+=f'<header><h1>CoMER · Validation epoch {epoch}{qa}</h1><p><b>{correct}/{len(preds)} đúng hoàn toàn · {len(wrong)} ảnh cần xem lại</b></p>'
    document+='<p>Ảnh JPG nguyên gốc được nhúng theo đúng byte; nhãn và dự đoán hiển thị dạng văn bản. '
    document+='Không dùng tập test trong báo cáo này. Chuỗi prediction của các run cũ là token ghép để tính CER; chưa phải bằng chứng tương đương toán học.</p>'
    document+='<table><thead><tr><th>Nhóm</th><th>Tổng</th><th>Đúng</th><th>Cần xem</th></tr></thead><tbody>'+group_rows+'</tbody></table></header>'
    document+=''.join(cards)+'</main></html>'
    payloads={'json':json.dumps(details,ensure_ascii=False,indent=2)+'\n','csv':buffer.getvalue(),'html':document}
    for suffix,text in payloads.items():
        pending=paths[suffix].with_suffix('.'+suffix+'.tmp')
        pending.write_text(text,encoding='utf-8',newline='');pending.replace(paths[suffix])
    pending=paths['zip'].with_suffix('.zip.tmp')
    with zipfile.ZipFile(pending,'w',zipfile.ZIP_DEFLATED) as archive:
        for suffix in payloads:archive.write(paths[suffix],paths[suffix].name)
        archive.writestr('checksums.json',json.dumps({paths[s].name:digest(paths[s]) for s in payloads},indent=2))
    pending.replace(paths['zip'])
    return details,paths


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--data',help='Optional relocated dataset folder or exact metadata.json')
    p.add_argument('--epoch',type=int);p.add_argument('--overwrite',action='store_true');a=p.parse_args()
    details,paths=review(a.output,a.data,a.epoch,a.overwrite)
    print(f"Validation epoch {details['epoch']}: {details['correct']}/{details['samples']} exact, {details['incorrect']} to review.")
    for name,path in paths.items():print(name.upper()+':',path)


if __name__=='__main__':main()
