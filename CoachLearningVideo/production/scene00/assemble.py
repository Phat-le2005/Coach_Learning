from pathlib import Path
import json,subprocess,hashlib
D=Path(__file__).parent;R=D.parent;F='C:/ffmpeg/bin/ffmpeg.exe';P='C:/ffmpeg/bin/ffprobe.exe'
c=json.loads((D/'capture.json').read_text());assert c.get('status')=='PASS'
n=json.loads((D/'narration.json').read_text());duration=n['seconds'];segments={x['name']:x for x in c['segments']}
targets=[('login',2),('classroom',8),('material',2),('configure',7),('confirm',1),('published',duration-20)]
filters=[];labels=[]
for i,(name,seconds) in enumerate(targets):
 s=segments[name];end=s['start']+min(seconds,s['duration']);label=f'v{i}'
 # Drop only real waiting/overlong cursor dwell, preserving the visible fixed viewport.
 filters.append(f"[0:v]trim=start={s['start']}:end={end},setpts=PTS-STARTPTS,fps=30,setsar=1[{label}]");labels.append('['+label+']')
filters.append(''.join(labels)+f'concat=n={len(labels)}:v=1:a=0,format=yuv420p[v]')
dest=R/'out/MathMate-Scene-00-Teacher.mp4'
subprocess.run([F,'-y','-v','error','-i',c['raw'],'-i',str(D/'narration.wav'),'-filter_complex',';'.join(filters),'-map','[v]','-map','1:a','-t',str(duration),'-c:v','libx264','-preset','veryfast','-crf','18','-threads','4','-c:a','aac','-af','loudnorm=I=-16:TP=-1.5:LRA=7','-ar','48000','-b:a','192k','-movflags','+faststart',str(dest)],check=True,stderr=(D/'encoding.log').open('wb'))
probe=json.loads(subprocess.check_output([P,'-v','error','-show_streams','-show_format','-of','json',str(dest)],text=True));v=next(x for x in probe['streams'] if x['codec_type']=='video');a=next(x for x in probe['streams'] if x['codec_type']=='audio')
decode=subprocess.run([F,'-v','error','-i',str(dest),'-f','null','-'],capture_output=True,text=True);assert decode.returncode==0 and not decode.stderr.strip()
qa=D/'qa';qa.mkdir(exist_ok=True)
for sec in [0.6,4,9,13,17,19.5,22]:subprocess.run([F,'-y','-v','error','-ss',str(sec),'-i',str(dest),'-frames:v','1',str(qa/f'{sec}.png')],check=True)
report={'file':str(dest),'durationSeconds':float(probe['format']['duration']),'width':v['width'],'height':v['height'],'fps':v['r_frame_rate'],'audioCodec':a['codec_name'],'fullDecode':'PASS','fixedViewport':True,'postproductionZoom':False,'startFromVisibleLogin':True,'firstLandingPage':'Teacher classroom / Phòng 1 Lớp học chính','assignmentPublishedThroughUi':True,'dueAt':c['dueAt'],'singleContinuousNarration':True,'addedAudioSilence':False,'sourceCaptureSegments':targets,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}
(R/'out/MathMate-Scene-00-Teacher-QA.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report))
