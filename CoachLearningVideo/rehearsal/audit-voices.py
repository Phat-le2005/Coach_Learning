import base64,json
from pathlib import Path
import httpx
from dotenv import dotenv_values
R=Path(__file__).parent/'voice';key=dotenv_values('D:/SGU/DuAn/Coach_Learning/backend/.env').get('AI_API_KEY')
parts=[{'text':'Compare two generated Vietnamese narration samples labeled Charon and Orus. We need an adult male Southern Vietnamese/Saigon accent, warm and clear for an educational product demo. Listen to actual audio, do not infer from the requested accent or voice name. Return JSON with each sample: perceived_gender, perceived_accent (southern/northern/central/mixed/uncertain), clarity_1_to_5, naturalness_1_to_5, brief Vietnamese evidence. Then recommended_sample and uncertainty. It is acceptable to say neither meets Southern accent. Do not claim certainty from a short sample.'}]
for name in ['charon','orus']:
 parts.extend([{'text':name},{'inlineData':{'mimeType':'audio/wav','data':base64.b64encode((R/(name+'.wav')).read_bytes()).decode()}}])
body={'contents':[{'parts':parts}],'generationConfig':{'responseMimeType':'application/json','maxOutputTokens':2048}}
try:
 r=httpx.post('https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent',headers={'x-goog-api-key':key},json=body,timeout=60)
 report={'http':r.status_code,'assessmentKind':'automated model assessment, not human confirmation'}
 if r.status_code==200:
  data=r.json();text=''.join(p.get('text','') for p in data['candidates'][0]['content']['parts'] if not p.get('thought'))
  report['assessment']=json.loads(text)
except Exception as e:report={'errorType':type(e).__name__}
(R/'assessment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
