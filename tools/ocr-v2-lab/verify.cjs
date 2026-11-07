#!/usr/bin/env node
// Actual Next UI + loopback Paddle + real browser CoMER, isolated from grading APIs.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'.tmp/tri-ocr-v2-e2e'),session=JSON.parse(fs.readFileSync(path.join(root,'.tmp/tri-ocr-v2-runtime/session.json')));
const {chromium,expect}=require(path.join(root,'frontend/node_modules/@playwright/test'));
const {validateQaHarnessEnv}=require(path.join(root,'frontend/.test-build-run/e2e/qa-harness-safety.js'));const cfg=validateQaHarnessEnv(process.env,path.join(root,'.tmp/tri-ocr-e2e/.qa-e2e.env'));
const sourceDir=path.join(root,'.tmp/tri-ocr-root-cause'),samples=process.env.OCR_V2_SAMPLES?.split(',')??['quadratic','derivative','sigma','old-native-integral'];
const write=(n,v)=>fs.writeFileSync(path.join(out,n),JSON.stringify(v,null,2));
const sourceFiles=['frontend/src/features/math-workspace/components/OcrV2ExperimentalPanel.tsx','frontend/src/features/math-workspace/components/OcrV2LocalCanvas.tsx','frontend/src/features/math-workspace/utils/ocr-v2-experimental.ts','frontend/src/features/math-workspace/utils/handwritten-ocr.ts','frontend/src/features/math-workspace/utils/page-ocr.ts','frontend/src/app/api/ocr-v2-lab/route.ts','tools/ocr-v2-lab/service.py'];
const hashSources=()=>Object.fromEntries(sourceFiles.map(f=>[f,crypto.createHash('sha256').update(fs.readFileSync(path.join(root,f))).digest('hex')]));
const startHashes=hashSources();write('browser-run-manifest.json',{startedAt:new Date().toISOString(),sourceHashes:startHashes,gitSha:require('node:child_process').execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),inputs:samples.map(s=>({sample:s,sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(sourceDir,s+'.capture.json'))).digest('hex')}))});
let browser; const network=[],errors=[],outputs=[];
async function exportOne(page,name){
 await page.getByText('Tôi đồng ý lưu/xuất nét hiện tại trên máy để chẩn đoán',{exact:false}).locator('input').check().catch(async()=>{await page.getByRole('checkbox').last().check();});
 const pending=page.waitForEvent('download',d=>d.suggestedFilename()==='ocr-v2-package.json');await page.getByTestId('v2-export').click();const file=path.join(out,`${name}.package.json`);await(await pending).saveAs(file);return JSON.parse(fs.readFileSync(file));
}
async function run(page){await page.getByTestId('v2-run').click();await expect(page.getByTestId('ocr-v2-panel')).toHaveAttribute('aria-busy','false',{timeout:180000});await expect(page.getByTestId('v2-ir-status')).toBeVisible();}
async function selectAllInk(page,capture){
 // Whole-expression comparison is explicitly manual on an inspected one-expression fixture.
 await page.getByRole('button',{name:'Khoanh nét trong preview',exact:true}).click();
 const svg=page.getByTestId('v2-source-overlay');await svg.scrollIntoViewIfNeeded();const b=await svg.boundingBox();
 await svg.evaluate(el=>el.scrollIntoView({block:'center',behavior:'instant'}));await page.waitForTimeout(150);const box=await svg.boundingBox();
 const points=capture.strokes.filter(s=>s.tool==='PEN').flatMap(s=>s.points),l=Math.max(.002,Math.min(...points.map(p=>p.x))-.015),r=Math.min(.998,Math.max(...points.map(p=>p.x))+.015),t=Math.max(.002,Math.min(...points.map(p=>p.y))-.015),bottom=Math.min(.998,Math.max(...points.map(p=>p.y))+.015);
 const coords=await svg.evaluate((el,pts)=>pts.map(([x,y])=>{const p=el.createSVGPoint();p.x=x*794;p.y=y*1123;const q=p.matrixTransform(el.getScreenCTM());return{x:q.x,y:q.y};}),[[l,t],[r,t],[r,bottom],[l,bottom],[l,t]]);
 await page.mouse.move(coords[0].x,coords[0].y);await page.mouse.down();for(const p of coords.slice(1))await page.mouse.move(p.x,p.y,{steps:12});await page.mouse.up();
 await page.getByRole('button',{name:'Tạo scope từ nét đã chọn',exact:true}).click();
}
(async()=>{
 browser=await chromium.launch({channel:'chrome',headless:true});const context=await browser.newContext({viewport:{width:1800,height:1400},acceptDownloads:true});
 await context.route('**/*',async route=>{const req=route.request(),u=new URL(req.url());
  if(!['localhost','127.0.0.1'].includes(u.hostname)){network.push({externalBlocked:u.origin});return route.abort();}
  if(['POST','PUT','PATCH','DELETE'].includes(req.method())&&!u.pathname.startsWith('/__nextjs')){
   const allowed=/auth\/(login|refresh)/.test(u.pathname)||u.pathname==='/api/ocr-v2-lab';network.push({method:req.method(),path:u.pathname,allowed});if(!allowed)return route.abort();
  }return route.continue();});
 const login=await context.newPage();await login.goto(session.url+'/login');await login.locator('input[type=email]').fill('qa.ocr.e2e.isolated@edums.edu.vn');await login.locator('input[type=password]').fill(cfg.password);await login.locator('button[type=submit]').click();await login.waitForURL(u=>!u.pathname.startsWith('/login'),{timeout:30000});await login.close();
 for(const name of samples){const page=await context.newPage();page.on('pageerror',e=>errors.push({name,error:e.message}));
  await page.goto(session.url+'/ocr-v2-lab');await expect(page.getByRole('heading',{name:'MathCanvas · OCR V2 local lab'})).toBeVisible({timeout:60000});
  await page.getByLabel('Import capture V2').setInputFiles(path.join(sourceDir,`${name}.capture.json`));await page.getByLabel('Nguồn nét V2').selectOption('HANDOFF_CAPTURE');
  await run(page);const m=await exportOne(page,`${name}-layout-m`);outputs.push({sample:name,profile:'LAYOUT_M',data:m});
  await page.screenshot({path:path.join(out,`${name}-layout-m.png`),fullPage:false});console.log(JSON.stringify({sample:name,detector:m.perception.status,boxes:m.perception.regions.length,labels:m.perception.regions.map(r=>r.label),scopeCounts:m.scopes.map(s=>s.strokeIds.length),ocr:m.recognition.map(r=>r.wrapperLatex)}));
  // Manual-scope arm through the actual panel/lasso; never label it automatic model success.
  await selectAllInk(page,JSON.parse(fs.readFileSync(path.join(sourceDir,`${name}.capture.json`))));await page.getByTestId('v2-recognize-selected').click();await expect(page.getByTestId('ocr-v2-panel')).toHaveAttribute('aria-busy','false',{timeout:120000});
  const full=await exportOne(page,`${name}-manual-full`);outputs.push({sample:name,profile:'MANUAL_FULL_EXPRESSION',data:full});
  const last=full.recognition.at(-1);assert.equal(last.strokeIds.length,full.source.strokes.filter(s=>s.tool==='PEN').length);
  assert.ok(last.wrapperLatex);console.log(JSON.stringify({sample:name,manualFull:last.wrapperLatex,raw:last.diagnostic?.rawLatex}));
  // Correction remains authoritative when CoMER runs again.
  const corrected='x+1=3 \\Rightarrow x=5';await page.getByTestId('v2-transcript').fill(corrected);await page.getByRole('button',{name:'Xác nhận nội dung / cấu trúc',exact:true}).click();await page.getByTestId('v2-recognize-selected').click();await expect(page.getByTestId('ocr-v2-panel')).toHaveAttribute('aria-busy','false',{timeout:120000});await expect(page.getByTestId('v2-transcript')).toHaveValue(corrected);
  // Empty edits and explicit manual scopes are corrections too; perception rerun must preserve them.
  await page.getByTestId('v2-transcript').fill('');await run(page);await expect(page.getByTestId('v2-transcript')).toHaveValue('');
  await page.getByTestId('v2-transcript').fill(corrected);await run(page);await expect(page.getByTestId('v2-transcript')).toHaveValue(corrected);
  await page.screenshot({path:path.join(out,`${name}-review.png`)});
  // Baselines are fresh review sessions on precisely the same capture, not on the corrected draft.
  for(const profile of ['V1','V2']){const p=await context.newPage();await p.goto(session.url+'/ocr-v2-lab');await p.getByLabel('Import capture V2').setInputFiles(path.join(sourceDir,`${name}.capture.json`));await p.getByLabel('Nguồn nét V2').selectOption('HANDOFF_CAPTURE');await p.getByLabel('Chế độ OCR V2').selectOption(profile);await run(p);const data=await exportOne(p,`${name}-${profile}`);outputs.push({sample:name,profile,data});await p.close();}
  await page.close();write('run-results.json',outputs);
 }
 write('network.json',{requests:network,errors,applicationMutations:network.filter(n=>n.allowed===false)});
 assert.equal(errors.length,0,JSON.stringify(errors));assert.equal(network.filter(n=>n.allowed===false).length,0);
 assert.deepEqual(hashSources(),startHashes,'Source changed during verification run');
 write('verification.json',{status:'COMPLETED_REAL_BROWSER',actualInkCases:samples.length,runs:outputs.length,externalInferenceRequests:0,applicationMutations:0,modelMetrics:'NOT_MEASURED_MISSING_HUMAN_VERIFIED_LABELS'});
})().catch(e=>{console.error(e.stack);write('verification-error.json',{error:e.stack,network,errors});process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();});
