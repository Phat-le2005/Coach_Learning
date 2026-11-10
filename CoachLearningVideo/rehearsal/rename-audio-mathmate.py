"""Replace only the two brand-name clips; preserve the user's chosen unpaced edit."""
import base64,hashlib,json,subprocess,wave
from pathlib import Path
import httpx,numpy as np
from dotenv import dotenv_values
R=Path(__file__).parent;OLD=R/'voice-v4';D=R/'voice-mathmate';D.mkdir(exist_ok=True)
c=json.loads((R/'narration-v4.json').read_text(encoding='utf8'))
env=dotenv_values('D:/SGU/DuAn/Coach_Learning/backend/.env');key=env.get('GEMINI_KEY_DEMO_04') or env.get('AI_API_KEY')
records=[];track=np.zeros(180*24000,dtype='<i2')
for scene in c['scenes']:
    old=OLD/(scene['id']+'-trim.wav');changed='Coach Learning' in scene['text']
    scene['text']=scene['text'].replace('Coach Learning','Math Mate')
    if scene['id']=='08-close':scene['text']='Math Mate. Học có định hướng, làm bài có phản hồi.'
    source=old
    rec={'id':scene['id'],'changedBrand':changed}
    if changed:
        source=D/(scene['id']+'.wav')
        prompt=c['direction'].replace('Coach Learning đọc gần như Câu-ch Lơ-ning.','Math Mate là tên sản phẩm, đọc theo tiếng Anh gần như Mát Mây-t, không đọc thành Mát Mát.')+'\n'+scene['delivery']+'\nChỉ đọc nội dung sau, giữ nhịp tự nhiên như những đoạn trước:\n'+scene['text']
        if not source.exists():
            body={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'responseModalities':['AUDIO'],'speechConfig':{'voiceConfig':{'prebuiltVoiceConfig':{'voiceName':'Charon'}}}}}
            response=httpx.post('https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent',headers={'x-goog-api-key':key},json=body,timeout=100)
            if response.status_code!=200:raise SystemExit('Brand clip request HTTP '+str(response.status_code))
            inline=next(p['inlineData'] for p in response.json()['candidates'][0]['content']['parts'] if 'inlineData' in p)
            if '24000' not in inline.get('mimeType',''):raise SystemExit('Unexpected sample rate')
            with wave.open(str(source),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(base64.b64decode(inline['data']))
    with wave.open(str(source)) as w:data=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
    if changed:
        active=np.flatnonzero(np.abs(data.astype(np.int32))>160)
        if active.size:data=data[max(0,int(active[0])-2880):min(len(data),int(active[-1])+2881)]
    tail=scene['duration']-scene['lead']-len(data)/24000
    rec.update(seconds=round(len(data)/24000,4),tail=round(tail,3),source=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    if tail<.25:raise SystemExit('Replacement exceeds slot '+scene['id'])
    with wave.open(str(D/(scene['id']+'-trim.wav')),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(data.tobytes())
    offset=round((scene['start']+scene['lead'])*24000);track[offset:offset+len(data)]=data;records.append(rec)
file=D/'mathmate-narration-180s.wav'
with wave.open(str(file),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(track.tobytes())
subprocess.run(['C:/ffmpeg/bin/ffmpeg.exe','-y','-i',str(file),'-af','loudnorm=I=-16:TP=-1.5:LRA=7','-ar','48000','-c:a','libmp3lame','-q:a','2',str(D/'mathmate-narration-180s.mp3')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
(D/'narration.json').write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf8')
(D/'report.json').write_text(json.dumps({'brand':'Math Mate','base':'user-selected narration-v4-180s.mp3 unpaced structure','timelineSeconds':180,'speed':1,'records':records},indent=2),encoding='utf8')
print(json.dumps({'replacedClips':sum(x['changedBrand'] for x in records),'preservedClips':sum(not x['changedBrand'] for x in records),'seconds':180}))
