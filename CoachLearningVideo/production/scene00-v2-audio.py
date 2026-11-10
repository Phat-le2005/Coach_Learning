from pathlib import Path
import base64,json,wave,subprocess
import httpx,numpy as np
from dotenv import dotenv_values
D=Path(__file__).parent/'scene00-v2';D.mkdir(exist_ok=True)
text='Khi học toán, có lời giải chưa chắc là đã hiểu bài. Học sinh dễ làm theo đáp án mà bỏ qua cách suy luận, còn giáo viên khó theo sát từng bước của cả lớp. Ngay cả AI cũng có thể lập luận sai. Math Mate hướng tới việc gợi mở và phản hồi theo từng bước, giúp học sinh tự tìm cách giải. Sau khi đăng nhập, cô Thu Hà quản lý lớp, học sinh, học liệu, lý thuyết và báo cáo trong cùng một không gian. Cô chọn phiếu luyện tập, đặt hạn nộp và giao những câu phù hợp cho lớp. Từ đây, thầy cô tiếp tục theo dõi tiến độ và xem lại bài làm của học sinh.'
direction='Người thuyết minh NAM trưởng thành khoảng 30 tuổi, giọng miền Nam Việt Nam, Sài Gòn tự nhiên, trầm vừa, ấm, rõ, gần gũi. Math Mate đọc gần như Mát Mây-t. Đọc liền mạch tự nhiên, khoảng 3,2 tiếng mỗi giây, không kéo dài âm, không dừng lâu giữa các câu hoặc ý. Giọng hướng dẫn nhẹ nhàng, không quảng cáo. Chỉ nghỉ ngắn tự nhiên theo dấu câu, không tạo khoảng trống cho thao tác. Chỉ đọc nguyên văn nội dung sau:\n'
env=dotenv_values('D:/SGU/DuAn/Coach_Learning/backend/.env');keys=[env.get('GEMINI_KEY_DEMO_04'),env.get('GEMINI_KEY_DEMO_05')];raw=D/'narration-raw.wav'
if not raw.exists():
 body={'contents':[{'parts':[{'text':direction+text}]}],'generationConfig':{'responseModalities':['AUDIO'],'speechConfig':{'voiceConfig':{'prebuiltVoiceConfig':{'voiceName':'Charon'}}}}}
 for key in keys:
  if not key:continue
  r=httpx.post('https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent',headers={'x-goog-api-key':key},json=body,timeout=100)
  if r.status_code==200:break
 if r.status_code!=200:raise SystemExit('TTS HTTP '+str(r.status_code))
 inline=next(p['inlineData'] for p in r.json()['candidates'][0]['content']['parts'] if 'inlineData' in p)
 with wave.open(str(raw),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(base64.b64decode(inline['data']))
with wave.open(str(raw)) as w:data=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
active=np.flatnonzero(np.abs(data.astype(np.int32))>160)
if active.size:data=data[max(0,int(active[0])-2400):min(len(data),int(active[-1])+4801)]
with wave.open(str(D/'narration.wav'),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(data.tobytes())
report={'text':text,'seconds':len(data)/24000,'voice':'Charon','accentRequested':'Southern Vietnamese','singleContinuousClip':True,'speed':1,'addedSilence':False}
(D/'narration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:report[k] for k in ['seconds','voice','singleContinuousClip']}))
