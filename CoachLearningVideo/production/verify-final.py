"""Technical output QA and visual review sheet for the delivered MP4."""
from pathlib import Path
import hashlib,json,subprocess
R=Path(__file__).parent;OUT=R/'out';VIDEO=OUT/'MathMate-Demo-1080p.mp4'
FF='C:/ffmpeg/bin/ffmpeg.exe';PROBE='C:/ffmpeg/bin/ffprobe.exe'
if not VIDEO.exists():raise SystemExit('Final MP4 is not present yet')
probe=json.loads(subprocess.check_output([PROBE,'-v','error','-show_streams','-show_format','-of','json',str(VIDEO)],text=True))
v=next(s for s in probe['streams'] if s['codec_type']=='video');a=next(s for s in probe['streams'] if s['codec_type']=='audio')
duration=float(probe['format']['duration']);caps=json.loads((R/'public/captions.json').read_text(encoding='utf8'))
checks={'durationAbout180Seconds':abs(duration-180)<.15,'resolution1080p':v['width']==1920 and v['height']==1080,'fps30':v['r_frame_rate']=='30/1','videoH264':v['codec_name']=='h264','audioAAC':a['codec_name']=='aac','captionsPresent':len(caps)>0,'captionTimesValid':all(0<=c['startMs']<c['endMs']<=180000 for c in caps),'captionsNonOverlapping':all(x['endMs']<=y['startMs'] for x,y in zip(caps,caps[1:]))}
decode=subprocess.run([FF,'-v','error','-i',str(VIDEO),'-f','null','-'],capture_output=True,text=True)
checks['fullVideoDecode']=decode.returncode==0 and not decode.stderr.strip()
frames=[2,12,23,39,60,82,94,112,136,154,167,177]
qa=OUT/'qa';qa.mkdir(exist_ok=True)
for t in frames:
    subprocess.run([FF,'-y','-ss',str(t),'-i',str(VIDEO),'-frames:v','1',str(qa/f'frame-{t:03}.png')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
report={'checks':checks,'pass':all(checks.values()),'file':str(VIDEO),'durationSeconds':duration,'bytes':VIDEO.stat().st_size,'sha256':hashlib.sha256(VIDEO.read_bytes()).hexdigest(),'video':{'codec':v['codec_name'],'width':v['width'],'height':v['height'],'fps':v['r_frame_rate']},'audio':{'codec':a['codec_name'],'sampleRate':a['sample_rate'],'channels':a['channels']},'captionCount':len(caps),'visualReviewFrames':frames,'contentEvidence':{'brand':'MathMate','actualUiRecordings':True,'handwriting':'two browsers, pointer replay, synchronized real persisted strokes','ocr':'real Gemini result, wait shortened','feedback':'real answer-grounded provisional AI feedback; no official score','teacher':'same new assignment, actual submitted work awaiting teacher review'},'audioSelection':json.loads((R/'audio-selection.json').read_text())}
(OUT/'FINAL-QA.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'pass':report['pass'],'checks':checks,'seconds':duration,'megabytes':round(VIDEO.stat().st_size/1024**2,1)}))
