from html import escape
import json
from pathlib import Path


SCENARIOS={'source_checked_work':'Bài làm đã đối chiếu với nguồn','equivalent_derivative':'Đạo hàm viết dạng tương đương',
 'wrong_derivative_sign':'Sai dấu khi tính đạo hàm','wrong_power':'Sai số mũ','wrong_final':'Sai kết quả cuối',
 'missing_derivative':'Thiếu bước tính đạo hàm','missing_critical_points':'Thiếu bước tìm nghiệm',
 'final_answer_only':'Chỉ ghi đáp án cuối','missing_domain':'Thiếu miền xét','wrong_domain':'Nêu sai miền xét',
 'cancelled_factor_new_hole':'Rút gọn làm phát sinh điểm không xác định','unsupported_expression':'Biểu thức ngoài phạm vi bộ kiểm',
 'reordered_claims':'Đổi thứ tự trình bày vẫn đúng','source_conflict_correct_work':'Bài làm đúng nhưng nguồn có mâu thuẫn',
 'source_conflict_wrong_work':'Bài làm sai và nguồn có mâu thuẫn',
 'valid_alternative_polynomial_division':'Cách giải đúng bằng chia đa thức',
 'valid_alternative_rational_critical_ratio':'Cách giải đúng bằng tỉ số đạo hàm',
 'wrong_alternative_division':'Sai đẳng thức chia đa thức','wrong_alternative_rule':'Dùng sai hệ thức tại cực trị',
 'wrong_alternative_line':'Cách giải khác nhưng sai đường thẳng kết luận'}
STATUSES={'PASS':'Đạt','FAIL':'Sai','MISSING':'Chưa có bước này','NOT_ASSESSED':'Chưa đánh giá',
 'COMPLETE_SANDBOX_ASSESSMENT':'Đã kiểm theo rubric thử nghiệm','NEEDS_REVIEW':'Cần đối chiếu thêm',
 'HELD_SOURCE_CONFLICT':'Giữ lại vì mâu thuẫn nguồn'}
REASONS={'DOMAIN_MATCH':'Miền xét khớp','DOMAIN_MISMATCH':'Miền xét chưa khớp',
 'DOMAIN_NOT_PROVIDED':'Chưa cung cấp miền xét','DOMAIN_GATE_NOT_SATISFIED':'Cần xác định đúng miền trước',
 'SYMBOLIC_IDENTITY_CHECK':'So sánh biểu thức và điểm không xác định',
 'FUNCTION_OR_DERIVATIVE_LABEL_MISMATCH':'Tên hàm hoặc bậc đạo hàm không khớp',
 'NEW_UNDEFINED_POINT_IN_STEP_DOMAIN':'Cách viết làm mất một điểm thuộc miền cần xét',
 'CRITICAL_SET_MATCH':'Đối chiếu tập nghiệm đạo hàm trong miền',
 'INCREASING_INTERVALS_MATCH':'Đối chiếu các khoảng đồng biến',
 'EXTREMA_COORDINATES_MATCH':'Đối chiếu tọa độ các điểm cực trị',
 'EXACT_GEOMETRY_VALUE_MATCH':'Đối chiếu giá trị hình học chính xác',
 'FINAL_VALUE_AND_ROUNDING_CHECK':'Đối chiếu giá trị cuối và yêu cầu làm tròn',
 'STEP_NOT_SUBMITTED_NO_INFERRED_CREDIT':'Không tự suy ra bước còn thiếu để cộng điểm',
 'NONRATIONAL_FORMULA_UNSUPPORTED':'Bộ kiểm này chỉ hỗ trợ biểu thức hữu tỉ',
 'POLYNOMIAL_DIVISION_IDENTITY_CHECK':'Kiểm tra đẳng thức chia đa thức',
 'WRONG_QUOTIENT_CRITICAL_RULE':'Hệ thức sử dụng tại điểm cực trị chưa đúng'}
METHODS={'direct':'Đạo hàm, nghiệm và bước kết luận','polynomial_division':'Chia đa thức cho đạo hàm',
         'rational_critical_ratio':'Tỉ số đạo hàm tử và mẫu tại cực trị'}


def render(output,references,summary,*,cases=(),results=()):
    e=lambda value:escape(str(value),quote=True)
    cards=[];case_by_id={c['scenario_id']:c for c in cases}
    for reference in references:
        held=reference['eligibility']!='SANDBOX_REFERENCE_READY'
        rubric_tables=[]
        for method,criteria in reference['criteria_by_method'].items():
            rows=''.join('<tr><td>'+e(c['label'])+'</td><td>'+str(c['max_points'])+'</td><td><code>'+e(json.dumps(c['expected'],ensure_ascii=False))+'</code></td><td>'+str(len(c['source_alignment']['source_step_ids']))+'</td></tr>' for c in criteria)
            rubric_tables.append('<h3>'+e(METHODS.get(method,method))+'</h3><table><tr><th>Tiêu chí</th><th>Điểm tối đa</th><th>Kỳ vọng</th><th>Bước nguồn ghép được</th></tr>'+rows+'</table>')
        scenarios=[]
        for result in results:
            if result['question_id']!=reference['question_id']:continue
            outcome=result['outcome'];score='Chưa chấm' if outcome['score'] is None else str(outcome['score'])+'/10'
            detail=''.join('<tr><td>'+e(c['label'])+'</td><td>'+e(STATUSES.get(c['status'],c['status']))+'</td><td>'+e(c['points'] if c['points'] is not None else '—')+'/'+str(c['max_points'])+'</td><td title="'+e(c['reason'])+'">'+e(REASONS.get(c['reason'],c['reason']))+'</td></tr>' for c in outcome['criteria'])
            case=case_by_id[result['scenario_id']]
            scenarios.append('<details class="scenario" data-pass="'+str(result['assertion_passed']).lower()+'"><summary title="'+e(result['category'])+'">'+e(SCENARIOS.get(result['category'],result['category']))+' <b>'+score+'</b><span class="tag">'+('Đạt kỳ vọng kiểm thử' if result['assertion_passed'] else 'Lệch kỳ vọng')+'</span></summary><p>'+e(STATUSES.get(outcome['status'],outcome['status']))+' · Giới hạn điểm: '+str(outcome['score_lower_bound'])+'–'+str(outcome['score_upper_bound'])+'</p><p>Cách giải: '+e(METHODS.get(outcome.get('method'),outcome.get('method')))+'</p><table><tr><th>Tiêu chí</th><th>Phản hồi</th><th>Điểm thử</th><th>Lý do</th></tr>'+detail+'</table><details><summary>Đầu vào có cấu trúc</summary><pre>'+e(json.dumps(case['request'],ensure_ascii=False,indent=2))+'</pre></details>'+('<p>Một số kết quả sau khớp nhưng bước tiền đề còn thiếu hoặc sai. Điểm thử hiện tính từng tiêu chí độc lập; cần đối chiếu thêm mạch lập luận.</p>' if outcome.get('dependency_warnings') else '')+'</details>')
        images=''.join('<figure><figcaption>Trang PDF '+str(im['page_number'])+'</figcaption><img loading="lazy" src="'+e(im['path'])+'" alt="Ảnh đề và lời giải gốc"></figure>' for im in reference['source_images'])
        note='<p class="conflict">'+e(' · '.join(reference['source_issues']))+'</p>' if held else ''
        cards.append('<article data-number="'+str(reference['source_number'])+'" data-held="'+str(held).lower()+'"><header><div><small>BÀI TỪ PDF GỐC</small><h2>Câu '+str(reference['source_number'])+'</h2></div><span class="tag '+('amber' if held else '')+'">'+('Giữ lại: nguồn mâu thuẫn' if held else 'Sẵn sàng chấm thử trong sandbox')+'</span></header><div class="function"><code>'+e(reference['function_latex'])+'</code></div>'+note+'<p>Đáp án in: <b>'+e(reference['printed_answer'])+'</b> · Giá trị tính độc lập: <b>'+e(reference['answer_display'])+'</b></p><details><summary>Ảnh nguồn và ghi chú đối chiếu</summary>'+images+('<pre>'+e('\n'.join(reference['annotation_notes']))+'</pre>' if reference['annotation_notes'] else '')+'</details><details><summary>Rubric đề xuất · 10 điểm thử nghiệm</summary><p>Miền xét phải đúng. Kiểm từng mệnh đề độc lập; bước bị thiếu không được tự suy ra để cộng điểm. Các quan hệ tiền đề chưa thỏa được báo riêng.</p>'+''.join(rubric_tables)+'</details><h3>Các tình huống đã chạy</h3>'+(''.join(scenarios) or '<p>Chưa chạy bộ tình huống.</p>')+'</article>')
    html='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Coach · Chấm thử đạo hàm</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f7f6;color:#193b45;font:14px/1.6 "Segoe UI",system-ui,sans-serif}main{max-width:1220px;margin:32px auto;padding:0 24px}h1{font-size:30px;margin:8px 0}small{font-size:10px;letter-spacing:1.5px;color:#397e6b}h2{margin:3px 0}h3{font-size:15px}.intro{color:#637d85;max-width:850px}.notice{padding:18px 22px;border:1px solid #dfd2af;border-radius:12px;background:#fff8e8;margin:20px 0}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:22px 0}.stat{background:white;padding:18px;border:1px solid #dce7e2;border-radius:12px}.stat b{display:block;font-size:28px;color:#117b66}.stat span{color:#69858a;font-size:12px}article{background:white;border:1px solid #dce7e2;border-radius:14px;padding:24px;margin:20px 0}article header{display:flex;align-items:center;justify-content:space-between;gap:12px}.tag{display:inline-block;border-radius:20px;padding:5px 10px;font-size:11px;background:#e5f5ed;color:#16715d}.tag.amber,.conflict{background:#fff4df;color:#8b5a19}.conflict{padding:14px;border-radius:8px;overflow-wrap:anywhere}.function{background:#f2f8f5;padding:13px 16px;border-radius:9px;margin:14px 0}details{border:1px solid #e0e9e5;border-radius:9px;padding:12px 15px;margin:10px 0}summary{cursor:pointer;font-weight:550;overflow-wrap:anywhere}.scenario summary b{margin:0 10px}.scenario[data-pass=false]{border-color:#cf7666}table{border-collapse:collapse;width:100%;font-size:12px;margin:14px 0}td,th{border-bottom:1px solid #e4ebe8;text-align:left;padding:10px;vertical-align:top;overflow-wrap:anywhere}code,pre{font-family:Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}td code{word-break:break-word}pre{font-size:12px;padding:12px;background:#f6f8f8;border-radius:8px}img{max-width:100%;height:auto}figure{margin:16px 0}figcaption{color:#718b8c;font-size:12px}input,select{padding:11px;border:1px solid #c9dcd3;border-radius:8px;font:inherit;background:white;color:inherit}input{width:230px;max-width:100%}.toolbar{display:flex;gap:10px;flex-wrap:wrap}a{color:#117b66}@media(max-width:700px){main{padding:0 14px}.stats{grid-template-columns:repeat(2,1fr)}article{padding:16px}article header{align-items:flex-start}.scenario .tag{display:block;width:fit-content;margin-top:8px}table{font-size:11px}td,th{padding:7px}h1{font-size:24px}}
</style><main><small>COACH LEARNING · CALCULUS SANDBOX</small><h1>Chấm thử từng bước từ PDF</h1><p class="intro">Nguồn có ảnh đối chiếu · Tính toán độc lập bằng code · Rubric có phiên bản · Có tình huống đúng, sai và chưa đủ thông tin</p><div class="notice">Điểm trên trang là điểm thử theo rubric đề xuất, chưa là điểm học sinh chính thức. Mẫu được chọn để phát triển và kiểm lỗi, không đo độ chính xác trên học sinh thật hoặc toàn bộ PDF. Hai bài có mâu thuẫn nguồn được giữ lại, không tự sửa đáp án hay lời giải.</div>'''
    html+='<div class="stats">'+''.join('<div class="stat"><b>'+str(v)+'</b><span>'+label+'</span></div>' for v,label in [(summary['questions'],'bài được đối chiếu'),(summary['ready_for_sandbox'],'bài có thể chấm thử'),(summary['held_for_source_conflict'],'bài giữ lại do nguồn'),(summary.get('assertions_passed',0),'tình huống đạt kỳ vọng')])+'</div>'
    html+='<div class="toolbar"><input id="search" placeholder="Tìm số câu, ví dụ 179"><select id="filter"><option value="">Mọi bài</option><option value="false">Có thể chấm thử</option><option value="true">Có mâu thuẫn nguồn</option></select></div><p><a href="questions.sandbox-rubric.jsonl">Gói rubric JSONL</a> · <a href="scenario-results.jsonl">Phản hồi từng tình huống</a> · <a href="evaluation.json">Báo cáo kiểm thử</a></p>'+''.join(cards)
    html+='''<script>function filter(){let q=document.getElementById('search').value.trim(),held=document.getElementById('filter').value;for(const a of document.querySelectorAll('article'))a.hidden=!!((q&&!a.dataset.number.includes(q))||(held&&a.dataset.held!==held));}document.getElementById('search').addEventListener('input',filter);document.getElementById('filter').addEventListener('change',filter);</script></main></html>'''
    (Path(output)/'review.html').write_text(html,encoding='utf-8')
