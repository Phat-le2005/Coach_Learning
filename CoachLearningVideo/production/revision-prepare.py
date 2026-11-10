import json,httpx
from pathlib import Path
R=Path(__file__).parent;D=R/'revision';D.mkdir(exist_ok=True)
p=json.loads((R/'context.private.json').read_text(encoding='utf8'))
c=httpx.Client(base_url='http://127.0.0.1:8050',timeout=60)
t=c.post('/auth/login',json={'email':p['teacher']['email'],'password':p['password']}).json()['access_token'];h={'Authorization':__import__("os").environ["VIDEO_DEMO_PASSWORD"]+t}
title='Phiếu luyện tập đạo hàm — tuần 12'
rows=c.get('/teacher-materials',headers=h,params={'classroom_id':p['classroom_id']}).json()
m=next((x for x in rows if x['title']==title),None)
if not m:
 text="Câu 1. Tính đạo hàm của hàm số y = x^3 - 3x.\n\nCâu 2. Tính đạo hàm của hàm số y = x^2 - 2x.\n\nCâu 3. Tìm x để đạo hàm của y = x^3 - 3x bằng 0.\n"
 x=c.post('/teacher-materials/upload',headers=h,data={'classroom_id':p['classroom_id'],'subject_id':p['subject_id'],'title':title},files={'file':('phieu-dao-ham.txt',text.encode(),'text/plain')})
 if x.status_code!=201:raise SystemExit('Upload HTTP '+str(x.status_code))
 m=x.json()
items=c.get('/teacher-materials/'+m['id']+'/items',headers=h).json()
answers=[("3x^2 - 3","Đạo hàm của x^3 là 3x^2; đạo hàm của -3x là -3."),("2x - 2","Áp dụng quy tắc đạo hàm của tổng."),("x = -1 hoặc x = 1","Giải 3x^2 - 3 = 0.")]
for item,(answer,explanation) in zip(items,answers):
 x=c.patch('/teacher-materials/items/'+item['id'],headers=h,json={'question_type':'OPEN_RESPONSE','correct_answer':answer,'explanation':explanation,'content_reviewed':True,'difficulty':.4})
 if x.status_code!=200:raise SystemExit('Item review HTTP '+str(x.status_code))
p.update(revision_material_id=m['id'],revision_material_title=title,revision_assignment_title='Luyện tập đạo hàm — hạn nộp 15/11')
(D/'context.private.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'materialReady':True,'itemCount':len(items)}))
