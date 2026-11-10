const path=require('node:path');
const fs=require('node:fs');
const {bundle}=require('@remotion/bundler');
const {selectComposition,renderStill}=require('@remotion/renderer');
(async()=>{
  const serveUrl=await bundle({entryPoint:path.join(__dirname,'render-preflight.tsx')});
  const composition=await selectComposition({serveUrl,id:'ToolchainCheck'});
  await renderStill({serveUrl,composition,output:path.join(__dirname,'qa/remotion-still.png'),frame:0});
  fs.writeFileSync(path.join(__dirname,'qa/render-report.json'),JSON.stringify({width:composition.width,height:composition.height,fps:composition.fps,still:'PASS'},null,2));
  console.log('Remotion bundle and 1080p still PASS');
})().catch(e=>{console.error(e.message);process.exitCode=1});
