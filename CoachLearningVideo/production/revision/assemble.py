import json,subprocess
from pathlib import Path
D=Path(__file__).parent;R=D.parent;OUT=R/'out';FF='C:/ffmpeg/bin/ffmpeg.exe'
def run(args):
 subprocess.run([FF,'-y','-v','error',*args],cwd=D,check=True,stderr=(D/'assembly-errors.log').open('ab'))
def ass(name,rows,chapter=None):
 head='[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,34,&H00FFFFFF,&H00FFFFFF,&H00192B21,&H00192B21,-1,0,0,0,100,100,0,0,3,12,0,2,100,100,80,1\nStyle: Chapter,Arial,22,&H00FFFFFF,&H00FFFFFF,&H00233E2B,&H00233E2B,-1,0,0,0,100,100,0,0,3,10,0,1,38,40,25,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
 def ts(ms):
  cs=round(ms/10);return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'
 for c in rows:head+=f"Dialogue: 0,{ts(c['startMs'])},{ts(c['endMs'])},Default,,0,0,0,,{c['text']}\n"
 if chapter:head+=f'Dialogue: 0,0:00:00.00,0:00:20.00,Chapter,,0,0,0,,{chapter}\n'
 (D/name).write_text(head,encoding='utf-8-sig')
ass('intro.ass',json.loads((D/'audio/intro-captions.json').read_text(encoding='utf8')))
ass('teacher.ass',json.loads((D/'audio/teacher00-captions.json').read_text(encoding='utf8')),'00  /  GIAO BÀI & THEO DÕI LỚP')
t=json.loads((D/'teacher-capture.json').read_text());s=json.loads((D/'student-ready.json').read_text());raw=t['teacherRaw']
# Three real capture intervals: material selection, dated assignment confirmation, received student card.
teacherfilter='[0:v]split=2[p][q];[p]trim=start=26.517:duration=3,setpts=PTS-STARTPTS[a];[q]trim=start=31.832:duration=9,setpts=PTS-STARTPTS[b];[1:v]trim=start='+str(s['start'])+':duration=8,setpts=PTS-STARTPTS[c];[a][b][c]concat=n=3:v=1:a=0,fps=30,subtitles=teacher.ass[v]'
run(['-i',raw,'-i',s['raw'],'-filter_complex',teacherfilter,'-map','[v]','-an','-c:v','libx264','-preset','veryfast','-crf','18','-threads','4','-pix_fmt','yuv420p',str(D/'teacher00.mp4')])
old=OUT/'MathMate-Demo-1080p.mp4'
# The chosen old opening artwork is retained with fresh problem-context voice and captions.
run(['-i',str(old),'-vf','trim=end=8,setpts=PTS*1.375,drawbox=x=0:y=930:w=1920:h=150:color=0x073e32:t=fill,subtitles=intro.ass,fps=30','-t','11','-an','-c:v','libx264','-preset','veryfast','-crf','18','-threads','4',str(D/'intro.mp4')])
filters='[0:v]split=2[x][y];[x]trim=start_frame=240:end_frame=990,setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[y]trim=start_frame=1470:end_frame=5400,setpts=PTS-STARTPTS[c];[2:v]setpts=PTS-STARTPTS[i];[3:v]setpts=PTS-STARTPTS[t];[i][t][a][b][c]concat=n=5:v=1:a=0,format=yuv420p[v];[4:a]apad,atrim=duration=11,asetpts=PTS-STARTPTS[ai];[5:a]apad,atrim=duration=20,asetpts=PTS-STARTPTS[at];[0:a]atrim=start=8:end=180,asetpts=PTS-STARTPTS[ao];[ai][at][ao]concat=n=3:v=0:a=1[a]'
dest=OUT/'MathMate-Demo-V2-1080p.mp4'
run(['-i',str(old),'-i',str(OUT/'theory-patch.mp4'),'-i',str(D/'intro.mp4'),'-i',str(D/'teacher00.mp4'),'-i',str(D/'audio/intro.wav'),'-i',str(D/'audio/teacher00.wav'),'-filter_complex',filters,'-map','[v]','-map','[a]','-c:v','libx264','-preset','veryfast','-crf','18','-threads','4','-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart',str(dest)])
print('Final V2 ready:',dest,flush=True)
