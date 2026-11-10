const fs=require('node:fs'),path=require('node:path');
const {chromium,expect}=require('../toolchain/node_modules/@playwright/test');
const ROOT=__dirname,p=JSON.parse(fs.readFileSync(path.join(ROOT,'private.json'),'utf8'));
const BASE='http://127.0.0.1:3150';const report={};
async function login(browser,role){const c=await browser.newContext({viewport:{width:1920,height:1080}});const page=await c.newPage();await page.goto(BASE+'/login');await page.locator('input[name=email]').fill(p[role].email);await page.locator('input[name=password]').fill(p.password);await page.locator('button[type=submit]').click();await page.waitForURL(u=>!u.pathname.startsWith('/login'),{timeout:60000});return {c,page};}
async function scene(name,fn){const t=Date.now();try{report[name]={status:'PASS',...await fn(),seconds:(Date.now()-t)/1000};}catch(e){report[name]={status:'FAILED',reason:e.message.slice(0,550),seconds:(Date.now()-t)/1000};}fs.writeFileSync(path.join(ROOT,'scene-report.json'),JSON.stringify(report,null,2));console.log(name,report[name].status);}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
 const {c,page}=await login(browser,'student');
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 if(!process.env.ONLY_FAILED) await scene('goalAndPlan',async()=>{
  await page.getByRole('button',{name:'Lập kế hoạch học',exact:true}).click({timeout:12000});
  const dialog=page.locator('dialog[open]');await dialog.getByRole('button',{name:/8.0/}).click();await dialog.getByRole('button',{name:'30 phút',exact:true}).click();await dialog.locator('input[type=date]').fill('2027-06-01');
  const responsePromise=page.waitForResponse(r=>r.url().includes('/api/student/study-plan')&&r.request().method()==='POST');
  await dialog.getByRole('button',{name:'Tạo kế hoạch học',exact:true}).click();const response=await responsePromise;
  if(!response.ok())throw Error('Study-plan HTTP '+response.status());await expect(dialog).not.toBeVisible({timeout:30000});
  await page.screenshot({path:path.join(ROOT,'scene-plan.png'),fullPage:true});return {http:response.status(),target:8,minutes:30};
 });
 if(!process.env.ONLY_FAILED) await scene('knowledgeMap',async()=>{
  await page.goto(BASE+'/student/knowledge');await expect(page.getByRole('button',{name:'Cây 3D',exact:true})).toBeVisible({timeout:60000});
  await page.screenshot({path:path.join(ROOT,'scene-knowledge.png')});return {canvasCount:await page.locator('canvas').count(),headings:await page.locator('h1,h2').allTextContents()};
 });
 if(!process.env.ONLY_FAILED) await scene('theory',async()=>{
  await page.goto(BASE+'/student/theory');await page.getByLabel('Chọn tài liệu bài học').selectOption(p.theory_id,{timeout:60000});
  await expect(page.getByRole('tab',{name:'Sơ đồ tư duy',exact:true})).toBeVisible();await page.screenshot({path:path.join(ROOT,'scene-theory.png')});
  return {publishedMap:true};
 });
 await scene('mathView',async()=>{
  await page.goto(BASE+'/student/attempts/'+p.self_attempt_id);
  await page.locator('summary').filter({hasText:'Công cụ toán'}).click({timeout:60000});
  await page.getByRole('button',{name:'Math View',exact:true}).click();
  const panel=page.getByRole('complementary',{name:'Math View',exact:true});
  const input=page.locator('#canvas-formula');await input.fill('z=a*x^2+b*y^2');await input.press('Tab');
  await expect(page.getByRole('button',{name:'Lưu vào bài học',exact:true})).toBeEnabled({timeout:30000});
  await page.screenshot({path:path.join(ROOT,'scene-math-view.png')});
  await page.getByRole('button',{name:'Lưu vào bài học',exact:true}).click();
  await expect(page.getByText(/Đã lưu/).last()).toBeVisible({timeout:30000});
  return {formula:'z=a*x^2+b*y^2',canvasCount:await page.locator('canvas').count()};
 });
 report.browserErrors=errors;await c.close();
 const teacher=await login(browser,'teacher');
 await scene('teacherClassAndSubmissions',async()=>{
  await teacher.page.goto(BASE+'/teacher?tab=submissions&classroom_id='+p.classroom_id);
  await expect(teacher.page.getByLabel('Chọn lớp học quản lý')).toBeEnabled({timeout:30000});
  await teacher.page.getByLabel('Chọn lớp học quản lý').selectOption(p.classroom_id);
  await expect(teacher.page.getByText('Luyện tập đạo hàm và khảo sát hàm số',{exact:false}).first()).toBeVisible({timeout:60000});
  await teacher.page.screenshot({path:path.join(ROOT,'scene-teacher.png')});return {assignmentVisible:true};
 });await teacher.c.close();
 }finally{await browser.close();fs.writeFileSync(path.join(ROOT,'scene-report.json'),JSON.stringify(report,null,2));}
})().catch(e=>{console.error(e.message);process.exitCode=1});
