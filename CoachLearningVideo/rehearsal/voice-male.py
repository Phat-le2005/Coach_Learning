import base64,json,wave,subprocess
from pathlib import Path
import httpx
from dotenv import dotenv_values
R=Path(__file__).parent;out=R/'voice';out.mkdir(exist_ok=True)
key=dotenv_values('D:/SGU/DuAn/Coach_Learning/backend/.env').get('AI_API_KEY')
text='Học toán không chỉ là tìm ra đáp án. Mình cần hiểu từng bước giải và biết chỗ nào nên xem lại. Với Coach Learning, các em có thể viết bài, đối chiếu bản chép và nhận phản hồi ngay trong quá trình học.'
direction='Bạn là người thuyết minh NAM trưởng thành khoảng 28 đến 35 tuổi, giọng miền Nam Việt Nam, Sài Gòn tự nhiên. Giọng trầm vừa, ấm, gần gũi, rõ chữ; không đọc theo giọng Bắc và không đọc kiểu quảng cáo. Nhịp vừa phải, ngắt ngắn giữa các câu. Coach Learning đọc gần như Câu-ch Lơ-ning. Chỉ đọc nguyên văn đoạn sau, không đọc chỉ dẫn: '
report={}
for voice in ['Charon','Orus']:
 body={'contents':[{'parts':[{'text':direction+text}]}],'generationConfig':{'responseModalities':['AUDIO'],'speechConfig':{'voiceConfig':{'prebuiltVoiceConfig':{'voiceName':voice}}}}}
 try:
  response=httpx.post('https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent',headers={'x-goog-api-key':key},json=body,timeout=90)
  record={'http':response.status_code,'requestedGender':'male','requestedAccent':'Southern Vietnamese','accentHumanVerified':False}
  if response.status_code==200:
   part=next(p['inlineData'] for p in response.json()['candidates'][0]['content']['parts'] if 'inlineData' in p)
   data=base64.b64decode(part['data']);file=out/(voice.lower()+'.wav')
   with wave.open(str(file),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(data)
   record['seconds']=len(data)/48000
   subprocess.run(['C:/ffmpeg/bin/ffmpeg.exe','-y','-i',str(file),'-c:a','libmp3lame','-q:a','2',str(file.with_suffix('.mp3'))],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
  report[voice]=record
 except Exception as e:report[voice]={'errorType':type(e).__name__}
 (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
