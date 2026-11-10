"""Insert breathing room ONLY inside measured natural silence; keep speech at 1x."""
import json,subprocess,wave
from pathlib import Path
import numpy as np
R=Path(__file__).parent;D=R/'voice-v4';SR=24000
cfg=json.loads((R/'narration-v4.json').read_text(encoding='utf8'))
gaps=json.loads((D/'silence-gaps.json').read_text())
# Desired natural sentence gaps from waveform inspection; seconds relative to raw clip.
pauses={
 '02-plan':[(6.4,1.5,'Giữ mục tiêu'),(10.0,1.5,'Chuyển từ kế hoạch sang cây kiến thức')],
 '03-theory':[(7.5,1.8,'Đọc công thức trước khi mở nguồn')],
 '04-mathview':[(3.6,.8,'Math View xuất hiện'),(8.2,2.5,'Đổi tham số và quan sát'),(13.8,1.5,'Giữ hình trước khi lưu')],
 '05-handwriting':[(8.4,4,'Nét viết đồng bộ'),(11.9,4,'Giữ bước viết sai dấu'),(15.7,3,'Kết quả nhận diện xuất hiện'),(28.1,1.5,'Đối chiếu dấu cộng đã viết')],
 '06-feedback':[(11.9,.8,'Giữ giải thích trừ ba/cộng ba')],
 '07-teacher':[(4.1,1.5,'Nộp toàn bộ bài'),(15.6,1.5,'Giữ bài nộp của Minh Anh')]
}
track=np.zeros(180*SR,dtype='<i2');report=[]
for scene in cfg['scenes']:
    ident=scene['id'];p=D/(ident+'-trim.wav')
    with wave.open(str(p)) as w:data=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
    inserts=[]
    for target,seconds,reason in pauses.get(ident,[]):
        candidates=[(a,b) for a,b in gaps[ident] if a>.25 and b<len(data)/SR-.25]
        a,b=min(candidates,key=lambda ab:abs(sum(ab)/2-target))
        if abs((a+b)/2-target)>.7:raise ValueError('No safe natural silence near cue '+ident)
        inserts.append((round((a+b)/2*SR),seconds,reason))
    pieces=[];cursor=0;events=[];added=0
    for index,seconds,reason in sorted(inserts):
        pieces.extend([data[cursor:index],np.zeros(round(seconds*SR),dtype='<i2')])
        events.append({'timelineStart':round(scene['start']+scene['lead']+index/SR+added,3),'seconds':seconds,'purpose':reason})
        cursor=index;added+=seconds
    pieces.append(data[cursor:]);paced=np.concatenate(pieces)
    tail=scene['duration']-scene['lead']-len(paced)/SR
    if tail<.35:raise ValueError('Scene does not fit: '+ident)
    offset=round((scene['start']+scene['lead'])*SR);track[offset:offset+len(paced)]=paced
    report.append({'id':ident,'audioSeconds':round(len(data)/SR,3),'insertedPausesSeconds':added,'endHoldSeconds':round(tail,3),'pauses':events})
file=D/'narration-v4-paced-180s.wav'
with wave.open(str(file),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(SR);w.writeframes(track.tobytes())
subprocess.run(['C:/ffmpeg/bin/ffmpeg.exe','-y','-i',str(file),'-af','loudnorm=I=-16:TP=-1.5:LRA=7','-ar','48000','-c:a','libmp3lame','-q:a','2',str(D/'narration-v4-paced-180s.mp3')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
(D/'pacing-report.json').write_text(json.dumps({'durationSeconds':180,'speechSpeed':1,'cutSpeech':False,'scenes':report},ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'durationSeconds':180,'speechSpeed':1,'sceneCount':len(report),'insertedBreathingRoom':sum(s['insertedPausesSeconds'] for s in report)}))
