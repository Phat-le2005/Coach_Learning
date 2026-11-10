"""Replace exactly frames 990..1469; preserve the complete approved audio stream."""
from pathlib import Path
import subprocess,json
R=Path(__file__).parent;D=R/'out';source=D/'MathMate-Demo-1080p.mp4';patch=D/'theory-patch.mp4';dest=D/'MathMate-Demo-finalizing.mp4'
if not patch.exists():raise SystemExit('Theory patch is not ready')
ff='C:/ffmpeg/bin/ffmpeg.exe';probe='C:/ffmpeg/bin/ffprobe.exe'
meta=json.loads(subprocess.check_output([probe,'-v','error','-show_entries','stream=width,height,r_frame_rate:format=duration','-of','json',str(patch)],text=True))
if abs(float(meta['format']['duration'])-16)>.1:raise SystemExit('Patch duration is not 16 seconds')
filters='[0:v]split=2[p][q];[p]trim=end_frame=990,setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[q]trim=start_frame=1470,setpts=PTS-STARTPTS[c];[a][b][c]concat=n=3:v=1:a=0,format=yuv420p[v]'
subprocess.run([ff,'-y','-i',str(source),'-i',str(patch),'-filter_complex',filters,'-map','[v]','-map','0:a:0','-c:v','libx264','-preset','veryfast','-crf','18','-threads','4','-c:a','copy','-movflags','+faststart',str(dest)],stdout=subprocess.DEVNULL,stderr=(D/'splice-encoding.log').open('wb'),check=True)
out=json.loads(subprocess.check_output([probe,'-v','error','-show_entries','format=duration','-of','json',str(dest)],text=True))
if abs(float(out['format']['duration'])-180)>.15:raise SystemExit('Unexpected final duration; original preserved')
backup=R/'private-render/original-before-theory-fix.mp4';backup.parent.mkdir(exist_ok=True)
if backup.exists():raise SystemExit('Backup already exists; inspect before replacing')
source.replace(backup);dest.replace(source)
(D/'theory-fix-report.json').write_text(json.dumps({'replacedFrameRange':[990,1469],'replacementSeconds':16,'globalAudioStreamCopied':True,'originalPreservedPrivately':str(backup),'finalFile':str(source)},indent=2),encoding='utf8')
print('Theory scene replaced frame-accurately; original audio stream preserved.')
