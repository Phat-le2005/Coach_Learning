"""Technical speech probe only; never log credentials or provider response bodies."""
import base64
import json
from pathlib import Path
import wave
import httpx
from dotenv import dotenv_values

root = Path(__file__).parent
out = root / 'toolchain' / 'qa'
out.mkdir(parents=True, exist_ok=True)
values = dotenv_values('D:/SGU/DuAn/Coach_Learning/backend/.env')
key = values.get('AI_API_KEY') or values.get('GEMINI_API_KEY')
if not key:
    raise SystemExit('Local Gemini credential missing')
model = 'gemini-2.5-flash-preview-tts'
body = {
    'contents': [{'parts': [{'text': 'Đọc bằng giọng nữ miền Nam Việt Nam, tự nhiên, ấm áp, rõ chữ, tốc độ vừa phải. Chỉ đọc lời sau: Mình cùng xem lại bài làm nha. Kiểm tra từng bước để hiểu rõ hơn cách giải.'}]}],
    'generationConfig': {'responseModalities': ['AUDIO'], 'speechConfig': {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': 'Aoede'}}}},
}
report = {'model':model,'voice':'Aoede','purpose':'Technical preparation sample, not final narration','accentValidated':False}
try:
    r = httpx.post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',headers={'x-goog-api-key':key},json=body,timeout=90)
    report['http'] = r.status_code
    if r.status_code == 200:
        parts = r.json().get('candidates',[{}])[0].get('content',{}).get('parts',[])
        item = next((p['inlineData'] for p in parts if 'inlineData' in p),None)
        if item:
            raw = base64.b64decode(item['data'])
            with wave.open(str(out/'voice-probe.wav'),'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(raw)
            report.update({'mime':item.get('mimeType'),'seconds':len(raw)/48000,'audio':'voice-probe.wav'})
    else:
        error = r.json().get('error',{})
        report['providerStatus'] = error.get('status')
except Exception as e:
    report['errorType'] = type(e).__name__
(out/'voice-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
