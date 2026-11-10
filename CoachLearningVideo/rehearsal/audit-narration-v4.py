"""Automated audio/content QA, explicitly not a human listening approval."""
import base64,json
from pathlib import Path
import httpx
from dotenv import dotenv_values
R=Path(__file__).parent;D=R/'voice-v4'
c=json.loads((R/'narration-v4.json').read_text(encoding='utf8'))
env=dotenv_values('D:/SGU/DuAn/Coach_Learning/backend/.env');key=env.get('GEMINI_KEY_DEMO_03') or env.get('AI_API_KEY')
parts=[{'text':'''Evaluate the ACTUAL attached Vietnamese narration recordings, not what their instructions requested. Each clip is labeled with its id and intended text. Return compact JSON with overall perceived_gender, perceived_accent (southern/northern/central/mixed/uncertain), speaker_consistency, clarity_1_to_5, naturalness_1_to_5, and issues. For EACH clip give id, content_matches (boolean), omitted_or_added_words, mispronunciations, and sentences [{text,start,end}] with approximate timestamps in seconds measured FROM THAT CLIP. Use the spoken sentence boundaries, not evenly allocated timestamps. Include whether pauses sound natural or rushed. Pay special attention to names Coach Learning, Math View, and the mathematical explanation: derivative of minus three x must be minus three whereas student wrote plus three. It is okay to report mixed accent or uncertainty. Do not claim human review. Do not invent missing audio.''' }]
for s in c['scenes']:
    p=D/(s['id']+'-trim.wav')
    if not p.exists():raise SystemExit('A clip is missing; generate audio before auditing.')
    parts.extend([{'text':s['id']+' Intended content: '+s['text']},{'inlineData':{'mimeType':'audio/wav','data':base64.b64encode(p.read_bytes()).decode()}}])
report={'assessmentKind':'automated audio model assessment; not human listening approval'}
try:
    response=httpx.post('https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent',headers={'x-goog-api-key':key},json={'contents':[{'parts':parts}],'generationConfig':{'responseMimeType':'application/json','maxOutputTokens':10000}},timeout=110)
    report['http']=response.status_code
    if response.status_code==200:
        text=''.join(p.get('text','') for p in response.json()['candidates'][0]['content']['parts'] if not p.get('thought'))
        report['assessment']=json.loads(text)
except Exception as e:report['errorType']=type(e).__name__
(D/'assessment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=True)[:1400])
