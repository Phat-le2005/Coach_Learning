import json,base64
from pathlib import Path
import httpx
from dotenv import dotenv_values
R=Path('C:/CoachLearningVideo/rehearsal/voice-mathmate')
env=dotenv_values('D:/SGU/DuAn/Coach_Learning/backend/.env');key=env.get('GEMINI_KEY_DEMO_03') or env.get('AI_API_KEY')
parts=[{'text':'Listen to these TWO ACTUAL Vietnamese audio clips. Do not infer speech or accent from file names. Return JSON with per clip: id, literal_transcript, content_matches_intended, perceived_gender, perceived_accent (southern/northern/central/mixed/uncertain), brand_pronunciation, issues. We need adult male Southern Vietnamese and brand MathMate, spoken Math Mate. In clip02 intended begins "Với Math Mate, Minh Anh bắt đầu từ mục tiêu tám điểm, cùng ba mươi phút học mỗi ngày" and continues educational plan/knowledge tree. Clip08 intended EXACTLY "Math Mate. Học có định hướng, làm bài có phản hồi." Listen for mangled or missing Vietnamese words in particular. Do not generate timing estimates. Automated assessment only, no human approval claim.'}]
for ident in ['02-plan','08-close']:
    parts.extend([{'text':ident},{'inlineData':{'mimeType':'audio/wav','data':base64.b64encode((R/(ident+'-trim.wav')).read_bytes()).decode()}}])
record={'kind':'automated audio assessment, not human review'}
try:
    r=httpx.post('https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent',headers={'x-goog-api-key':key},json={'contents':[{'parts':parts}],'generationConfig':{'responseMimeType':'application/json','maxOutputTokens':3000}},timeout=90)
    record['http']=r.status_code
    if r.status_code==200:
        text=''.join(p.get('text','') for p in r.json()['candidates'][0]['content']['parts'] if not p.get('thought'));record['assessment']=json.loads(text)
except Exception as e:record['errorType']=type(e).__name__
(R/'assessment-brand.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(record,ensure_ascii=True)[:1800])
