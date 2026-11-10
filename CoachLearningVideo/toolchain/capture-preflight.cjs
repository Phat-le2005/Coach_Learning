const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('@playwright/test');
const {parseSrt, serializeSrt} = require('@remotion/captions');

(async () => {
  const qa = path.join(__dirname, 'qa');
  fs.mkdirSync(qa, {recursive: true});
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  try {
    const context = await browser.newContext({viewport: {width: 1920, height: 1080},
      recordVideo: {dir: path.join(qa, 'capture'), size: {width: 1920, height: 1080}}});
    const page = await context.newPage();
    const font = fs.readFileSync('D:/SGU/DuAn/Coach_Learning/frontend/src/features/student-home/assets/BeVietnamPro-Regular.woff2').toString('base64');
    await page.setContent(`<style>@font-face{font-family:Demo;src:url(data:font/woff2;base64,${font})}body{font-family:Demo;background:#f4f8f6;margin:60px;color:#163e32}canvas{background:white;border:2px solid #163e32}</style><h1>Kiểm tra công cụ — Tiếng Việt, công thức và nét viết</h1><p>Đây là mẫu kỹ thuật, không phải cảnh demo sản phẩm.</p><canvas id="paper" width="1000" height="650"></canvas>`);
    await page.evaluate(async () => {
      await document.fonts.load('24px Demo');
      const c = document.querySelector('#paper'), ctx = c.getContext('2d');
      window.strokeCount = 0; window.pointCount = 0;
      c.onpointerdown = e => {c.setPointerCapture(e.pointerId);ctx.beginPath();ctx.moveTo(e.offsetX,e.offsetY);};
      c.onpointermove = e => {if(e.buttons){ctx.lineWidth=4;ctx.lineTo(e.offsetX,e.offsetY);ctx.stroke();window.pointCount++;}};
      c.onpointerup = () => {window.strokeCount++;};
    });
    const box = await page.locator('#paper').boundingBox();
    for (const points of [[[80,80],[160,160]],[[160,80],[80,160]],[[210,105],[280,105]],[[210,135],[280,135]]]) {
      await page.mouse.move(box.x+points[0][0], box.y+points[0][1]);
      await page.mouse.down();
      await page.mouse.move(box.x+points[1][0], box.y+points[1][1], {steps: 12});
      await page.mouse.up();
    }
    const result = await page.evaluate(() => {
      const c = document.createElement('canvas'); const gl = c.getContext('webgl2');
      return {strokes:window.strokeCount,points:window.pointCount,fontReady:document.fonts.check('24px Demo'),webgl2:!!gl};
    });
    const mobile = await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    const mobilePage = await mobile.newPage(); await mobilePage.setContent('<button onclick="window.clicked=true" style="width:200px;height:100px">Thiết bị phụ</button>');
    await mobilePage.getByRole('button').tap();
    result.mobileTap = await mobilePage.evaluate(() => window.clicked === true);
    await mobile.close();
    await page.screenshot({path:path.join(qa,'capture-preflight.png')});
    const recording = page.video(); await context.close(); result.recording = await recording.path();
    const srt = '1\n00:00:00,000 --> 00:00:01,500\nKiểm tra phụ đề tiếng Việt.\n\n';
    const {captions} = parseSrt({input:srt});
    fs.writeFileSync(path.join(qa,'captions.srt'),serializeSrt({lines:captions.map(c=>[c])}));
    result.captions = captions.length;
    fs.writeFileSync(path.join(qa,'capture-report.json'),JSON.stringify(result,null,2));
    console.log(JSON.stringify(result));
    if (result.strokes!==4 || !result.mobileTap || !result.fontReady || !result.webgl2) process.exitCode=1;
  } finally {await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1});
