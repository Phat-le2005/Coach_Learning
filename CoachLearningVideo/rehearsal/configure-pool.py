"""Import user-provided local keys without printing secret material."""
import concurrent.futures,json,re
from pathlib import Path
import httpx
from dotenv import dotenv_values,set_key
ROOT=Path(__file__).parent;ENV=Path('D:/SGU/DuAn/Coach_Learning/backend/.env')
raw=Path('C:/Users/ADMIN/OneDrive/MayTinh/note.txt').read_text(encoding='utf-8-sig')
found=re.findall(r'(?:AQ\.|AIza)[A-Za-z0-9_-]{25,}',raw)
values=dotenv_values(ENV);keys=list(dict.fromkeys([values.get('AI_API_KEY') or '',*found]));keys=[k for k in keys if k]
models=['gemini-3.6-flash','gemini-3.8-flash','gemini-3.5-flash']
def inspect(pair):
 i,key=pair;alias=f'key_{i+1:02}';record={'alias':alias,'quotaGroup':'unknown','models':{}}
 with httpx.Client(timeout=30) as c:
  for model in models:
   try:
    r=c.get('https://generativelanguage.googleapis.com/v1beta/models/'+model,headers={'x-goog-api-key':key});record['models'][model]={'metadataHttp':r.status_code}
   except Exception as e:record['models'][model]={'errorType':type(e).__name__}
  try:
   body={'contents':[{'parts':[{'text':'Return JSON with exactly one key ok and value true.'}]}],'generationConfig':{'responseMimeType':'application/json','maxOutputTokens':1024}}
   r=c.post('https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent',headers={'x-goog-api-key':key},json=body)
   record['generationHttp']=r.status_code
   if r.status_code==200:
    parts=r.json().get('candidates',[{}])[0].get('content',{}).get('parts',[])
    text=''.join(p.get('text','') for p in parts if not p.get('thought'))
    try:record['jsonProbe']=json.loads(text).get('ok') is True
    except (ValueError,AttributeError):record['jsonProbe']=False
  except Exception as e:record['generationErrorType']=type(e).__name__
 return i,record
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=sorted(pool.map(inspect,enumerate(keys)))
valid=[(keys[i],record) for i,record in results if record.get('generationHttp')==200 and record.get('jsonProbe')]
report={'providedFileKeys':len(found),'uniqueIncludingExisting':len(keys),'testedModels':models,'keys':[x for _,x in results],'enabled':len(valid)}
(ROOT/'key-pool-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
if not valid:raise SystemExit('No key passed generation probe; existing configuration preserved.')
pool=[]
for index,(key,record) in enumerate(valid,1):
 ref=f'GEMINI_KEY_DEMO_{index:02}'
 set_key(ENV,ref,key)
 pool.append({'id':record['alias'],'project':'unknown','env':ref})
set_key(ENV,'GEMINI_KEY_POOL',json.dumps(pool,separators=(',',':')))
set_key(ENV,'GEMINI_MODEL_PRIORITY',','.join(models))
set_key(ENV,'GEMINI_GRADING_MODELS','gemini-3.6-flash,gemini-3.8-flash')
settings={'GEMINI_ATTEMPT_TIMEOUT_SECONDS':'20','GEMINI_TUTOR_ATTEMPT_TIMEOUT_SECONDS':'15','GEMINI_OCR_ATTEMPT_TIMEOUT_SECONDS':'20','GEMINI_OCR_TOTAL_TIMEOUT_SECONDS':'60','GEMINI_REVIEW_ATTEMPT_TIMEOUT_SECONDS':'30'}
for key,value in settings.items():set_key(ENV,key,value)
print(json.dumps({'providedKeys':len(found),'uniqueTested':len(keys),'enabledKeys':len(valid),'models':models,'quotaGroup':'unknown','secretOutput':False}))
