import json
from pathlib import Path
import httpx
R=Path(__file__).parent;p=json.loads((R/'private.json').read_text(encoding='utf-8'))
c=httpx.Client(base_url='http://127.0.0.1:8050',timeout=30)
token=c.post('/auth/login',json={'email':p['teacher']['email'],'password':p['password']}).json()['access_token'];c.headers['Authorization']='Bearer '+token
url='/api/v2/teacher/theory/'+p['theory_id'];r=c.get(url);r.raise_for_status();doc=r.json()
if doc['status']=='PUBLISHED':print('Theory already published');raise SystemExit(0)
old={x['id']:x for x in doc['nodes']}
def node(id,parent,kind,title,body,page,quote,latex=None,steps=None):
 return dict(id=id,parent_id=parent,kind=kind,title=title,body=body,source_page=page,source_quote=quote,latex=latex,reviewed=True,learning_steps=steps or [])
q1=old['n2']['source_quote'];q2=old['n4']['source_quote'];q3=old['n6']['source_quote']
nodes=[
 node('root',None,'ROOT','Đạo hàm và khảo sát hàm số','Ôn công thức đạo hàm, xét tính đơn điệu và nhận biết cực trị.',1,old['n1']['source_quote']),
 node('rules','root','SECTION','Bảng đạo hàm','Các công thức cơ bản cần nhớ.',1,q1),
 node('power','rules','FORMULA','Đạo hàm hàm lũy thừa','Dùng quy tắc này để tính đạo hàm các đa thức.',1,q1,r"(x^n)'=n x^{n-1}"),
 node('sum','rules','FORMULA','Đạo hàm của tổng và hiệu','Tính đạo hàm riêng từng hạng tử, giữ đúng dấu.',1,q1,r"(u\pm v)'=u'\pm v'"),
 node('factor','rules','FORMULA','Hệ số không đổi','Hệ số k được giữ nguyên khi lấy đạo hàm.',1,q1,r"(ku)'=ku'"),
 node('monotonic','root','SECTION','Tính đơn điệu','Dựa vào dấu đạo hàm để xét chiều biến thiên.',2,q2),
 node('increasing','monotonic','FORMULA','Khoảng đồng biến','Nếu đạo hàm dương trên khoảng K thì hàm số đồng biến trên K.',2,q2,r"f'(x)>0\quad\forall x\in K"),
 node('decreasing','monotonic','FORMULA','Khoảng nghịch biến','Nếu đạo hàm âm trên khoảng K thì hàm số nghịch biến trên K.',2,q2,r"f'(x)<0\quad\forall x\in K"),
 node('method','monotonic','METHOD','Bốn bước xét tính đơn điệu','Xác định miền; tính đạo hàm; xét dấu; kết luận.',2,q2,steps=[{'instruction':x,'source_page':2,'source_quote':q2} for x in ['Tìm tập xác định của hàm số.','Tính đạo hàm và tìm các điểm đạo hàm bằng 0 hoặc không tồn tại.','Sắp xếp các điểm theo thứ tự và lập bảng biến thiên.','Kết luận các khoảng đồng biến và nghịch biến.']]),
 node('extrema','root','CONCEPT','Điểm cực trị và giá trị cực trị','Phân biệt vị trí cực trị với giá trị của hàm số tại vị trí đó.',3,q3),
]
r=c.put(url+'/map',json={'expected_revision':doc['revision'],'nodes':nodes});r.raise_for_status();doc=r.json()
r=c.post(url+'/publish',json={'expected_revision':doc['revision']});r.raise_for_status();doc=r.json()
r=c.post(url+'/share-source',json={'expected_revision':doc['revision']});r.raise_for_status();doc=r.json()
(R/'theory-reviewed.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
print('Manually reviewed source-faithful theory map published:',len(nodes),'nodes; original source shared.')
