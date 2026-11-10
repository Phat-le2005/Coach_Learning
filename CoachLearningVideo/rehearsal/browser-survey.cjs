const fs=require('node:fs'),path=require('node:path');
const {chromium}=require('../toolchain/node_modules/@playwright/test');
const root=__dirname, p=JSON.parse(fs.readFileSync(path.join(root,'private.json'),'utf8'));
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const report={};
 try{
  for(const role of ['student','teacher']){
   const context=await browser.newContext({viewport:{width:1920,height:1080}});const page=await context.newPage();
   const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto('http://127.0.0.1:3150/login');
   await page.locator('input[name=email]').fill(p[role].email);
   await page.locator('input[name=password]').fill(p.password);
   await page.locator('button[type=submit]').click();
   await page.waitForURL(u=>!u.pathname.startsWith('/login'),{timeout:60000});
   await page.locator('h1').first().waitFor({timeout:60000});
   await page.screenshot({path:path.join(root,role+'-home.png'),fullPage:true});
   report[role]={url:page.url(),headings:await page.locator('h1,h2,h3').allTextContents(),buttons:await page.getByRole('button').allTextContents(),errors};
   await context.storageState({path:path.join(root,role+'-session.private.json')});
   await context.close();
  }
 }finally{await browser.close();}
 fs.writeFileSync(path.join(root,'browser-survey.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify(report));
})().catch(e=>{console.error(e.message);process.exitCode=1});
