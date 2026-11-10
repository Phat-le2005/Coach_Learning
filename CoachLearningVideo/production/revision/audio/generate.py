"""Two private TTS calls, no secret material printed."""
from pathlib import Path
import base64,json,wave,subprocess,re
import httpx,numpy as np
from dotenv import dotenv_values
D=Path(__file__).parent;D.mkdir(exist_ok=True)
base=json.loads(Path('C:/CoachLearningVideo/rehearsal/narration-v4.json').read_text(encoding='utf8'))['direction']
direction=base.replace('Coach Learning đọc gần như Câu-ch Lơ-ning.','Math Mate đọc gần như Mát Mây-t. Giữ giọng nam miền Nam Việt Nam, Sài Gòn tự nhiên.')
scenes=[{'id':'intro','text':'Có lời giải chưa chắc đã hiểu bài. Học sinh dễ lệ thuộc đáp án, thầy cô khó theo sát từng bước. Math Mate đồng hành để các em tự giải và hiểu cách làm.','target':12,'delivery':'Đọc mở đầu hơi nhanh, khoảng ba phẩy bốn tiếng mỗi giây, rõ ràng. Nhấn hiểu bài, tự giải. Không kéo dài chữ.'},
{'id':'teacher00','text':'Với giáo viên, cô Thu Hà quản lý lớp và học liệu trong cùng một không gian. Cô chọn bài luyện tập, đặt hạn nộp, rồi giao cho học sinh. Minh Anh nhận được bài mới cùng thời gian hoàn thành. Thầy cô tiếp tục theo dõi quá trình làm bài ngay tại đây.','target':21,'delivery':'Nhịp vừa phải, gần gũi. Nhấn chọn bài, đặt hạn nộp, giao cho học sinh. Ngắt rõ mỗi câu.'}]
env=dotenv_values('D:/SGU/DuAn/Coach_Learning/backend/.env');keys=list(dict.fromkeys(x for x in [env.get('GEMINI_KEY_DEMO_04'),env.get('GEMINI_KEY_DEMO_05'),env.get('AI_API_KEY')] if x))
report=[]
for scene in scenes:
 raw=D/(scene['id']+'-raw.wav');dst=D/(scene['id']+'.wav')
 if not raw.exists():
  prompt=direction+'\n'+scene['delivery']+f" Độ dài mong muốn khoảng {scene['target']} giây, giữ âm tự nhiên.\nChỉ đọc nguyên văn:\n"+scene['text']
  body={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'responseModalities':['AUDIO'],'speechConfig':{'voiceConfig':{'prebuiltVoiceConfig':{'voiceName':'Charon'}}}}}
  for key in keys[:2]:
   response=httpx.post('https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent',headers={'x-goog-api-key':key},json=body,timeout=100)
   if response.status_code==200:break
  if response.status_code!=200:raise SystemExit('TTS HTTP '+str(response.status_code))
  inline=next(p['inlineData'] for p in response.json()['candidates'][0]['content']['parts'] if 'inlineData' in p)
  with wave.open(str(raw),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(base64.b64decode(inline['data']))
 with wave.open(str(raw)) as w:data=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
 active=np.flatnonzero(np.abs(data.astype(np.int32))>160)
 if active.size:data=data[max(0,int(active[0])-2400):min(len(data),int(active[-1])+4801)]
 with wave.open(str(dst),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(data.tobytes())
 seconds=len(data)/24000
 subprocess.run(['C:/ffmpeg/bin/ffmpeg.exe','-y','-i',str(dst),'-af','loudnorm=I=-16:TP=-1.5:LRA=7','-ar','48000','-c:a','libmp3lame','-q:a','2',str(D/(scene['id']+'.mp3'))],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
 sentences=re.findall(r'[^.!?]+[.!?]?',scene['text']);weights=[len(x.split()) for x in sentences];at=.1;captions=[]
 for s,n in zip(sentences,weights):
  end=at+(seconds-.3)*n/sum(weights);captions.append({'startMs':round(at*1000),'endMs':round(end*1000),'text':s.strip()});at=end
 (D/(scene['id']+'-captions.json')).write_text(json.dumps(captions,ensure_ascii=False,indent=2),encoding='utf8')
 report.append({**scene,'seconds':seconds,'wav':str(dst),'mp3':str(D/(scene['id']+'.mp3')),'voice':'Charon','speechSpeed':1})
(D/'narration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps([{'id':x['id'],'seconds':x['seconds']} for x in report]))
