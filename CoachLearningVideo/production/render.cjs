const fs=require('fs'),path=require('path'),cp=require('child_process');
const {bundle}=require('@remotion/bundler');
const {selectComposition,renderStill,renderMedia}=require('@remotion/renderer');
const ROOT=__dirname;
(async()=>{
 const mode=process.argv[2]||'still';
 const source=JSON.parse(fs.readFileSync(path.join(ROOT,'src/manifest.json'),'utf8'));
 const missing=source.filter(s=>!fs.existsSync(path.join(ROOT,'public',s.file))).map(s=>s.file);
 for(const file of ['audio/narration.mp3','footage/mobile.mp4','stills/feedback.png'])if(!fs.existsSync(path.join(ROOT,'public',file)))missing.push(file);
 if(mode!=='still'&&missing.length)throw Error('Missing real footage: '+missing.join(', '));
 if(mode!=='still'&&!JSON.parse(fs.readFileSync(path.join(ROOT,'public/captions.json'),'utf8')).length)throw Error('Timed captions are missing.');
 for(const shot of source){const file=path.join(ROOT,'public',shot.file);if(fs.existsSync(file)){
  const duration=Number(cp.execFileSync('C:/ffmpeg/bin/ffprobe.exe',['-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',file],{encoding:'utf8'}));
  shot.sourceDuration=duration;
  if(shot.id==='handwriting')shot.rate=Math.max(1,(duration-shot.trim)/shot.duration);
 }}
 fs.writeFileSync(path.join(ROOT,'src/manifest.json'),JSON.stringify(source,null,2));
 fs.mkdirSync(path.join(ROOT,'out'),{recursive:true});
 const serveUrl=await bundle({entryPoint:path.join(ROOT,'src/index.tsx'),publicDir:path.join(ROOT,'public')});
 const composition=await selectComposition({serveUrl,id:'CoachLearningDemo'});
 if(mode==='render'||mode==='patch'){
  const frameRange=mode==='patch'?[Number(process.argv[3]||990),Number(process.argv[4]||1469)]:undefined;
  await renderMedia({serveUrl,composition,codec:'h264',audioCodec:'aac',outputLocation:path.join(ROOT,mode==='patch'?'out/theory-patch.mp4':'out/MathMate-Demo-1080p.mp4'),...(frameRange?{frameRange}:{}),crf:18,concurrency:2,onProgress:p=>{const v=Math.floor(p.progress*100);if(v%10===0&&v!==global.lastPrinted){global.lastPrinted=v;console.log('Render '+v+'%');}}});
  console.log('Rendered MP4');
 }else{
  const frames=process.argv.slice(3).map(Number);for(const frame of frames.length?frames:[0,5370]){
   await renderStill({serveUrl,composition,frame,output:path.join(ROOT,`out/frame-${frame}.png`)});console.log('Rendered still '+frame);
  }
 }
})().catch(e=>{console.error(e.stack||e.message);process.exitCode=1});
