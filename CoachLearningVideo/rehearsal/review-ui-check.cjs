const fs=require('fs'),path=require('path');
const {chromium}=require('../toolchain/node_modules/@playwright/test');
(async()=>{
 const p=JSON.parse(fs.readFileSync(path.join(__dirname,'private.json'),'utf8'));
 const b=await chromium.launch({channel:'msedge'});let a;
 try{
  const c=await b.newContext({viewport:{width:1920,height:1080}});a=await c.newPage();a.setDefaultTimeout(20000);
  await a.goto('http://127.0.0.1:3150/login');await a.locator('input[name=email]').fill(p.student.email);await a.locator('input[name=password]').fill(p.password);await a.locator('button[type=submit]').click();
  await a.waitForURL(u=>!u.pathname.startsWith('/login'),{waitUntil:'domcontentloaded'});
  await a.goto('http://127.0.0.1:3150/student/attempts/'+p.attempt_id,{waitUntil:'domcontentloaded'});
  await a.waitForTimeout(2000);
  console.log('BODY', (await a.locator('body').innerText()).slice(-7000));
  console.log('BUTTONS',await a.locator('button').allTextContents());
  await a.screenshot({path:path.join(__dirname,'review-before.png'),timeout:15000});
  await a.getByRole('button',{name:/Kiểm tra bài|Xem kết quả|Nộp bài & kiểm tra/}).first().click();
  await a.getByRole('button',{name:'Mở tất cả',exact:true}).click();
  await a.getByText(/Tính sai dấu/).first().waitFor();
  await a.waitForTimeout(700);
  await a.screenshot({path:path.join(__dirname,'scene-feedback.png'),timeout:15000});
  fs.writeFileSync(path.join(__dirname,'review-ui-report.json'),JSON.stringify({status:'PASS',body:await a.locator('body').innerText()},null,2));console.log('Real feedback displayed: PASS');
 }catch(e){const body=a?await a.locator('body').innerText().catch(()=> ''):'';fs.writeFileSync(path.join(__dirname,'review-ui-report.json'),JSON.stringify({status:'BLOCKED',error:e.message,body},null,2));console.log('FAILED',e.message,body.slice(-4000));process.exitCode=1;}finally{await b.close();}
})();
