"""Private, resumable voice production. Never print provider bodies or credentials."""
import base64,concurrent.futures,hashlib,json,subprocess,wave
import os
from pathlib import Path
import httpx
import numpy as np
from dotenv import dotenv_values

ROOT=Path(__file__).parent
CFG=json.loads((ROOT/'narration-v4.json').read_text(encoding='utf8'))
OUT=ROOT/'voice-v4';OUT.mkdir(exist_ok=True)
env=dotenv_values('D:/SGU/DuAn/Coach_Learning/backend/.env')
key=env.get('AI_API_KEY') or env.get('GEMINI_API_KEY')
key=env.get(os.environ.get('NARRATION_KEY_REF',''),key)
if not key:raise SystemExit('No private credential configured')
FFMPEG='C:/ffmpeg/bin/ffmpeg.exe'

def generate(scene):
    target=scene['duration']-scene['lead']-.7
    prompt=CFG['direction']+'\nHướng đọc riêng: '+scene['delivery']+f'\nĐọc khoảng {target:.1f} giây, không nói dồn, không kéo dài từng âm.\nNội dung:\n'+scene['text']
    digest=hashlib.sha256((CFG['voice']+CFG['model']+prompt).encode()).hexdigest()
    wav=OUT/(scene['id']+'.wav');meta=OUT/(scene['id']+'.json')
    record={'id':scene['id'],'start':scene['start'],'slot':scene['duration'],'lead':scene['lead'],'textUnits':len(scene['text'].split()),'hash':digest}
    try:
        cached=json.loads(meta.read_text()) if meta.exists() else {}
        if not (wav.exists() and cached.get('hash')==digest and cached.get('http')==200):
            body={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'responseModalities':['AUDIO'],'speechConfig':{'voiceConfig':{'prebuiltVoiceConfig':{'voiceName':CFG['voice']}}}}}
            response=httpx.post('https://generativelanguage.googleapis.com/v1beta/models/'+CFG['model']+':generateContent',headers={'x-goog-api-key':key},json=body,timeout=100)
            record['http']=response.status_code
            if response.status_code!=200:return record
            inline=next(p['inlineData'] for p in response.json()['candidates'][0]['content']['parts'] if 'inlineData' in p)
            if '24000' not in inline.get('mimeType',''):raise ValueError('Unexpected audio sample rate')
            data=base64.b64decode(inline['data'])
            with wave.open(str(wav),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(data)
        record['http']=200
        with wave.open(str(wav)) as w:
            samples=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
            record['seconds']=len(samples)/w.getframerate()
            # Trim only leading/trailing digital near-silence; retain 120 ms of air.
            active=np.flatnonzero(np.abs(samples.astype(np.int32))>160)
            if active.size:
                lo=max(0,int(active[0]) - 2880);hi=min(len(samples),int(active[-1])+2881)
                samples=samples[lo:hi]
            record['trimmedSeconds']=len(samples)/24000
            record['peak']=float(np.max(np.abs(samples.astype(np.int32)))/32768)
            record['tailSeconds']=round(scene['duration']-scene['lead']-len(samples)/24000,3)
            record['fits']=record['tailSeconds']>=.35
        with wave.open(str(OUT/(scene['id']+'-trim.wav')),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(samples.tobytes())
        subprocess.run([FFMPEG,'-y','-i',str(OUT/(scene['id']+'-trim.wav')),'-c:a','libmp3lame','-q:a','2',str(OUT/(scene['id']+'.mp3'))],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    except Exception as e:record['errorType']=type(e).__name__
    finally:meta.write_text(json.dumps(record,indent=2),encoding='utf8')
    return record

with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
    records=list(pool.map(generate,CFG['scenes']))
report={'voice':CFG['voice'],'model':CFG['model'],'speedManipulated':False,'records':records,'allFit':all(x.get('fits') for x in records)}
if report['allFit']:
    track=np.zeros(180*24000,dtype='<i2')
    for scene in CFG['scenes']:
        with wave.open(str(OUT/(scene['id']+'-trim.wav'))) as w:data=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
        offset=round((scene['start']+scene['lead'])*24000);track[offset:offset+len(data)]=data
    file=OUT/'narration-v4-180s.wav'
    with wave.open(str(file),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(track.tobytes())
    subprocess.run([FFMPEG,'-y','-i',str(file),'-af','loudnorm=I=-16:TP=-1.5:LRA=7','-ar','48000','-c:a','libmp3lame','-q:a','2',str(OUT/'narration-v4-180s.mp3')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    report['timelineSeconds']=180
(OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report),flush=True)
