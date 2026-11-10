import json,httpx,uuid
from pathlib import Path
R=Path(__file__).parent;p=json.loads(Path('C:/CoachLearningVideo/rehearsal/private.json').read_text(encoding='utf8'))
dest=R/'context.private.json'
if dest.exists():raise SystemExit('Recording context exists; preserve active capture.')
c=httpx.Client(base_url='http://127.0.0.1:8050',timeout=60)
def req(method,url,token=None,**kw):
    r=c.request(method,url,headers={'Authorization':__import__("os").environ["VIDEO_DEMO_PASSWORD"]+token} if token else {},**kw)
    if r.status_code>=400:raise RuntimeError('HTTP '+str(r.status_code)+' '+url)
    return r.json() if r.content else None
t=req('POST','/auth/login',json={'email':p['teacher']['email'],'password':p['password']})['access_token']
s=req('POST','/auth/login',json={'email':p['student']['email'],'password':p['password']})['access_token']
title='Đạo hàm — luyện tập từng bước'
a=req('POST',f"/teacher/classes/{p['classroom_id']}/assignments",t,json={'classroom_id':p['classroom_id'],'subject_id':p['subject_id'],'title':title,'description':'Tính đạo hàm, đối chiếu lời giải và nhận góp ý theo từng bước.','assignment_type':'SAME_SET','delivery_mode':'PRACTICE','question_count':3,'question_ids':p['question_ids']})
req('POST',f"/teacher/assignments/{a['id']}/publish",t)
rows=req('GET','/students/me/assignments',s)
rows=rows.get('items',rows) if isinstance(rows,dict) else rows
assigned=next(x for x in rows if x['assignment_id']==a['id'])
prepared=req('POST',f"/api/v2/math-solutions/student-assignments/{assigned['id']}/prepare",s)
(R/'prepared-problems.private.json').write_text(json.dumps(prepared,ensure_ascii=False,indent=2),encoding='utf8')
problems=prepared.get('problems',prepared) if isinstance(prepared,dict) else prepared
item=next(x for x in problems if x.get('question_id')==p['question_ids'][0])
attempt=req('POST','/api/v2/math-solutions/attempts',s,json={'source_kind':'CANONICAL','context_type':'CLASSROOM_ASSIGNMENT','mode':'GUIDED_LEARNING','question_id':p['question_ids'][0],'student_assignment_id':assigned['id'],'assignment_student_question_id':item['assignment_student_question_id'],'create_idempotency_key':'video-production-'+str(uuid.uuid4())})
p.update(attempt_id=attempt['id'],assignment_id=a['id'],student_assignment_id=assigned['id'],assignment_title=title)
dest.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'assignment_id':a['id'],'title':title,'attempt_id':attempt['id'],'status':'Fresh real recording context ready'},ensure_ascii=True))
