import json,os,sys
from pathlib import Path
import httpx
R=Path(__file__).parent;os.environ.update(json.loads((R/'environment.json').read_text()));sys.path.insert(0,'D:/SGU/DuAn/Coach_Learning/backend')
from app.core.config import get_settings
from app.math_ink.schemas import InkStroke
import app.math_ocr.gemini_adapter as m
p=json.loads((R/'private.json').read_text(encoding='utf-8'));c=httpx.Client(base_url='http://127.0.0.1:8050',timeout=30)
t=c.post('/auth/login',json={'email':p['student']['email'],'password':p['password']}).json()['access_token']
raw=c.get('/api/v2/math-solutions/attempts/'+p['attempt_id']+'/ink/pages/0',headers={'Authorization':__import__("os").environ["VIDEO_DEMO_PASSWORD"]+t}).json()
strokes=[InkStroke.model_validate(s) for s in raw['strokes']]
orig=m.sdk_failure
def spy(error):
 message=str(error)
 for field in get_settings().model_fields:
  value=getattr(get_settings(),field)
  if hasattr(value,'get_secret_value'):
   secret=value.get_secret_value()
   if secret:message=message.replace(secret,'[REDACTED]')
 print('Sanitized upstream error:',message[:2200],flush=True)
 return orig(error)
m.sdk_failure=spy
adapter=m.GeminiMathOCRAdapter()
try:
 result=adapter.recognize(strokes)
 (R/'actual-ocr-direct.json').write_text(result.model_dump_json(indent=2),encoding='utf-8');print('Direct real OCR PASS')
except Exception as e:print('Adapter result:',type(e).__name__)
