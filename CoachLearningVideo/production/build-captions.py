"""Sentence anchors from measured PCM silence, not model-generated timestamps."""
import json,re,textwrap,wave,subprocess,math
from pathlib import Path
ROOT=Path(__file__).parent;VOICE=Path('C:/CoachLearningVideo/rehearsal/voice-mathmate')
cfg=json.loads((VOICE/'narration.json').read_text(encoding='utf8'))
# Each interval is an actual speech range bounded by the measured natural pauses.
spans={
 '01-hook':[(.128,2.566),(3.092,6.408)],
 '02-plan':[(.127,5.740),(6.413,9.535),(10.222,13.798),(14.484,18.922)],
 '03-theory':[(.121,2.672),(3.224,7.057),(7.812,10.332)],
 '04-mathview':[(.123,3.248),(3.896,7.754),(8.771,13.390),(14.188,17.679)],
 '05-handwriting':[(.121,3.181),(3.728,8.025),(8.751,11.587),(12.142,15.495),(15.971,19.900),(20.332,23.415),(24.101,27.944),(28.609,30.736),(30.920,33.958)],
 '06-feedback':[(.269,4.008),(4.595,11.509),(12.263,15.881),(16.625,19.456)],
 '07-teacher':[(.131,3.650),(4.510,9.294),(9.998,15.149),(15.990,20.069)]
}
def chunks(sentence,limit=80):
    if len(sentence)<=limit:return [sentence]
    words=sentence.split();out=[];groups=math.ceil(len(sentence)/limit)
    while groups>1:
        target=len(' '.join(words))/groups
        options=[k for k in range(1,len(words)-groups+2) if len(' '.join(words[:k]))<=limit]
        k=min(options,key=lambda k:abs(len(' '.join(words[:k]))-target)-(3 if words[k-1].endswith(',') else 0))
        out.append(' '.join(words[:k]));words=words[k:];groups-=1
    out.append(' '.join(words))
    return out
def stamp(ms):
    ms=round(ms);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
rows=[];checks=[]
for scene in cfg['scenes']:
    ident=scene['id'];wav=VOICE/(ident+'-trim.wav')
    with wave.open(str(wav)) as w:duration=w.getnframes()/w.getframerate()
    text=scene['text'].replace('Math Mate','MathMate')
    if ident=='08-close':
        text='MathMate. Học có định hướng, làm bài có phản hồi.'
        run=subprocess.run(['C:/ffmpeg/bin/ffmpeg.exe','-hide_banner','-i',str(wav),'-af','silencedetect=noise=-38dB:d=0.12','-f','null','-'],capture_output=True,text=True,check=True)
        gaps=[];a=None
        for line in run.stderr.splitlines():
            if 'silence_start:' in line:a=float(line.split('silence_start:')[1].split()[0])
            if 'silence_end:' in line and a is not None:
                b=float(line.split('silence_end:')[1].split()[0]);gaps.append((a,b));a=None
        # Brand ends near one second; choose the longest nearby gap, then use PCM duration.
        middle=max((g for g in gaps if .45<g[0]<1.8),key=lambda g:g[1]-g[0])
        initial=gaps[0][1] if gaps and gaps[0][0]==0 else .08
        tail=next((g[0] for g in reversed(gaps) if duration-g[1]<.03),duration-.08)
        spans[ident]=[(initial,middle[0]),(middle[1],tail)]
    sentences=re.split(r'(?<=[.!?])\s+',text)
    assert len(sentences)==len(spans[ident]),(ident,len(sentences),len(spans[ident]))
    for sentence,(start,end) in zip(sentences,spans[ident]):
        assert 0<=start<end<=duration+.04,(ident,start,end,duration)
        pieces=chunks(sentence);total=sum(len(p.split()) for p in pieces);cursor=start
        for piece in pieces:
            segment=(end-start)*len(piece.split())/total
            offset=scene['start']+scene['lead']
            rows.append({'startMs':round((offset+cursor)*1000),'endMs':round((offset+cursor+segment)*1000),'text':piece})
            cursor+=segment
    checks.append({'id':ident,'audioSeconds':round(duration,4),'sentenceAnchors':spans[ident]})
assert all(0<=x['startMs']<x['endMs']<=180000 and len(x['text'])<=80 for x in rows)
assert all(a['endMs']<=b['startMs'] for a,b in zip(rows,rows[1:]))
assert not any('Coach Learning' in x['text'] or 'Math Mate' in x['text'] or '?' in x['text'] for x in rows)
(ROOT/'public/captions.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
(ROOT/'out').mkdir(exist_ok=True)
srt='\n\n'.join(f"{i}\n{stamp(x['startMs'])} --> {stamp(x['endMs'])}\n"+'\n'.join(textwrap.wrap(x['text'],width=43,break_long_words=False,break_on_hyphens=False)) for i,x in enumerate(rows,1))+'\n'
(ROOT/'out/MathMate-Demo.srt').write_text(srt,encoding='utf8')
(ROOT/'caption-qa.json').write_text(json.dumps({'captionCount':len(rows),'nonOverlapping':True,'maxCharacters':max(len(x['text']) for x in rows),'maxEndMs':max(x['endMs'] for x in rows),'timingMethod':'Manual sentence matching to actual waveform silence; proportional text units within split long sentences; unpaced actual start+lead','scenes':checks},ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'captions':len(rows),'maxEndMs':max(x['endMs'] for x in rows),'nonOverlapping':True}))
