// Repository-only QA; Node + frontend's @playwright/test. Not a training dependency.
// node train/comer/tests/browser_smoke.mjs <candidate-directory> <report.json>
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const require=createRequire(path.join(repo,'frontend/package.json'));
const {chromium}=require('@playwright/test');
const candidate=path.resolve(process.argv[2]),reportPath=path.resolve(process.argv[3]);
const assets=path.join(repo,'frontend/public/ocr');
const server=http.createServer(async(req,res)=>{
  try{
    if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>CoMER QA</title>');return;}
    const root=req.url.startsWith('/ocr/')?assets:candidate;
    const relative=decodeURIComponent(req.url.replace(/^\/(ocr|candidate)\//,''));
    const target=path.resolve(root,relative);
    if(!target.startsWith(root+path.sep))throw Error('Path escape');
    res.setHeader('Content-Type',target.endsWith('.mjs')||target.endsWith('.js')?'text/javascript':target.endsWith('.wasm')?'application/wasm':'application/octet-stream');
    res.end(await fs.readFile(target));
  }catch{res.statusCode=404;res.end('Not found');}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true,
  ...(process.env.COMER_BROWSER_CHANNEL?{channel:process.env.COMER_BROWSER_CHANNEL}:{})});
try{
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const result=await page.evaluate(async()=>{
    const ort=await import('/ocr/runtime/ort.wasm.min.mjs');
    const core=await import('/ocr/ink-on/core.js');
    ort.env.wasm.wasmPaths='/ocr/runtime/';ort.env.wasm.numThreads=1;
    const vocab=await (await fetch('/candidate/vocab.json')).json();
    const exists=await fetch('/candidate/encoder_int8.onnx',{method:'HEAD'});
    const suffix=exists.ok?'_int8':'';
    const engine=new core.InferenceEngine({encoderUrl:`/candidate/encoder${suffix}.onnx`,
      decoderUrl:`/candidate/decoder${suffix}.onnx`,beamWidth:3,maxDecodeSteps:16,executionProvider:'wasm'});
    await engine.init();
    const line=(x1,y1,x2,y2)=>({lineWidth:5,points:Array.from({length:20},(_,i)=>({x:x1+(x2-x1)*i/19,y:y1+(y2-y1)*i/19}))});
    const narrow=[line(20,20,65,90),line(65,20,20,90)];
    const wide=[...narrow,line(110,55,145,55),line(128,35,128,75),line(180,20,225,90),line(225,20,180,90)];
    const cases=[];
    for(const [name,strokes] of [['narrow',narrow],['wide',wide]]){
      const input=core.preprocessStrokes(strokes);
      const pred=await engine.recognize(input,vocab,'expression');
      if(!Number.isFinite(pred.totalMs)||!Array.isArray(pred.tokenIds))throw Error('Invalid prediction result');
      cases.push({name,height:input.height,width:input.width,beam:3,...pred});
    }
    return{status:'PASS',scope:'headless Chromium, ORT WASM, synthetic geometry; no accuracy or device benchmark claim',cases};
  });
  if(errors.length)throw Error(errors.join('\n'));
  await fs.mkdir(path.dirname(reportPath),{recursive:true});await fs.writeFile(reportPath,JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result));
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
