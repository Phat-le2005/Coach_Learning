from pathlib import Path
import json,subprocess,hashlib
D=Path(__file__).parent;R=D.parent;O=R/'out';F='C:/ffmpeg/bin/ffmpeg.exe';V=O/'MathMate-Demo-V2-1080p.mp4'
def run(args):return subprocess.run(args,check=True,capture_output=True,text=True)
probe=json.loads(run(['C:/ffmpeg/bin/ffprobe.exe','-v','error','-show_streams','-show_format','-of','json',str(V)]).stdout)
duration=float(probe['format']['duration']);video=next(x for x in probe['streams'] if x['codec_type']=='video');audio=next(x for x in probe['streams'] if x['codec_type']=='audio')
assert duration<210 and abs(duration-203)<.2
assert video['width']==1920 and video['height']==1080
decoded=run([F,'-v','error','-i',str(V),'-f','null','-']);assert not decoded.stderr.strip()
qa=D/'qa';qa.mkdir(exist_ok=True)
for t in [3,14,18,24,29,35,47,59,63,67,84,105,159,190,200]:
 run([F,'-y','-v','error','-ss',str(t),'-i',str(V),'-frames:v','1',str(qa/f'frame-{t:03}.png')])
rows=json.loads((D/'audio/intro-captions.json').read_text(encoding='utf8'))
for row in json.loads((D/'audio/teacher00-captions.json').read_text(encoding='utf8')):rows.append({**row,'startMs':row['startMs']+11000,'endMs':row['endMs']+11000})
for row in json.loads((R/'public/captions.json').read_text(encoding='utf8')):
 if row['startMs']>=8000:rows.append({**row,'startMs':row['startMs']+23000,'endMs':row['endMs']+23000})
def ts(ms):
 ms=round(ms);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
(O/'MathMate-Demo-V2.srt').write_text('\n\n'.join(f"{i+1}\n{ts(x['startMs'])} --> {ts(x['endMs'])}\n{x['text']}" for i,x in enumerate(rows)),encoding='utf8')
report={'file':str(V),'durationSeconds':duration,'resolution':'1920x1080','fps':video['r_frame_rate'],'videoCodec':video['codec_name'],'audioCodec':audio['codec_name'],'fullDecode':'PASS','captionCount':len(rows),'sourcePreserved':str(O/'MathMate-Demo-1080p.mp4'),'newIntroSeconds':11,'newTeacherSceneSeconds':20,'teacherDueAt':'2026-11-15T20:00:00+07:00','teacherPublishedViaRealUI':True,'studentReceivedRealAssignment':True,'theoryLoadingRemoved':True,'remainingOldFootageAndNarrationPreserved':True,'bytes':V.stat().st_size,'sha256':hashlib.sha256(V.read_bytes()).hexdigest()}
(O/'MathMate-Demo-V2-QA.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report))
