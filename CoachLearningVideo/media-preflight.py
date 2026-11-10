"""Validate local encoding, timed subtitles and waiting-segment speed tools."""
import json
from pathlib import Path
import subprocess

qa=Path(__file__).parent/'toolchain/qa'
capture=json.loads((qa/'capture-report.json').read_text())
ffmpeg='C:/ffmpeg/bin/ffmpeg.exe'
ffprobe='C:/ffmpeg/bin/ffprobe.exe'
command=[ffmpeg,'-y','-i',capture['recording'],'-vf',"fps=30,subtitles=captions.srt:force_style='Fontname=Arial,Fontsize=28',format=yuv420p",'-c:v','libx264','-crf','18','-an','-movflags','+faststart','capture-check.mp4']
r=subprocess.run(command,cwd=qa,capture_output=True)
(qa/'encode.log').write_bytes(r.stderr)
r.check_returncode()
subprocess.run([ffmpeg,'-y','-i','capture-check.mp4','-vf','setpts=0.5*PTS,fps=30','-c:v','libx264','-an','speed-check.mp4'],cwd=qa,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
def probe(name):
 return json.loads(subprocess.check_output([ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(qa/name)]))
video=probe('capture-check.mp4'); speed=probe('speed-check.mp4')
v=video['streams'][0]
report={'codec':v['codec_name'],'width':v['width'],'height':v['height'],'fps':v['r_frame_rate'],'pixelFormat':v['pix_fmt'],'seconds':float(video['format']['duration']),'acceleratedSeconds':float(speed['format']['duration']),'subtitleBurn':'PASS'}
if (qa/'voice-probe.wav').exists():
 subprocess.run([ffmpeg,'-y','-i',str(qa/'voice-probe.wav'),'-c:a','libmp3lame','-q:a','2',str(qa/'voice-probe.mp3')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
 report['voiceMp3']='PASS'
(qa/'media-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
assert report['width']==1920 and report['height']==1080 and report['fps']=='30/1'
