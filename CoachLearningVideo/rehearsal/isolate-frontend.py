"""Read-only source snapshot for capture runtime, not a development checkout/worktree."""
import json,os,shutil,subprocess
from pathlib import Path
R=Path(__file__).parent;REPO=Path('D:/SGU/DuAn/Coach_Learning');DEST=R.parent/'capture-frontend'
p=json.loads((R/'private.json').read_text(encoding='utf-8'))
if DEST.exists():raise SystemExit('Capture snapshot already exists; preserve it and inspect.')
shutil.copytree(REPO/'frontend',DEST,ignore=shutil.ignore_patterns('node_modules','.next*','.test-build*','playwright-report','test-results','.env*','undefined'))
subprocess.run(['powershell','-NoProfile','-Command',"New-Item -ItemType Junction -Path 'C:/CoachLearningVideo/capture-frontend/node_modules' -Target 'D:/SGU/DuAn/Coach_Learning/frontend/node_modules' | Out-Null"],check=True)
env={'API_BASE_URL':'http://127.0.0.1:8050','AUTH_SESSION_SECRET':p['session_secret'],'SESSION_COOKIE_SECURE':'false','NEXT_PUBLIC_APP_URL':'http://127.0.0.1:3150','SELF_STUDY_PUBLISHED_SUBJECT_CODES':'MATH_G12','OCR_V2_EXPERIMENTAL':'0'}
(DEST/'.env.local').write_text(''.join(k+'='+v+'\n' for k,v in env.items()),encoding='utf-8')
revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
(R/'source-snapshot.json').write_text(json.dumps({'revision':revision,'kind':'capture runtime snapshot, not Git worktree','source':str(REPO/'frontend'),'path':str(DEST)},indent=2))
childEnv=os.environ.copy();childEnv.update(env)
proc=subprocess.Popen(['node',str(DEST/'node_modules/next/dist/bin/next'),'dev','--hostname','127.0.0.1','--port','3150'],cwd=DEST,env=childEnv,stdout=(R/'frontend.log').open('wb'),stderr=(R/'frontend-errors.log').open('wb'),creationflags=subprocess.CREATE_NO_WINDOW)
(R/'frontend.pid').write_text(str(proc.pid))
# Restore only our automatic include additions, preserving any concurrent source edit.
cfg=REPO/'frontend/tsconfig.json';before=(R/'tsconfig-before.json').read_bytes();now=json.loads(cfg.read_text());old=json.loads(before)
now['include']=[x for x in now.get('include',[]) if not x.startswith('.next-video-rehearsal/')]
if now==old:cfg.write_bytes(before)
print('Isolated capture frontend started on 3150; application checkout and its environment preserved.')
