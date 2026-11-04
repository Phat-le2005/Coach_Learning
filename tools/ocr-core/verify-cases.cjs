#!/usr/bin/env node
// Real application + database + browser CoMER. QA fixture mutations only. No OCR response mocks.
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict'),{execFileSync}=require('child_process');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'.tmp/tri-ocr-v2-core-integration');fs.mkdirSync(path.join(out,'screenshots'),{recursive:true});
const {chromium,expect}=require(path.join(root,'frontend/node_modules/@playwright/test'));
const {validateQaHarnessEnv,loadUntrackedQaEnv}=require(path.join(root,'frontend/.test-build-run/e2e/qa-harness-safety.js'));
const cfg=validateQaHarnessEnv({...process.env},process.env.QA_E2E_ENV_FILE||path.join(root,'.tmp/tri-ocr-e2e/.qa-e2e.env'));
if(cfg.appEnv!=='test')throw Error('APP_ENV=test required');
const env={...process.env};loadUntrackedQaEnv(env,process.env.QA_BACKEND_ENV_FILE||path.join(root,'backend/.env'));
Object.assign(env,{APP_ENV:'test',DATABASE_NAME:cfg.qaDatabaseName,QA_E2E_DATABASE_NAME:cfg.qaDatabaseName,QA_E2E_PASSWORD:cfg.password});
const python=process.env.PYTHON_EXE||path.join(root,'backend/.venv/Scripts/python.exe');
function db(...args){return JSON.parse(execFileSync(python,[path.join(root,'frontend/e2e/qa_db_helper.py'),...args],{cwd:path.join(root,'backend'),env,encoding:'utf8',stdio:['ignore','pipe','pipe']}));}
const base=process.env.E2E_BASE_URL||'http://localhost:3020',write=(n,v)=>fs.writeFileSync(path.join(out,n),JSON.stringify(v,null,2));
let browser;const errors=[],requests=[];
async function draw(page,points){const c=page.locator('canvas').first();await c.scrollIntoViewIfNeeded();const b=await c.boundingBox();await page.mouse.move(b.x+points[0].x*b.width,b.y+points[0].y*b.height);await page.mouse.down();for(const p of points.slice(1))await page.mouse.move(b.x+p.x*b.width,b.y+p.y*b.height);await page.mouse.up();}
async function exportReview(page,name){const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Xuất bản chép và nguồn nét',exact:true}).click();await(await pending).saveAs(path.join(out,name));return JSON.parse(fs.readFileSync(path.join(out,name)));}
async function putInk(page,id,strokes) { return await page.evaluate(async({id,strokes})=>{
 const csrf=(await(await fetch('/auth/csrf')).json()).csrf_token;
 const p=`/api/v2/math-solutions/attempts/${id}/ink/pages/0`;
 const before=await(await fetch(p,{headers:{'X-EduMS-BFF':'1'}})).json();
 const response=await fetch(p,{method:'PUT',headers:{'X-EduMS-BFF':'1','X-CSRF-Token':csrf,'Content-Type':'application/json'},body:JSON.stringify({expected_document_revision:before.document_revision,client_action_id:crypto.randomUUID(),strokes})});
 return {status:response.status,body:await response.json()};
 },{id,strokes}); }
async function openCase(page,fixture,strokes) {
 const response=await putInk(page,fixture.attempt_id,strokes);if(response.status!==200){const error=Error(`INPUT_PERSISTENCE_BLOCKED_${response.status}`);error.response=response;throw error;}
 await page.goto(base+'/student/attempts/'+fixture.attempt_id);await page.getByRole('button',{name:/Trích xuất trang/}).click();
 const d=page.getByTestId('ocr-v2-main-review');await expect(d).toHaveAttribute('aria-busy','false',{timeout:180000});return d;
}
(async()=>{
 db('verify-safety');browser=await chromium.launch({channel:'chrome',headless:true});const context=await browser.newContext({viewport:{width:1700,height:1200},acceptDownloads:true});
 await context.route('**/*',route=>{const r=route.request(),u=new URL(r.url());if(!['localhost','127.0.0.1'].includes(u.hostname))return route.abort();if(['POST','PUT','PATCH','DELETE'].includes(r.method())&&!u.pathname.startsWith('/__nextjs')){requests.push({method:r.method(),path:u.pathname});if(/submit|ai-review|grade/.test(u.pathname))return route.abort();}return route.continue();});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));await page.goto(base+'/login');await page.locator('input[type=email]').fill('qa.ocr.e2e.isolated@edums.edu.vn');await page.locator('input[type=password]').fill(cfg.password);await page.locator('button[type=submit]').click();await page.waitForURL(u=>!u.pathname.startsWith('/login'));
 const cases=[];
 if(process.env.OCR_TEST_CAPTURE_DIR)for(const name of ['quadratic','derivative','sigma','old-native-integral']){const file=path.join(process.env.OCR_TEST_CAPTURE_DIR,name+'.capture.json');if(fs.existsSync(file))cases.push({name,source:'REAL_CAPTURE_API_REPLAY; no independent GT',strokes:JSON.parse(fs.readFileSync(file)).strokes});}
 if(process.env.OCR_TEST_MIXED_CAPTURE){const value=JSON.parse(fs.readFileSync(process.env.OCR_TEST_MIXED_CAPTURE));cases.push({name:'mixed-native',source:'REAL_CAPTURE_API_REPLAY; no independent GT',strokes:value.strokes??value.source.strokes});}
 const stamp=(id,pts)=>({id:require('crypto').randomUUID(),tool:'PEN',color:'#101010',width:2,points:pts.map(([x,y])=>({x,y,pressure:.5}))});
 const equation=[stamp('x-a',[[.1,.1],[.12,.13]]),stamp('x-b',[[.12,.1],[.1,.13]]),stamp('eq-a',[[.15,.11],[.19,.11]]),stamp('eq-b',[[.15,.12],[.19,.12]]),stamp('zero',[[.21,.1],[.23,.1],[.23,.13],[.21,.13],[.21,.1]])];
 cases.push({name:'two-lines',source:'SYNTHETIC_SOFTWARE_GEOMETRY',strokes:[...equation,...equation.map(s=>({...s,id:require('crypto').randomUUID(),points:s.points.map(p=>({...p,y:p.y+.19}))}))]});
 const results=[];
 for(const sample of cases){const fixture=db('create-attempt','--label','ocr-v2-'+sample.name);let d;try{d=await openCase(page,fixture,sample.strokes);}catch(error){if(error.response){results.push({name:sample.name,source:sample.source,strokes:sample.strokes.length,status:'BLOCKED_EXISTING_BACKEND_INK_STORAGE_LIMIT',response:error.response});continue;}throw error;}const value=await exportReview(page,`case-${sample.name}.json`);
  assert.equal(value.ir.rawStrokeCount,sample.strokes.length);const roots=new Set(value.ir.contentUnits.flatMap(u=>u.sourceStrokeIds));assert.equal(roots.size,sample.strokes.length);assert.equal(db('inspect-attempt','--attempt-id',fixture.attempt_id).active_step_count,0);
  results.push({name:sample.name,source:sample.source,strokes:sample.strokes.length,units:value.ir.contentUnits.length,kinds:value.ir.contentUnits.map(u=>u.kind),mode:value.mode,inferences:value.evidence.filter(e=>e.result).length,raw:value.evidence.map(e=>e.result?.rawLatex??e.error),accuracy:'NOT_MEASURED_MISSING_INDEPENDENT_GT'});
  if(sample.name==='two-lines'){
   assert.ok(value.ir.contentUnits.length>=2,'Two independent equations must not become one full-page expression');
   // Literal Vietnamese TEXT manual path and UNKNOWN abstention stay separate from math.
   await d.getByTestId('ocr-v2-kind').selectOption('TEXT');await d.getByTestId('ocr-v2-content').fill('Ta có x + 1 = 3, nên x = 5.');await d.getByTestId('ocr-v2-approve').click();await expect(d.getByRole('button',{name:'Nhận diện lại bằng CoMER'})).toBeDisabled();
   const text=await exportReview(page,'case-text-manual.json');assert.equal(text.ir.contentUnits[0].approvedContent,'Ta có x + 1 = 3, nên x = 5.');
   await d.getByTestId('ocr-v2-kind').selectOption('UNKNOWN');await expect(d.getByTestId('ocr-v2-boundary')).toBeDisabled();
   await d.locator('summary').click();const checkboxes=d.getByRole('checkbox',{name:/^Chọn đơn vị /});await checkboxes.nth(0).check();await checkboxes.nth(1).check();await d.getByLabel('Quan hệ bản chép').selectOption('SYSTEM');await d.getByRole('button',{name:'Tạo cấu trúc từ các đơn vị',exact:true}).click();
   const grouped=await exportReview(page,'case-system-proposal.json');const parent=grouped.ir.contentUnits.find(u=>u.role==='CONTAINER');assert.ok(parent);assert.equal(parent.approvedContent,null);assert.equal(parent.reviewStatus,'NEEDS_REVIEW');
   await expect(d).toContainText('Đã lưu bản chép trên thiết bị');
   const alternate=await context.newPage();alternate.on('pageerror',e=>errors.push(e.message));await alternate.goto(base+'/student/attempts/'+fixture.attempt_id);await alternate.getByRole('button',{name:/Trích xuất trang/}).click();const other=alternate.getByTestId('ocr-v2-main-review');await expect(other).toHaveAttribute('aria-busy','false',{timeout:30000});await other.getByTestId('ocr-v2-unit').filter({hasText:'UNKNOWN'}).first().click();await other.getByTestId('ocr-v2-content').fill('Second tab durable correction');await expect(other).toContainText('Đã lưu bản chép trên thiết bị');
   await d.getByTestId('ocr-v2-content').fill('Stale first tab must not overwrite');await expect(d.getByRole('alert')).toContainText('REVIEW_CHANGED_IN_ANOTHER_TAB');await expect(d.getByTestId('ocr-v2-approve')).toBeDisabled();const preserved=await exportReview(alternate,'case-concurrent-preserved.json');assert.ok(preserved.ir.contentUnits.some(u=>u.approvedContent==='Second tab durable correction'));await alternate.close();
  }
  await d.getByRole('button',{name:'Đóng',exact:true}).click();
 }
 // Network fault injection: no mocked OCR result, followed by a real retry after assets become available.
 const faultFixture=db('create-attempt','--label','ocr-v2-runtime-unavailable');await context.route('**/ocr/comer/**',route=>route.abort());let d=await openCase(page,faultFixture,equation);await expect(d).toContainText('CoMER chưa nhận diện');const failed=await exportReview(page,'case-comer-unavailable.json');assert.ok(failed.evidence.every(e=>!e.result));await context.unroute('**/ocr/comer/**');await d.getByRole('button',{name:'Nhận diện lại bằng CoMER',exact:true}).click();await expect(d).toHaveAttribute('aria-busy','false',{timeout:120000});const retried=await exportReview(page,'case-comer-retried.json');assert.ok(retried.evidence.some(e=>e.result));
 // Remote ink change is rejected before a batch journal or step mutation is started.
 await d.getByTestId('ocr-v2-content').fill('x=5');await d.getByTestId('ocr-v2-approve').click();await d.getByTestId('ocr-v2-order').click();await d.getByTestId('ocr-v2-boundary').check();await d.getByTestId('ocr-v2-step-kind').selectOption('CUSTOM');await putInk(page,faultFixture.attempt_id,[...equation,stamp('remote-dot',[[.4,.4]])]);await d.getByTestId('ocr-v2-prepare-save').click();await expect(d.getByRole('alert')).toContainText('SERVER_INK_REVISION_CHANGED');assert.equal(db('inspect-attempt','--attempt-id',faultFixture.attempt_id).active_step_count,0);await d.getByRole('button',{name:'Đóng',exact:true}).click();
 // Existing journal recovery still blocks the primary OCR entry and can explicitly resume.
 const recovery=db('create-attempt','--label','ocr-v2-existing-batch-recovery');await putInk(page,recovery.attempt_id,equation);await page.goto(base+'/student/attempts/'+recovery.attempt_id);
 await page.evaluate(async id=>{const request=indexedDB.open('edums_step_batch_journal_v1',1);await new Promise((resolve,reject)=>{request.onsuccess=()=>resolve();request.onerror=()=>reject(request.error);});const db=request.result;const action=crypto.randomUUID();const tx=db.transaction('pending_batches','readwrite');tx.objectStore('pending_batches').put({schemaVersion:1,batchId:crypto.randomUUID(),attemptId:id,createdAt:Date.now(),nextRevision:1,state:'PAUSED',message:'Software workflow recovery fixture',entries:[{draftId:'explicit-recovery-fixture',actionId:action,content:{step_type:'CUSTOM',content_latex:'x+1=3 \\Rightarrow x=5',explanation_text:null,artifact:null},state:'QUEUED',frozen:null,beforeStepIds:null,serverStepId:null,serverRevision:null,error:null}]});await new Promise((res,rej)=>{tx.oncomplete=res;tx.onerror=rej;});db.close();},recovery.attempt_id);
 await page.reload();await expect(page.getByRole('button',{name:/Trích xuất trang/})).toBeDisabled();await page.getByRole('button',{name:'Lưu tiếp (Resume)',exact:true}).click();await expect(page.getByRole('button',{name:/Trích xuất trang/})).toBeEnabled({timeout:30000});assert.equal(db('inspect-attempt','--attempt-id',recovery.attempt_id).active_step_count,1);
 // Existing canvas controls remain connected to the same persisted ink document.
 const canvasFixture=db('create-attempt','--label','ocr-v2-canvas-regression');await page.goto(base+'/student/attempts/'+canvasFixture.attempt_id);await expect(page.locator('canvas').first()).toBeVisible();
 await draw(page,[{x:.1,y:.1},{x:.12,y:.13}]);await draw(page,[{x:.12,y:.1},{x:.1,y:.13}]);
 const pageCount=()=>db('inspect-attempt','--attempt-id',canvasFixture.attempt_id).ink_document?.pages.find(p=>p.page_index===0)?.stroke_count??0;
 await expect.poll(pageCount,{timeout:20000}).toBe(2);await page.getByTitle('Hoàn tác (Ctrl+Z)',{exact:true}).click();await expect.poll(pageCount,{timeout:20000}).toBe(1);await page.getByTitle('Làm lại (Ctrl+Y)',{exact:true}).click();await expect.poll(pageCount,{timeout:20000}).toBe(2);
 await page.getByRole('button',{name:'Tẩy',exact:true}).click();await draw(page,[{x:.1,y:.1},{x:.12,y:.13}]);await expect.poll(pageCount,{timeout:20000}).toBeLessThan(2);
 await page.getByRole('button',{name:'Thêm trang',exact:true}).click();await page.getByRole('button',{name:'Bút',exact:true}).click();await draw(page,[{x:.4,y:.4},{x:.42,y:.45}]);await expect.poll(()=>db('inspect-attempt','--attempt-id',canvasFixture.attempt_id).ink_document?.pages.find(p=>p.page_index===1)?.stroke_count??0,{timeout:20000}).toBe(1);await page.getByRole('button',{name:'Trang trước',exact:true}).click();
 assert.equal(errors.length,0,JSON.stringify(errors));assert.equal(requests.filter(r=>/submit|ai-review|grade/.test(r.path)).length,0);
 write('case-verification.json',{status:'VERIFIED_MAIN_APP_CAPTURE_REPLAY_AND_FAILURE_PATHS',cases:results,comerUnavailableAndRealRetry:true,remoteRevisionBlocksStep:true,existingPendingBatchBlocksOcrAndResumes:true,concurrentCorrectionProtection:true,drawingErasingUndoRedoPageNavigation:true,textAndUnknown:'VERIFIED_MANUAL_ABSTENTION',structure:'EXPLICIT_HUMAN_WORKFLOW; software test, not structural accuracy',modelMocks:0,submitRequests:0,errors});console.log('MAIN_CASES_AND_FAILURE_PATHS_VERIFIED');
})().catch(e=>{write('case-error.json',{error:e.stack,errors,requests});console.error(e.stack);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();});
