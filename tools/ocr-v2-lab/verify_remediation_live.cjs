#!/usr/bin/env node
// New physical IDs through the real shared MathCanvas. Replayed ink is not a new human sample.
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'.tmp/tri-ocr-v2-remediation');
const {chromium,expect}=require(path.join(root,'frontend/node_modules/@playwright/test'));
const {validateQaHarnessEnv}=require(path.join(root,'frontend/.test-build-run/e2e/qa-harness-safety.js'));
const cfg=validateQaHarnessEnv(process.env,path.join(root,'.tmp/tri-ocr-e2e/.qa-e2e.env'));
const session=JSON.parse(fs.readFileSync(path.join(root,'.tmp/tri-ocr-v2-runtime/session.json')));let browser;
const requests=[],errors=[];
async function run(page){await page.getByTestId('v2-run').click();await expect(page.getByTestId('ocr-v2-panel')).toHaveAttribute('aria-busy','false',{timeout:180000});}
async function draw(page,points){const c=page.getByTestId('v2-live-canvas').locator('canvas');await c.evaluate(e=>e.scrollIntoView({block:'start',behavior:'instant'}));const b=await c.boundingBox();await page.mouse.move(b.x+points[0].x*b.width,b.y+points[0].y*b.height);await page.mouse.down();for(const p of points.slice(1))await page.mouse.move(b.x+p.x*b.width,b.y+p.y*b.height);await page.mouse.up();}
async function exportOne(page,name){await page.getByRole('checkbox').last().check();const waiting=page.waitForEvent('download',d=>d.suggestedFilename()==='ocr-v2-package.json');await page.getByTestId('v2-export').click();const file=path.join(out,name);await(await waiting).saveAs(file);return JSON.parse(fs.readFileSync(file));}
(async()=>{browser=await chromium.launch({channel:'chrome',headless:true});const context=await browser.newContext({viewport:{width:1900,height:1500},acceptDownloads:true});
 await context.route('**/*',route=>{const r=route.request(),u=new URL(r.url());if(!['localhost','127.0.0.1'].includes(u.hostname))return route.abort();if(['POST','PUT','PATCH','DELETE'].includes(r.method())&&!u.pathname.startsWith('/__nextjs')){const allowed=/auth\/(login|refresh)/.test(u.pathname)||u.pathname==='/api/ocr-v2-lab';requests.push({path:u.pathname,allowed});if(!allowed)return route.abort();}return route.continue();});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));await page.goto(session.url+'/login');await page.locator('input[type=email]').fill('qa.ocr.e2e.isolated@edums.edu.vn');await page.locator('input[type=password]').fill(cfg.password);await page.locator('button[type=submit]').click();await page.waitForURL(u=>!u.pathname.startsWith('/login'));await page.goto(session.url+'/ocr-v2-lab');
 const original=JSON.parse(fs.readFileSync(path.join(out,'user-equation-14.capture.json')));
 for(const stroke of original.strokes)await draw(page,stroke.points);
 await page.getByLabel('Nguồn nét V2').selectOption('SYNTHETIC_INK');assert.equal(await page.getByLabel('Chế độ OCR V2').inputValue(),'HYBRID');await run(page);
 const auto=await exportOne(page,'live-auto.package.json');assert.equal(auto.source.strokes.length,original.strokes.length);assert.ok(auto.source.strokes.every(s=>!original.strokes.some(o=>o.id===s.id)));
 const scope=auto.scopes.find(s=>s.kind==='MATH'&&s.strokeIds.length===auto.source.strokes.length);assert.ok(scope);assert.equal(auto.modelInferenceCalls,1);assert.ok(auto.recognition[0].diagnostic.rawLatex);assert.equal(auto.ir.approvedUnitCount,0);assert.equal(auto.projection.readyToSubmit,false);
 await page.screenshot({path:path.join(out,'screenshots/live-auto.png'),fullPage:true});
 const literal='x+1=3 \\Rightarrow x=5';await page.getByTestId('v2-transcript').fill(literal);await page.getByRole('button',{name:'Xác nhận nội dung / cấu trúc',exact:true}).click();await run(page);await expect(page.getByTestId('v2-transcript')).toHaveValue(literal);
 const reviewed=await exportOne(page,'live-reviewed-rerun.package.json');assert.ok(reviewed.ir.contentUnits.some(u=>u.approvedContent===literal));
 await draw(page,[{x:.1,y:.45},{x:.15,y:.47}]);await expect(page.getByTestId('ocr-v2-panel')).toHaveAttribute('data-stale','true');const stale=await exportOne(page,'live-stale.package.json');assert.equal(stale.ir.approvedUnitCount,0);assert.equal(stale.effectiveReviewStatus,'STALE_REVIEW_REQUIRED');
 // Import a real 6MB package through the actual UI, extracting ink only.
 await page.goto(session.url+'/ocr-v2-lab');await page.getByLabel('Import capture V2').setInputFiles(path.join(out,'user-equation-14.original.package.json'));await run(page);const imported=await exportOne(page,'package-import.package.json');assert.deepEqual(imported.source.strokes,original.strokes);assert.equal(imported.ir.approvedUnitCount,0);
 assert.equal(requests.filter(r=>!r.allowed).length,0);assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(out,'live-verification.json'),JSON.stringify({status:'VERIFIED_ACTUAL_MATHCANVAS_HYBRID',inputKind:'SYNTHETIC_BROWSER_POINTER_REPLAY_OF_REAL14; not new native accuracy',nativePackageImport:'VERIFIED',automaticScopeStrokeCount:scope.strokeIds.length,confirmedInferenceCalls:auto.modelInferenceCalls,raw:auto.recognition[0].diagnostic.rawLatex,correctionPreserved:true,revisionInvalidatesApproval:true,applicationMutations:0,requests,errors},null,2));console.log('LIVE_HYBRID_AUTO_SCOPE_COMER_REVIEW_EXPORT_VERIFIED');
})().catch(e=>{fs.writeFileSync(path.join(out,'live-error.json'),JSON.stringify({error:e.stack,requests,errors},null,2));console.error(e.stack);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();});
