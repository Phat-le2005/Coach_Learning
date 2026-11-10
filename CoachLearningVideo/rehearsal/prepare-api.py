import json,time,uuid
from pathlib import Path
import httpx
from pypdf import PdfReader,PdfWriter
R=Path(__file__).parent;p=json.loads((R/'private.json').read_text(encoding='utf-8'))
client=httpx.Client(base_url='http://127.0.0.1:8050',timeout=150)
report={}
def req(method,path,token=None,**kw):
 r=client.request(method,path,headers={'Authorization':__import__("os").environ["VIDEO_DEMO_PASSWORD"]+token} if token else {},**kw)
 if r.status_code>=400:
  try:code=r.json().get('error',{}).get('code')
  except Exception:code=None
  raise RuntimeError(f'{method} {path} HTTP {r.status_code} {code}')
 return r.json() if r.content else None
tokens={}
for role in ['student','teacher']:
 tokens[role]=req('POST','/auth/login',json={'email':p[role]['email'],'password':p['password']})['access_token']
 report[role+'Login']='PASS'
s=tokens['student'];t=tokens['teacher']
if 'attempt_id' not in p:
 session=req('POST','/practice/sessions',s,json={'subject_id':p['subject_id'],'session_type':'PRACTICE','problem_type_ids':[p['problem_type_id']],'concept_ids':[]})
 attempt=req('POST','/api/v2/math-solutions/attempts',s,json={'source_kind':'CANONICAL','context_type':'SELF_PRACTICE','mode':'GUIDED_LEARNING','question_id':p['question_ids'][0],'practice_session_id':session['id'],'create_idempotency_key':'video-rehearsal-primary-v1'})
 p['attempt_id']=attempt['id'];p['practice_session_id']=session['id']
 report['attempt']='PASS'
if 'assignment_id' not in p:
 assignment=req('POST',f"/teacher/classes/{p['classroom_id']}/assignments",t,json={'classroom_id':p['classroom_id'],'subject_id':p['subject_id'],'title':'Luyện tập đạo hàm và khảo sát hàm số','description':'Ôn lại cách tính đạo hàm và trình bày lời giải theo từng bước.','assignment_type':'SAME_SET','delivery_mode':'PRACTICE','question_count':3,'question_ids':p['question_ids']})
 p['assignment_id']=assignment['id'];req('POST',f"/teacher/assignments/{assignment['id']}/publish",t)
 report['assignment']='PASS'
(R/'private.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
(R/'api-report.json').write_text(json.dumps(report,indent=2))
if 'theory_id' not in p:
 source=next(Path('D:/SGU/DuAn/data_demo/data_lythuyet').glob('3.*.pdf'))
 pages=PdfReader(source);w=PdfWriter()
 for page in pages.pages[:3]:w.add_page(page)
 excerpt=R/'dao-ham-va-cuc-tri.pdf';w.write(excerpt)
 with excerpt.open('rb') as f:
  doc=req('POST','/api/v2/teacher/theory/upload',t,data={'classroom_id':p['classroom_id'],'subject_id':p['subject_id'],'title':'Đạo hàm và cực trị — công thức cần nhớ'},files={'file':(excerpt.name,f,'application/pdf')})
 p['theory_id']=doc['id'];(R/'private.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
 (R/'theory-initial.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
 report['theoryUpload']='PASS'
 started=time.monotonic()
 try:
  doc=req('POST',f"/api/v2/teacher/theory/{doc['id']}/generate",t)
  (R/'theory-generated.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
  report['theoryGeneration']={'status':'PASS','seconds':round(time.monotonic()-started,2),'nodes':len(doc['nodes'])}
 except Exception as e:report['theoryGeneration']={'status':'FAILED','reason':str(e)}
 (R/'api-report.json').write_text(json.dumps(report,indent=2))
if 'pdf_import_id' not in p:
 excerpt=Path('C:/CoachLearningPdf/setup-check/sample-page.pdf')
 with excerpt.open('rb') as f:
  job=req('POST','/teacher-materials/pdf-imports',t,data={'classroom_id':p['classroom_id'],'subject_id':p['subject_id'],'title':'Ôn tập nguyên hàm — bài tập từ tài liệu'},files={'file':('on-tap-nguyen-ham.pdf',f,'application/pdf')})
 p['pdf_import_id']=job['id'];(R/'private.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8');report['pdfUpload']='PASS'
(R/'api-report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
