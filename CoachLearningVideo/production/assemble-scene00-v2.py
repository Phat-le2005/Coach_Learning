from pathlib import Path
import json,subprocess,re
R=Path(__file__).parent;D=R/'scene00-v2'
s=(R/'scene00/assemble.py').read_text(encoding='utf8')
s=s.replace("D=Path(__file__).parent;R=D.parent;", "R=Path(__file__).parent;D=R/'scene00-v2';")
s=s.replace("('classroom',8),('material',2),('configure',7),('confirm',1),('published',duration-20)","('classroom',18),('material',2),('configure',9),('confirm',1),('published',duration-32)")
s=s.replace('MathMate-Scene-00-Teacher.mp4','MathMate-Scene-00-Teacher-V2.mp4').replace('MathMate-Scene-00-Teacher-QA.json','MathMate-Scene-00-Teacher-V2-QA.json')
s=s.replace('for sec in [0.6,4,9,13,17,19.5,22]:','for sec in [0.6,5,15,19,23,27,31.5,34]:')
exec(compile(s,str(__file__),'exec'))
# Sidecar captions for the standalone clip. Approximate cue timing is proportional to spoken text.
meta=json.loads((D/'narration.json').read_text(encoding='utf8'));text=meta['text'];duration=meta['seconds'];sentences=re.findall(r'[^.!?]+[.!?]?',text)
chunks=[]
for sentence in sentences:
 words=sentence.strip().split();num=max(1,(len(sentence)+74)//75);size=(len(words)+num-1)//num
 for i in range(0,len(words),size):chunks.append(' '.join(words[i:i+size]))
weights=[len(t.split()) for t in chunks];at=.1;entries=[]
for text,weight in zip(chunks,weights):
 end=at+(duration-.3)*weight/sum(weights);entries.append({'startMs':round(at*1000),'endMs':round(end*1000),'text':text});at=end
def ts(ms):return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
(R/'out/MathMate-Scene-00-Teacher-V2.srt').write_text('\n\n'.join(f"{i+1}\n{ts(x['startMs'])} --> {ts(x['endMs'])}\n{x['text']}" for i,x in enumerate(entries)),encoding='utf8')
(D/'captions.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf8')
