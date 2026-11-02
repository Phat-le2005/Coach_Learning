"""Native formula refinement plus explicitly selected, small raster sign tables."""
from __future__ import annotations

import argparse
from collections import Counter
import io
from html import escape
import json
from pathlib import Path
import time
import sympy as sp
from jsonschema import Draft202012Validator

from PIL import Image,ImageOps

from .math_audit import run as audit_run
from .gemini_jobs import writer_lock
from .pilot_trial import snapshot
from .safe_math import UnsupportedMath, assignment
from .sign_table import analyze, structure, check
from .variation_table import structure as variation_structure,check as variation_check,check_values
from .table_glyphs import BoundaryGlyphs
from .step_segmentation import propose_steps
from .storage import configure_storage, file_hash, inference_versions, read_json, write_json, write_jsonl


def build_view(output,report,audits,tables):
    e = lambda text:escape(str(text),quote=True)
    cards = []
    for record in tables:
        table = record.get('table')
        body = f'<p class="muted">{e(record.get("reason","Ứng viên đã có cấu trúc; chưa duyệt học thuật."))}</p>'
        if table:
            body += '<table><tr><th>Khoảng '+e(table['axis'])+'</th><th>Dấu từ ảnh</th><th>Chiều biến thiên từ ảnh</th></tr>'
            body += ''.join(f'<tr><td>({e(i["left"])}; {e(i["right"])})</td><td>{e(i.get("source_sign","Không ghi ở bảng"))}</td><td>{e({"INCREASING":"↗ Tăng","DECREASING":"↘ Giảm"}.get(i.get("direction"),"Chỉ có hàng dấu"))}</td></tr>' for i in table['intervals'])
            body += '</table>'
            if table['point_values']:
                body += '<p>Đạo hàm = 0 tại '+', '.join(e(p['at']) for p in table['point_values'])+'</p>'
            if table.get('function_values'):
                body += '<p>Giá trị hàm từ ảnh: '+', '.join(e(table['function_label'])+'('+e(v['at'])+') = '+e(v['value']) for v in table['function_values'])+'</p>'
            if table.get('blocked_regions'):
                body += '<p class="muted">Có vùng gạch chéo được giữ riêng theo ảnh; chưa diễn giải thành điều kiện đại số.</p>'
            if table.get('quality_flags'):
                body += '<details><summary>Cờ cần đối chiếu</summary><pre>'+e('\n'.join(table['quality_flags']))+'</pre></details>'
            body += '<details><summary>Kiểm tra dấu bằng công thức</summary><pre>'+e(json.dumps(record['formula_checks'],ensure_ascii=False,indent=2))+'</pre></details>'
        cards.append(f'<section><h2>Câu {record["source_number"]} · {e(record["status"])}</h2><div class="columns"><div>{body}</div><div><p>Ảnh nguồn · trang {record["page_number"]} · 240 DPI</p><img src="{e(record["asset_path"])}" alt="Bảng nguồn câu {record["source_number"]}"></div></div></section>')
    formulas = []
    for audit in audits:
        native = audit.get('source_definitions',[])+[c for s in audit['steps'] for g in s['formula_groups'] for c in g['alternatives'] if c['parser_id'].startswith(('native-baseline-math/','native-fraction-tree/'))]
        if native:
            formulas.append(f'<details><summary>Câu {audit["source_number"]} · {len(native)} ứng viên từ glyph PDF</summary>'+''.join(
                f'<pre>{e(c["latex"])}</pre><p class="muted">Trang {c["page_number"]} · {e(c["source_block_id"])} · {len(c.get("superscript_evidence",[]))} ký tự số mũ · {len(c.get("fraction_evidence",[]))} đường phân số có bằng chứng hình học · {e(c.get("derivation_scope","Công thức ứng viên"))}</p>' for c in native)+'</details>')
    m=report['math']
    html=f'''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Phục hồi công thức và bảng dấu</title><style>body{{margin:0;background:#f2f6fa;color:#21354c;font:15px/1.6 system-ui,sans-serif}}main{{max-width:1160px;margin:32px auto;padding:0 24px}}h1{{font-size:28px}}section,details{{background:white;border:1px solid #d9e3ed;border-radius:12px;padding:18px;margin:14px 0}}summary{{cursor:pointer;font-weight:600}}h2{{font-size:18px}}.columns{{display:grid;grid-template-columns:1fr 1.3fr;gap:24px}}.notice{{padding:18px;background:#fff3d4;border:1px solid #eed395;border-radius:10px}}.muted{{color:#5a6e82}}img{{max-width:100%;height:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #d9e3ed;padding:8px;text-align:left}}a{{color:#087b6d}}@media(max-width:750px){{.columns{{display:block}}}}</style>
<main><h1>Phục hồi công thức và bảng dấu</h1><p>{m['page_count']} trang · {m['question_count']} câu · {m['native_geometry_candidates']} công thức ứng viên từ glyph · {m['questions_with_supported_checks']} câu có phép kiểm đạo hàm được hỗ trợ.</p>
<div class="notice">Đây là bản thử có nguồn. Kết quả khớp đại số có điều kiện theo cách đọc công thức; chưa xác nhận toàn lời giải hoặc đáp án, chưa dùng chấm điểm.</div>
<p><a href="layout-report.json">Báo cáo</a> · <a href="tables.pretty.json">Metadata bảng</a> · <a href="questions.math-audit.pretty.json">Metadata công thức</a></p>
<p>Đính chính câu 161: dấu cộng có nét dọc rất mảnh. Crop 240 DPI cho thấy bảng + 0 −; rút lại nhận xét cũ về hai dấu âm.</p>
{''.join(cards)}<h2>Công thức phục hồi từ PDF</h2>{''.join(formulas)}</main></html>'''
    (output/'review.html').write_text(html,encoding='utf-8')


def regions(source, pages):
    result = []
    for step in propose_steps(source, pages)["steps"]:
        if step["kind_candidate"] != "SIGN_TABLE":
            continue
        for span in step["context_spans"]:
            boxes = [i["bbox"] for i in pages[span["page_number"]]["images"]
                     if span["bbox"][1] <= i["bbox"][1] < i["bbox"][3] <= span["bbox"][3]]
            # Join adjacent raster strips only. Separate illustrations remain separate.
            groups = []
            for box in sorted(boxes,key=lambda b:(b[1],b[0])):
                if groups and abs(box[0]-groups[-1][0]) < 1 and abs(box[2]-groups[-1][2]) < 1 and box[1]-groups[-1][3] < 1:
                    groups[-1][3] = max(groups[-1][3],box[3])
                else:
                    groups.append(list(box))
            for box in groups:
                result.append({"step_id":step["step_id"],"page_number":span["page_number"],"bbox":box})
    return result


def evaluate(table, audit):
    matches = []
    for step in audit["steps"]:
        if step["kind"] != "DERIVATIVE_CALCULATION":
            continue
        for group in step["formula_groups"]:
            for candidate in group["alternatives"]:
                try:
                    parsed = assignment(candidate["latex"])
                    if not parsed["chain_consistent"] or parsed["derivative_order"] != 1:
                        continue
                    result = variation_check(table,parsed) if table.get('algorithm','').startswith('raster-variation') else check(table,parsed)
                except (UnsupportedMath,ValueError,TypeError,NotImplementedError):
                    continue
                if result["status"] != "NOT_ASSESSED":
                    matches.append({"formula_latex":candidate["latex"],"source_block_id":candidate["block_id"],
                                    "canonical_selected":group["selected_latex"] is not None,**result})
    base_candidates=list(audit.get('source_definitions',[]))
    base_candidates += [c for s in audit['steps'] if s['kind'] in {'MODEL_SETUP','UNCLASSIFIED'} for g in s['formula_groups'] for c in g['alternatives']]
    for candidate in base_candidates:
        try:
            base=assignment(candidate['latex'])
            if base['derivative_order'] or not base['chain_consistent'] or base['label']!=table['function_label']:
                continue
            variable=sp.Symbol(table['axis'])
            if base['expression'].free_symbols-{variable}:
                continue
            derivative={**base,'variable':table['axis'],'derivative_order':1,'expression':sp.diff(base['expression'],variable)}
            result=variation_check(table,derivative) if table.get('algorithm','').startswith('raster-variation') else check(table,derivative)
            if result['status']!='NOT_ASSESSED':
                matches.append({'formula_latex':candidate['latex'],'source_block_id':candidate['block_id'],
                    'basis':'SYMBOLIC_DERIVATIVE_OF_SOURCE_FUNCTION_NOT_A_TRANSCRIBED_DERIVATIVE',**result})
            if table.get('function_values'):
                values=check_values(table,base)
                if values['status']!='NOT_ASSESSED':
                    matches.append({'formula_latex':candidate['latex'],'source_block_id':candidate['block_id'],**values})
        except (UnsupportedMath,ValueError,TypeError,NotImplementedError):
            continue
    return matches


def run(pilot, pdf, output, runtime, numbers, *, limit=3):
    source_root,target = pilot.resolve(),output.resolve()
    if target==source_root or source_root.is_relative_to(target) or any(target.is_relative_to(source_root/p) for p in ("pages","reviews","steps","exports")):
        raise ValueError("USE_A_SEPARATE_LAYOUT_OUTPUT_DIRECTORY")
    with writer_lock(target):
        return _run(pilot,pdf,target,runtime,numbers,limit=limit)


def _run(pilot, pdf, output, runtime, numbers, *, limit=3):
    if not 1 <= limit <= 10 or len(set(numbers)) != len(numbers):
        raise ValueError("BOUNDED_UNIQUE_TABLE_SELECTION_REQUIRED")
    pilot,pdf,output,runtime = (p.resolve() for p in (pilot,pdf,output,runtime))
    if output == pilot or pilot.is_relative_to(output) or any(output.is_relative_to(pilot/p) for p in ("pages","reviews","steps","exports")):
        raise ValueError("USE_A_SEPARATE_LAYOUT_OUTPUT_DIRECTORY")
    configure_storage(runtime)
    before = snapshot(pilot,pdf)
    started = time.perf_counter()
    audits, math_report = audit_run(pilot,output,pdf=pdf)
    lookup = {a["source_number"]:a for a in audits}
    sources = {s["source_number"]:s for s in (json.loads(x) for x in (pilot/'questions.enriched.candidates.jsonl').read_text(encoding='utf-8').splitlines())}
    if set(numbers)-set(sources):
        raise ValueError("REQUESTED_QUESTION_NOT_FOUND")
    pages = {p["page_number"]:p for p in (read_json(f) for f in (pilot/'pages').glob('*.json'))}
    model_dir = runtime/'paddlex/official_models/PP-FormulaNet_plus-M'
    weights = model_dir/'inference.pdiparams'
    if not weights.exists():
        raise ValueError("LOCAL_FORMULA_MODEL_MISSING_RUN_EXPLICIT_OCR_SETUP")
    digest = file_hash(weights)
    packages = inference_versions()
    model, calls, hits = None, 0, 0
    def recognize(image):
        nonlocal model,calls,hits
        # Labels such as I, 0 and +infinity need whitespace and enough pixels.
        # This preprocessing is versioned in cache and never edits source assets.
        image=image.convert('RGB')
        if image.height<64:
            image=image.resize((image.width*2,image.height*2),Image.Resampling.LANCZOS)
        image=ImageOps.expand(image,border=12,fill='white')
        stream = io.BytesIO();image.save(stream,format='PNG')
        from hashlib import sha256
        key = sha256(stream.getvalue()+digest.encode()+json.dumps(packages,sort_keys=True).encode()+b'local-table-cell/v2').hexdigest()
        target = output/'cell-ocr'/f'{key}.json'
        image_path = output/'cell-ocr'/f'{key}.png'
        if target.exists():
            record = read_json(target)
            if record['crop_sha256'] != sha256(stream.getvalue()).hexdigest():
                raise ValueError("TABLE_CELL_CACHE_HASH_MISMATCH")
            hits += 1
            return record['latex']
        if model is None:
            from paddleocr import FormulaRecognition
            model = FormulaRecognition(model_name='PP-FormulaNet_plus-M',model_dir=str(model_dir),
                device='cpu',cpu_threads=3,enable_mkldnn=False)
        image_path.parent.mkdir(parents=True,exist_ok=True)
        image_path.write_bytes(stream.getvalue())
        tick = time.perf_counter()
        prediction = list(model.predict(str(image_path),batch_size=1))[0].json
        latex = prediction.get('res',prediction).get('rec_formula','')
        calls += 1
        write_json(target,{'latex':latex,'crop_sha256':file_hash(image_path),'model_weights_sha256':digest,
                           'packages':packages,
                           'seconds':round(time.perf_counter()-tick,3),'status':'OCR_CANDIDATE_NOT_VERIFIED'})
        return latex
    records = []
    table_validator=Draft202012Validator(read_json(Path(__file__).parents[1]/'schemas/math-table-candidate.v1.schema.json'))
    try:
        glyph_matcher=BoundaryGlyphs()
        label_matcher=BoundaryGlyphs(alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz',axis=True)
    except UnsupportedMath:
        glyph_matcher,label_matcher=None,None
    import pdfplumber
    with pdfplumber.open(pdf) as document:
        for number in numbers[:limit]:
            for index,region in enumerate(regions(sources[number],pages),1):
                path = output/'table-assets'/f'q{number}-{index}.png'
                path.parent.mkdir(parents=True,exist_ok=True)
                document.pages[region['page_number']-1].crop(tuple(region['bbox'])).to_image(resolution=240).save(path)
                record = {'source_number':number,'question_id':sources[number]['question_id'],
                    'source_sha256':math_report['source_sha256'],**region,'asset_path':str(path.relative_to(output)).replace('\\','/'),
                    'render_dpi':240,'crop_sha256':file_hash(path),'academic_review':'PENDING','publishable':False}
                try:
                    with Image.open(path) as image:
                        try:
                            analyze(image)
                            table = structure(image,recognize)
                        except UnsupportedMath as initial_error:
                            table = variation_structure(image,recognize,boundary_reader=glyph_matcher.read if glyph_matcher else None,
                                                        label_reader=label_matcher.read if label_matcher else None)
                    table_validator.validate(table)
                    record.update(status='STRUCTURED_CANDIDATE',table=table,formula_checks=evaluate(table,lookup[number]))
                except UnsupportedMath as error:
                    record.update(status='NEEDS_LAYOUT_REVIEW',reason=str(error))
                records.append(record)
                write_json(output/'tables.pretty.json',records)
                write_jsonl(output/'tables.jsonl',records)
                print(f"Table q{number}: {record['status']} {record.get('reason','')}",flush=True)
    after = snapshot(pilot,pdf)
    changed = sorted(k for k in before.keys()|after.keys() if before.get(k)!=after.get(k))
    report = {'schema_version':'layout-refinement-report/v1','source_sha256':math_report['source_sha256'],
        'math':math_report,'table_selected_numbers':numbers[:limit],'table_region_count':len(records),
        'table_status_counts':dict(Counter(r['status'] for r in records)),'table_model':'PP-FormulaNet_plus-M',
        'table_model_weights_sha256':digest,'table_cell_inference_calls':calls,'table_cell_cache_hits':hits,
        'packages':packages,
        'cloud_api_calls':0,'seconds':round(time.perf_counter()-started,3),
        'source_integrity':{'checked_files':len(before),'changed_files':changed},
        'academic_approved_count':0,'grading_ready_count':0,'publishable_count':0}
    review_queue=[{'question_id':r['question_id'],'source_number':r['source_number'],
                   'page_number':r['page_number'],'bbox':r['bbox'],'reason':r.get('reason','CANDIDATE_TRANSCRIPTION_AND_MATH_NOT_ACADEMICALLY_APPROVED'),
                   'quality_flags':r.get('table',{}).get('quality_flags',[]),
                   'asset_path':r['asset_path']} for r in records]
    write_json(output/'review-queue.json',review_queue)
    write_json(output/'layout-report.json',report)
    build_view(output,report,audits,records)
    if changed:
        raise ValueError('SOURCE_CHANGED_DURING_LAYOUT_REFINEMENT')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('pilot','pdf','output','runtime'):
        parser.add_argument('--'+arg,type=Path,required=True)
    parser.add_argument('--questions',required=True)
    parser.add_argument('--limit',type=int,default=3)
    args = parser.parse_args()
    report = run(args.pilot,args.pdf,args.output,args.runtime,[int(n.strip()) for n in args.questions.split(',')],limit=args.limit)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
