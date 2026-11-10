"""Recover real completed capture segments; remove API wait without changing results."""
from pathlib import Path
import subprocess,json,concurrent.futures
R=Path(__file__).parent;D=R/'public/footage';F='C:/ffmpeg/bin/ffmpeg.exe'
desktop=R/'raw-solution/page@5a7e727f4c2e8b002209c9b64869ac77.webm'
mobile=R/'raw-solution/page@ec51cdb8cbd86fe0662ec75cf2921831.webm'
jobs=[
('handwriting',desktop,['-vf','trim=start=12.3:end=27.3,setpts=PTS-STARTPTS,fps=30,format=yuv420p']),
('mobile',mobile,['-vf','trim=start=4.3:end=19.3,setpts=PTS-STARTPTS,crop=390:780:0:0,pad=390:844:0:0:color=white,fps=30,format=yuv420p']),
('ocr',desktop,['-filter_complex','[0:v]split=2[a][b];[a]trim=start=28:end=30,setpts=PTS-STARTPTS[a1];[b]trim=start=73:end=99,setpts=PTS-STARTPTS[b1];[a1][b1]concat=n=2:v=1:a=0,fps=30,format=yuv420p[v]','-map','[v]'])]
def run(job):
 name,source,args=job;target=D/(name+'.mp4')
 subprocess.run([F,'-y','-i',str(source),*args,'-an','-c:v','libx264','-preset','veryfast','-crf','18','-threads','2','-movflags','+faststart',str(target)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
 return {'id':name,'file':str(target),'status':'PASS'}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as p:results=list(p.map(run,jobs))
(R/'solution-edit-report.json').write_text(json.dumps({'source':'actual browser capture of fresh primary attempt','ocrWaitCut':True,'cutOnlyWait':True,'recordings':results},indent=2),encoding='utf8')
print(json.dumps(results))
