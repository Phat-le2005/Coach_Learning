#!/usr/bin/env node
const fs=require('node:fs'),path=require('node:path'),net=require('node:net'),crypto=require('node:crypto'),{spawn,execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..'),runtime=path.join(root,'.tmp/tri-ocr-v2-runtime'),out=path.join(root,'.tmp/tri-ocr-v2-e2e'),sessionFile=path.join(runtime,'session.json');
const python=process.platform==='win32'?path.join(runtime,'venv/Scripts/python.exe'):path.join(runtime,'venv/bin/python');
async function available(start){for(let port=start;port<start+20;port++){try{await new Promise((resolve,reject)=>{const s=net.createServer();s.once('error',reject);s.listen(port,'127.0.0.1',()=>s.close(resolve));});return port;}catch{}}throw Error('No free local experiment port');}
function launch(exe,args,cwd,env,name){const fd=fs.openSync(path.join(out,`${name}.log`),'a');const p=spawn(exe,args,{cwd,env,windowsHide:true,detached:true,stdio:['ignore',fd,fd]});fs.closeSync(fd);p.unref();return p.pid;}
async function ready(url,headers={}){for(let i=0;i<120;i++){try{const r=await fetch(url,{headers,signal:AbortSignal.timeout(2500)});if(r.ok)return;}catch{}await new Promise(r=>setTimeout(r,500));}throw Error(`Not ready: ${url}`);}
async function main(){
 fs.mkdirSync(runtime,{recursive:true});fs.mkdirSync(out,{recursive:true});
 if(process.argv[2]==='restart-sidecar'){
  const session=JSON.parse(fs.readFileSync(sessionFile));if(session.root!==root)throw Error('Session root mismatch');const entry=session.processes[0];
  if(process.platform==='win32'){
   const command=execFileSync('powershell.exe',['-NoProfile','-Command',`(Get-CimInstance Win32_Process -Filter "ProcessId = ${Number(entry.pid)}").CommandLine`],{encoding:'utf8',windowsHide:true});if(!command.includes('ocr-v2-lab'))throw Error('PID identity mismatch');execFileSync('taskkill.exe',['/PID',String(entry.pid),'/T','/F'],{stdio:'pipe',windowsHide:true});
  }else process.kill(-entry.pid,'SIGTERM');
  const token=fs.readFileSync(path.join(runtime,'service-token.txt'),'utf8').trim();const pid=launch(python,[path.join(__dirname,'service.py'),'--port',String(session.sidecarPort)],root,{...process.env,OCR_V2_SIDECAR_TOKEN:token},'sidecar');session.processes[0]={pid,marker:'ocr-v2-lab'};fs.writeFileSync(sessionFile,JSON.stringify(session,null,2));await ready(`http://127.0.0.1:${session.sidecarPort}/health`,{Authorization:`Bearer ${token}`});return console.log('SIDECAR_RESTARTED; frontend preserved');
 }
 if(process.argv[2]==='stop'){
  if(!fs.existsSync(sessionFile))return console.log('No managed session');const s=JSON.parse(fs.readFileSync(sessionFile));if(s.root!==root)throw Error('Session root mismatch');
  for(const entry of s.processes){
   try{if(process.platform==='win32'){const text=execFileSync('powershell.exe',['-NoProfile','-Command',`(Get-CimInstance Win32_Process -Filter "ProcessId = ${Number(entry.pid)}").CommandLine`],{encoding:'utf8',windowsHide:true});if(!text.includes(entry.marker))throw Error('PID identity mismatch');execFileSync('taskkill.exe',['/PID',String(entry.pid),'/T','/F'],{stdio:'pipe',windowsHide:true});}else{process.kill(-entry.pid,'SIGTERM');}}catch(e){console.log(`Process ${entry.pid}: ${e.message.includes('mismatch')?'identity mismatch; preserved':'already stopped or could not stop'}`);}
  } fs.renameSync(sessionFile,path.join(runtime,`stopped-${Date.now()}.json`));return;
 }
 if(fs.existsSync(sessionFile)){const old=JSON.parse(fs.readFileSync(sessionFile));try{await fetch(old.url+'/login',{signal:AbortSignal.timeout(1000)});return console.log(JSON.stringify({status:'ALREADY_RUNNING',url:old.url,labUrl:old.url+'/ocr-v2-lab'}));}catch{throw Error('Stale session file; run managed stop before restarting');}}
 if(!fs.existsSync(python))throw Error('Run setup.ps1 first');
 const tokenFile=path.join(runtime,'service-token.txt');if(!fs.existsSync(tokenFile))fs.writeFileSync(tokenFile,crypto.randomBytes(32).toString('hex'));
 const token=fs.readFileSync(tokenFile,'utf8').trim(),sidecarPort=await available(8014),frontendPort=await available(3014);
 const env={...process.env,OCR_V2_SIDECAR_TOKEN:token,OCR_V2_SIDECAR_URL:`http://127.0.0.1:${sidecarPort}`,OCR_V2_EXPERIMENTAL:'1',NEXT_PUBLIC_OCR_V2_EXPERIMENTAL:'1',NEXT_DIST_DIR:'.next-ocr-v2-dev',API_BASE_URL:process.env.API_BASE_URL||'http://127.0.0.1:8000'};
 const service=path.join(__dirname,'service.py'),next=path.join(root,'frontend/node_modules/next/dist/bin/next');
 const sidecarPid=launch(python,[service,'--port',String(sidecarPort)],root,env,'sidecar');
 const session={root,startedAt:new Date().toISOString(),url:`http://localhost:${frontendPort}`,sidecarPort,frontendPort,processes:[{pid:sidecarPid,marker:'ocr-v2-lab'}]};
 fs.writeFileSync(sessionFile,JSON.stringify(session,null,2));
 await ready(`http://127.0.0.1:${sidecarPort}/health`,{Authorization:`Bearer ${token}`});
 const frontendPid=launch(process.execPath,[next,'dev','--hostname','localhost','--port',String(frontendPort)],path.join(root,'frontend'),env,'frontend');session.processes.push({pid:frontendPid,marker:next});fs.writeFileSync(sessionFile,JSON.stringify(session,null,2));
 await ready(session.url+'/login');console.log(JSON.stringify({status:'READY',url:session.url,labUrl:session.url+'/ocr-v2-lab',sidecarPort,backend:env.API_BASE_URL,token:'PRIVATE_LOCAL_FILE_NOT_PRINTED'},null,2));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
