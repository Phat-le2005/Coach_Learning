import json,httpx
from pathlib import Path
R=Path(__file__).parent;p=json.loads((R/'context.private.json').read_text(encoding='utf8'))
c=httpx.Client(base_url='http://127.0.0.1:8050',timeout=120)
t=c.post('/auth/login',json={'email':p['student']['email'],'password':p['password']}).json()['access_token'];h={'Authorization':__import__("os").environ["VIDEO_DEMO_PASSWORD"]+t}
attempt=c.get('/api/v2/math-solutions/attempts/'+p['attempt_id'],headers=h).json()
if attempt.get('status')!='SUBMITTED':raise SystemExit('Preserve capture: primary ink attempt is not submitted yet.')
u='/students/me/assignments/'+p['student_assignment_id']
before=c.get(u,headers=h).json()
if before.get('status') not in ['SUBMITTED','GRADED']:
    response=c.post(u+'/submit',headers=h,json={'answers':[{'question_id':p['question_ids'][1],'student_answer':"y' = 2x - 2"},{'question_id':p['question_ids'][2],'student_answer':'x = -1 hoặc x = 1'}]})
    if response.status_code!=200:raise SystemExit('Whole submission HTTP '+str(response.status_code))
    after=response.json()
else:after=before
(R/'whole-submission.json').write_text(json.dumps({'before':before,'after':after},ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'status':after.get('status'),'primaryInkPreserved':True,'assignmentId':p['assignment_id']}))
