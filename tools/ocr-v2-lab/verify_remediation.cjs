#!/usr/bin/env node
// Real Next + local Paddle + bundled CoMER. No prediction response interception.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'.tmp/tri-ocr-v2-remediation');
const {chromium,expect}=require(path.join(root,'frontend/node_modules/@playwright/test'));
const {validateQaHarnessEnv}=require(path.join(root,'frontend/.test-build-run/e2e/qa-harness-safety.js'));
const cfg=validateQaHarnessEnv(process.env,path.join(root,'.tmp/tri-ocr-e2e/.qa-e2e.env'));
const session=JSON.parse(fs.readFileSync(path.join(root,'.tmp/tri-ocr-v2-runtime/session.json')));
const write=(file,data)=>fs.writeFileSync(path.join(out,file),JSON.stringify(data,null,2));
const samples=process.env.OCR_REMEDIATION_SAMPLES?.split(',')??['user-equation-14','user-mixed-71','quadratic','derivative','sigma','old-native-integral','stress-nearby-lines','stress-two-columns'];
const profiles=process.env.OCR_REMEDIATION_PROFILES?.split(',')??['LAYOUT_M','V2','GEOMETRY','HYBRID'];
const inputFile=name=>name.startsWith('user-')?path.join(out,name+'.capture.json'):path.join(root,name.startsWith('stress-')?'.tmp/tri-ocr-v2-e2e':'.tmp/tri-ocr-root-cause',name+'.capture.json');
const results=[],network=[],consoleMessages=[],errors=[];let browser;
const hash=f=>crypto.createHash('sha256').update(fs.readFileSync(path.join(root,f))).digest('hex');
const sourceFiles=['frontend/src/features/math-workspace/utils/ocr-v2-scope-candidates.ts','frontend/src/features/math-workspace/utils/ocr-v2-experimental.ts','frontend/src/features/math-workspace/components/OcrV2ExperimentalPanel.tsx','frontend/src/features/math-workspace/components/OcrV2LocalCanvas.tsx','frontend/src/features/math-workspace/utils/ocr-model-diagnostics.ts'];
const hashes=()=>Object.fromEntries(sourceFiles.map(f=>[f,hash(f)]));
(async()=>{
 fs.mkdirSync(out,{recursive:true});fs.mkdirSync(path.join(out,'screenshots'),{recursive:true});const initialHashes=hashes();
 write('browser-manifest.json',{startedAt:new Date().toISOString(),sourceHashes:initialHashes,inputs:samples.map(n=>({sample:n,sha256:crypto.createHash('sha256').update(fs.readFileSync(inputFile(n))).digest('hex')})),method:'ACTUAL_NEXT_BROWSER; no model/preprocessing/mapping mocks; synthetic layouts labeled separately'});
 browser=await chromium.launch({channel:'chrome',headless:true});const context=await browser.newContext({viewport:{width:1850,height:1450},acceptDownloads:true});
 await context.route('**/*',route=>{const r=route.request(),u=new URL(r.url());if(!['localhost','127.0.0.1'].includes(u.hostname)){network.push({blockedExternal:u.origin});return route.abort();}if(['POST','PUT','PATCH','DELETE'].includes(r.method())&&!u.pathname.startsWith('/__nextjs')){const allowed=/auth\/(login|refresh)/.test(u.pathname)||u.pathname==='/api/ocr-v2-lab';network.push({method:r.method(),path:u.pathname,allowed});if(!allowed)return route.abort();}return route.continue();});
 const login=await context.newPage();await login.goto(session.url+'/login');await login.locator('input[type=email]').fill('qa.ocr.e2e.isolated@edums.edu.vn');await login.locator('input[type=password]').fill(cfg.password);await login.locator('button[type=submit]').click();await login.waitForURL(u=>!u.pathname.startsWith('/login'));await login.close();
 for(const name of samples)for(const profile of profiles){const page=await context.newPage();page.on('pageerror',e=>errors.push({name,profile,error:e.message}));page.on('console',m=>{if(['warning','error'].includes(m.type()))consoleMessages.push({sample:name,profile,type:m.type(),text:m.text()});});
  await page.goto(session.url+'/ocr-v2-lab');await page.getByLabel('Import capture V2').setInputFiles(inputFile(name));await page.getByLabel('Nguồn nét V2').selectOption(name.startsWith('stress-')?'SYNTHETIC_INK':name.startsWith('user-')?'IMPORTED_CAPTURE':'HANDOFF_CAPTURE');await page.getByLabel('Chế độ OCR V2').selectOption(profile);
  const started=Date.now();await page.getByTestId('v2-run').click();await expect(page.getByTestId('ocr-v2-panel')).toHaveAttribute('aria-busy','false',{timeout:180000});await expect(page.getByTestId('v2-ir-status')).toBeVisible();
  await page.getByRole('checkbox').last().check();const pending=page.waitForEvent('download',d=>d.suggestedFilename()==='ocr-v2-package.json');await page.getByTestId('v2-export').click();const file=path.join(out,`${name}-${profile}.package.json`);await(await pending).saveAs(file);const pkg=JSON.parse(fs.readFileSync(file));
  assert.deepEqual(pkg.integrity.missing,[]);assert.deepEqual(pkg.integrity.duplicateOwnership,[]);assert.deepEqual(pkg.integrity.unknown,[]);assert.deepEqual(pkg.projection.steps,[]);assert.equal(pkg.projection.submitPayload,null);assert.equal(pkg.projection.readyToSubmit,false);
  const capture=JSON.parse(fs.readFileSync(inputFile(name)));assert.deepEqual(pkg.source.strokes,capture.strokes);
  const active=pkg.scopes.filter(s=>s.strokeIds.length),row={sample:name,profile,inputKind:name.startsWith('stress-')?'SYNTHETIC_LAYOUT':'REAL_HUMAN_INK',sourceStrokeCount:capture.strokes.length,rawLabels:pkg.perception.regions.map(r=>r.label),activeScopes:active.map(s=>({id:s.id,kind:s.kind,count:s.strokeIds.length,strokeIds:s.strokeIds})),integrity:pkg.integrity,inferenceCount:pkg.modelInferenceCalls,latencyMs:Date.now()-started,constructionMs:pkg.construction?.durationMs,detectorTimings:pkg.perception.timings,raw:pkg.recognition.map(r=>({scopeId:r.scopeId,strokeIds:r.strokeIds,raw:r.diagnostic?.rawLatex,selected:r.wrapperLatex,error:r.error,timings:r.diagnostic?.timings})),routing:pkg.routingOutcomes,labelStatus:name==='user-equation-14'?'USER_CONFIRMED_TRANSCRIPT_AND_FULL_SCOPE':'MISSING_INDEPENDENT_HUMAN_GROUP_LABELS'};
  if(name==='user-equation-14'){
   row.fullScopeAutomatic=active.some(s=>s.kind==='MATH'&&s.strokeIds.length===capture.strokes.length);row.exactTranscript=Boolean(row.raw.find(r=>r.strokeIds.length===capture.strokes.length)?.raw?.replace(/\s/g,'')==='x^{2}+3x-4=0');
   if(profile==='HYBRID'||profile==='GEOMETRY'){assert.equal(row.fullScopeAutomatic,true);assert.ok(row.inferenceCount>=1);}
  }
  if(name==='user-mixed-71'&&(profile==='HYBRID'||profile==='GEOMETRY')){
   assert.ok(active.every(s=>s.strokeIds.length<capture.strokes.length));
   const proseIds=[...capture.strokes.slice(0,6),...capture.strokes.slice(22,26)].map(s=>s.id);
   row.proseRoutingCheck='ANALYST_VISUAL_STROKE_GROUPS; not independent metric GT';row.proseSentToComer=pkg.recognition.some(r=>r.strokeIds.some(id=>proseIds.includes(id)));
   assert.equal(row.proseSentToComer,false,'Vietnamese prose must remain outside automatic math scopes');
  }
  if(profile==='HYBRID'&&name.startsWith('user-')){
   await page.screenshot({path:path.join(out,'screenshots',name+'-hybrid.png'),fullPage:true});
   const first=active.find(s=>s.kind==='MATH');if(first){await page.getByRole('checkbox',{name:'Chọn nhóm unit-'+first.id,exact:true}).locator('..').getByRole('button').click();await page.getByTestId('v2-transcript').fill('x+1=3 \\Rightarrow x=5');await page.getByRole('button',{name:'Xác nhận nội dung / cấu trúc',exact:true}).click();await page.getByTestId('v2-run').click();await expect(page.getByTestId('ocr-v2-panel')).toHaveAttribute('aria-busy','false',{timeout:180000});await page.getByRole('checkbox',{name:'Chọn nhóm unit-'+first.id,exact:true}).locator('..').getByRole('button').click();await expect(page.getByTestId('v2-transcript')).toHaveValue('x+1=3 \\Rightarrow x=5');row.correctionRerun='VERIFIED';}
  }
  results.push(row);write('browser-results.json',results);console.log(JSON.stringify({sample:name,profile,scopes:active.map(s=>`${s.kind}:${s.strokeIds.length}`),calls:pkg.modelInferenceCalls,exact:row.exactTranscript,raw:row.raw.map(r=>r.raw)}));await page.close();
 }
 assert.equal(errors.length,0,JSON.stringify(errors));assert.equal(network.filter(n=>n.allowed===false).length,0);assert.deepEqual(hashes(),initialHashes,'Source changed during comparison run');
 write('browser-verification.json',{status:'COMPLETED_ACTUAL_BROWSER',runs:results.length,realInputs:samples.filter(n=>!n.startsWith('stress-')).length,syntheticLayouts:samples.filter(n=>n.startsWith('stress-')).length,modelMocks:0,applicationMutations:0,errors,network,sourceHashesUnchanged:true});write('browser-console.json',consoleMessages);
})().catch(e=>{write('browser-error.json',{error:e.stack,errors,network});console.error(e.stack);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();});
