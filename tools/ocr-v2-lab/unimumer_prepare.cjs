// Reuse captured Lab crops and exact existing CoMER preprocessing. No Uni-MuMER calls/GT prompts.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),assert=require('assert/strict');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'.tmp/tri-unimumer-lab');
const {chromium}=require(path.join(root,'frontend/node_modules/@playwright/test'));
const {toModelStrokes}=require(path.join(root,'frontend/.test-build-run/src/features/math-workspace/utils/handwritten-ocr.js'));
const {constructScopeCandidates}=require(path.join(root,'frontend/.test-build-run/src/features/math-workspace/utils/ocr-v2-scope-candidates.js'));
const {renderTransform}=require(path.join(root,'frontend/.test-build-run/src/features/math-workspace/utils/ocr-v2-experimental.js'));
const sha=s=>crypto.createHash('sha256').update(s).digest('hex');
const write=(n,v)=>fs.writeFileSync(path.join(out,n),JSON.stringify(v,null,2));
(async()=>{fs.mkdirSync(path.join(out,'inputs'),{recursive:true});const inputs=[],native=[];
 for(const name of ['user-equation-14','quadratic','derivative','sigma','old-native-integral']){
  const pkg=JSON.parse(fs.readFileSync(path.join(root,`.tmp/tri-ocr-v2-remediation/${name}-GEOMETRY.package.json`)));
  const ink=pkg.source.strokes.filter(s=>s.tool==='PEN');const scope=pkg.scopes.find(s=>s.strokeIds.length===ink.length);assert.ok(scope,'Expected bounded single-expression fixture');
  const crop=pkg.render.crops.find(c=>c.scopeId===scope.id).png;
  inputs.push({id:name,sourceKind:'NATIVE_MATHCANVAS_CAPTURE',scopeSource:'FULL_EXPRESSION_DIAGNOSTIC; scope not independently human-annotated here',annotationStatus:'DRAFT_NO_INDEPENDENT_GT',reference:null,sourceStrokeIds:ink.map(s=>s.id),strokes:ink,sourceSha256:sha(JSON.stringify(pkg.source.strokes)),imageData:crop,imageOrigin:'EXISTING_LAB_cropLabScope',sourceRevision:pkg.source.sourceRevision});native.push(name);
 }
 const pool=JSON.parse(fs.readFileSync(path.join(root,'.tmp/tri-ocr-v2-evaluation/source-pages.json'))).filter(p=>p.split==='DEV');
 const rules=['\\frac','\\sum','\\int','=','\\sqrt[3]','\\sqrt[','\\Leftrightarrow','\\Rightarrow','\\mathbb{R}','('],chosen=[];
 for(const rule of rules){const p=pool.filter(p=>p.annotation.units[0].transcript.includes(rule)&&!chosen.some(c=>c.id===p.id)).sort((a,b)=>a.id.localeCompare(b.id))[0];if(p)chosen.push(p);}
 for(const p of chosen){inputs.push({id:p.id,sourceKind:'EXTERNAL_HUMAN_INK',scopeSource:'ORACLE_DATASET_EXPRESSION_MEMBERSHIP',annotationStatus:'SOURCE_AUTHORITATIVE; not manually reverified in this experiment',reference:p.annotation.units[0].transcript,sourceStrokeIds:p.source.strokes.map(s=>s.id),strokes:p.source.strokes,sourceSha256:p.sourceChecksum,imageOrigin:'EXISTING_COMER_PREPROCESS_TENSOR_PREVIEW_INVERTED_TO_WHITE',sourceRevision:p.source.sourceRevision});}
 write('selection-before-recognition.json',{rules,native,pickedExternal:chosen.map(p=>({id:p.id,label:p.annotation.units[0].transcript})),unavailableRules:rules.filter(r=>!chosen.some(p=>p.annotation.units[0].transcript.includes(r))),selectionTime:new Date().toISOString(),split:'DEV; dataset may overlap training sources, not held-out generalization'});
 const autoSource=chosen.find(p=>p.annotation.units[0].transcript.includes('\\frac'));
 const construction=constructScopeCandidates(autoSource.source,{status:'GEOMETRY_ONLY',model:'NONE',regions:[]},renderTransform(),'GEOMETRY');
 for(const s of construction.scopes.filter(s=>s.kind==='MATH'))inputs.push({id:`auto-${autoSource.id}-${s.id}`,sourceKind:'EXTERNAL_HUMAN_INK',scopeSource:'AUTOMATIC_GEOMETRY',annotationStatus:'SCOPE_MISMATCH_EXCLUDED_FROM_RECOGNITION_ACCURACY',reference:null,sourceStrokeIds:s.strokeIds,strokes:autoSource.source.strokes.filter(p=>s.strokeIds.includes(p.id)),sourceSha256:autoSource.sourceChecksum,imageOrigin:'EXISTING_COMER_PREPROCESS_TENSOR_PREVIEW_INVERTED_TO_WHITE',sourceRevision:autoSource.source.sourceRevision});
 const browser=await chromium.launch({channel:'chrome',headless:true});try{const context=await browser.newContext();await context.route('**/*',r=>['localhost','127.0.0.1'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort());const page=await context.newPage();await page.goto('http://localhost:3014/login');
  await page.evaluate(async()=>{const ort=await import('/ocr/runtime/ort.wasm.min.mjs');ort.env.wasm.wasmPaths='/ocr/runtime/';const core=await import('/ocr/ink-on/core.js');const vocab=await core.loadVocab('/ocr/comer/v0_1/vocab.json');const engine=new core.InferenceEngine({encoderUrl:'/ocr/comer/v0_1/encoder_int8.onnx',decoderUrl:'/ocr/comer/v0_1/decoder_int8.onnx',beamWidth:3,executionProvider:'wasm'});await engine.init();window.realCoMER={core,vocab,engine};});
  const results=[];
  for(const input of inputs){const modelStrokes=toModelStrokes(input.strokes);const result=await page.evaluate(async ink=>{const {core,vocab,engine}=window.realCoMER;const pre=core.preprocessStrokes(ink);const canvas=document.createElement('canvas');canvas.width=pre.width;canvas.height=pre.height;const ctx=canvas.getContext('2d'),pixels=ctx.createImageData(pre.width,pre.height);pre.tensor.forEach((v,i)=>{const c=255-Math.round(v*255);pixels.data.set([c,c,c,255],i*4);});ctx.putImageData(pixels,0,0);const t=performance.now();const value=await engine.recognize(pre,vocab,'expression');return {rawLatex:core.decodeToTokenArray(value.tokenIds,vocab).join(' '),selectedLatex:value.latex,tokenIds:value.tokenIds,durationMs:performance.now()-t,encoderMs:value.encoderMs,decoderMs:value.decoderMs,preview:canvas.toDataURL('image/png')};},modelStrokes);
    if(!input.imageData)input.imageData=result.preview;delete result.preview;
    const raw=Buffer.from(input.imageData.split(',')[1],'base64');fs.writeFileSync(path.join(out,'inputs',input.id+'.png'),raw);input.inputImageHash=sha(raw);input.imageFile='inputs/'+input.id+'.png';
    results.push({id:input.id,modelId:'CoMER/v0_1/INT8',config:{beamWidth:3,mode:'expression',executionProvider:'wasm',preprocessing:'same toModelStrokes and vendor preprocessStrokes as existing Lab'},sourceStrokeIds:input.sourceStrokeIds,...result});
    console.log('REAL_COMER '+input.id+' '+result.rawLatex);write('comer-baseline.json',results);
  }
  // Typeset diagnostic images explicitly separate from handwriting and CoMER stroke comparison.
  const katex=require(path.join(root,'frontend/node_modules/katex'));
  for(const [i,label] of ['x+1=3 \\Rightarrow x=5','2+2=5'].entries()){
    await page.setContent(`<html><head><link rel="stylesheet" href="http://localhost:3014/ocr/katex/katex.min.css"></head><body style="margin:0;padding:30px;background:white"><div id="math" style="display:inline-block;font-size:38px;padding:16px;background:white;color:black">${katex.renderToString(label,{output:'html',trust:false,throwOnError:true})}</div></body></html>`);
    // Use app's installed KaTeX CSS through its real static asset if available; otherwise style-free glyph rendering is explicitly retained in screenshot.
    const file=path.join(out,'inputs',`error-preservation-${i}.png`);await page.locator('#math').screenshot({path:file});const raw=fs.readFileSync(file);
    inputs.push({id:`error-preservation-${i}`,sourceKind:'SYNTHETIC_TYPESET_NOT_HANDWRITING',scopeSource:'DETERMINISTIC_IMAGE_GENERATION',annotationStatus:'GENERATED_LITERAL_TRANSCRIPT',reference:label,sourceStrokeIds:[],sourceSha256:sha(label),imageFile:'inputs/'+path.basename(file),inputImageHash:sha(raw),imageOrigin:'Browser KaTeX typeset screenshot; not real handwriting',imageData:'data:image/png;base64,'+raw.toString('base64')});
  }
  write('inputs.json',inputs.map(({imageData,...i})=>i));console.log('BENCHMARK_INPUTS_PREPARED '+inputs.length);
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
