const fs=require('node:fs'),path=require('node:path');
const {chromium,expect}=require('../toolchain/node_modules/@playwright/test');
const R=__dirname,p=JSON.parse(fs.readFileSync(path.join(R,'private.json'),'utf8')),BASE='http://127.0.0.1:3150';
const glyphs={x:[[[0,0],[1,1]],[[1,0],[0,1]]],y:[[[0,0],[.5,.55],[1,0]],[[.5,.55],[.4,1],[.2,1.15]]],"=":[[[0,.3],[1,.3]],[[0,.7],[1,.7]]],"-":[[[0,.5],[1,.5]]],"+":[[[0,.5],[1,.5]],[[.5,0],[.5,1]]],"'":[[[.3,.2],[.6,-.3]]],"3":[[[0,.1],[.3,0],[.8,0],[1,.2],[.85,.4],[.4,.5],[.8,.5],[1,.7],[.9,.9],[.6,1],[.1,.95]]],"2":[[[0,.15],[.2,0],[.7,0],[1,.2],[.85,.4],[.1,.95],[1,.95]]]};
const rows=[{top:.10,chars:[['y',.09],['=',.17],['x',.25],['3',.305,.65],['-',.36],['3',.44],['x',.52]]},{top:.22,chars:[['y',.09],["'",.145,.6],['=',.20],['3',.28],['x',.36],['2',.415,.65],['+',.47],['3',.55]]}];
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});const report={};let mobile;
 try{
  const desktop=await browser.newContext({viewport:{width:1920,height:1080}});const a=await desktop.newPage();
  await a.goto(BASE+'/login');await a.locator('input[name=email]').fill(p.student.email);await a.locator('input[name=password]').fill(p.password);await a.locator('button[type=submit]').click();await a.waitForURL(u=>!u.pathname.startsWith('/login'));
  await a.goto(BASE+'/student/attempts/'+p.attempt_id);
  const read=()=>a.evaluate(async id=>{const r=await fetch('/api/v2/math-solutions/attempts/'+id+'/ink/pages/0',{headers:{'X-EduMS-BFF':'1'}});return r.json()},p.attempt_id);
  if((await read()).strokes.length)throw Error('Rehearsal page already contains ink; preserved for review.');
  await a.getByRole('button',{name:'Kết nối thiết bị viết',exact:true}).click({timeout:60000});
  const pairing=a.getByRole('dialog');await pairing.getByAltText('Quét mã để kết nối thiết bị viết').waitFor();
  await pairing.locator('summary').first().click();const href=await pairing.getByRole('link',{name:'Mở bảng viết trên thiết bị này'}).getAttribute('href');
  if(new URL(href,BASE).origin!==BASE)throw Error('Pairing origin differs from isolated rehearsal origin');
  mobile=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});const b=await mobile.newPage();await b.goto(href);
  await pairing.getByRole('button',{name:'Cho phép viết',exact:true}).click();await expect(b.locator('[data-live-status]')).toHaveAttribute('data-live-status','connected',{timeout:30000});await pairing.getByRole('button',{name:'Tiếp tục làm bài'}).click();report.pairing='PASS';
  const canvas=b.getByLabel('Giấy viết MathCanvas',{exact:true});const box=await canvas.boundingBox();let count=0;
  for(const row of rows)for(const [char,left,small] of row.chars){const scale=small||1,top=row.top-(small?.02:0);for(const points of glyphs[char]){
   const coord=([x,y])=>[box.x+(left+x*.047*scale)*box.width,box.y+(top+y*.060*scale)*box.height];
   await b.mouse.move(...coord(points[0]));await b.mouse.down();for(const point of points.slice(1))await b.mouse.move(...coord(point),{steps:4});await b.mouse.up();count++;
  }}
  await expect(b.locator('[data-live-status]')).toHaveAttribute('data-pending','0',{timeout:30000});await expect.poll(async()=>(await read()).strokes.length,{timeout:30000}).toBe(count);
  report.handwriting={status:'PASS',strokes:count,expectedLines:['y=x^3-3x',"y'=3x^2+3"],input:'browser pointer replay'};
  await a.screenshot({path:path.join(R,'scene-handwriting-desktop.png')});await b.screenshot({path:path.join(R,'scene-handwriting-mobile.png')});
  const started=Date.now();const responsePromise=a.waitForResponse(r=>r.url().includes('/ocr/recognize')&&r.request().method()==='POST',{timeout:150000});
  await a.getByRole('button',{name:'Trích xuất trang (OCR)',exact:true}).click();const response=await responsePromise;const data=await response.json();
  fs.writeFileSync(path.join(R,'actual-ocr.json'),JSON.stringify(data,null,2));report.ocr={http:response.status(),seconds:(Date.now()-started)/1000};
  const review=a.getByTestId('ocr-v2-main-review');await expect(review).toHaveAttribute('aria-busy','false',{timeout:30000});await a.screenshot({path:path.join(R,'scene-ocr.png')});
  report.review={units:await review.getByTestId('ocr-v2-unit').count(),text:(await review.innerText()).slice(-2200)};
  await desktop.storageState({path:path.join(R,'student-session.private.json')});await desktop.close();
 }catch(e){report.failure=e.message.slice(0,600);process.exitCode=1;}
 finally{if(mobile)await mobile.close();await browser.close();fs.writeFileSync(path.join(R,'handwriting-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));}
})().catch(e=>{console.error(e.message);process.exitCode=1});
