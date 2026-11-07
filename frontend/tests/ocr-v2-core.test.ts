import test from "node:test";
import assert from "node:assert/strict";
import { createHash, webcrypto } from "node:crypto";
import { transcriptionKey } from "../src/features/math-workspace/utils/ocr-transcription-storage.js";
import type { InkStroke } from "../src/lib/api/contracts.js";
import { prepareCoreReview, applyRecognition, declareStepBoundary, sourceIdentity, recognizeCoreUnit } from "../src/features/math-workspace/utils/ocr-v2-core.js";
import { scopeIntegrity, strokeCoverage, renderTransform, groupIrUnits, ungroupIrUnit } from "../src/features/math-workspace/utils/ocr-v2-geometry.js";
import { editContentUnit, approveContentUnit, confirmTranscriptionReadingOrder } from "../src/features/math-workspace/utils/structured-transcription-ir.js";
import { createBatchApi } from "../src/features/math-workspace/utils/ocr-batch-adapter.js";
import type { ApiClient } from "../src/lib/api/client.js";

// Software geometry/invariant fixtures only, never handwriting accuracy evidence.
const stroke=(id:string,points:number[][]):InkStroke=>({id,tool:"PEN",color:"#101010",width:2,points:points.map(([x,y])=>({x,y,pressure:.5}))});
const ink=[stroke("x1",[[.1,.1],[.12,.13]]),stroke("x2",[[.12,.1],[.1,.13]]),stroke("e1",[[.15,.11],[.19,.11]]),stroke("e2",[[.15,.12],[.19,.12]]),stroke("zero",[[.21,.1],[.23,.1],[.23,.13],[.21,.13],[.21,.1]])];
const source={sourceKind:"INK" as const,pageIndex:0,sourceRevision:3,strokes:ink};

test("LAN and secure origins derive identical SHA-256 review keys, including Vietnamese ink metadata",async()=>{
 const descriptor=Object.getOwnPropertyDescriptor(globalThis,"crypto");
 const identity=JSON.stringify({source,annotation:"Ta có — Nên — Xét đề bài ta"});
 const expected=`attempt:${createHash("sha256").update(identity,"utf8").digest("hex")}`;
 try {
  Object.defineProperty(globalThis,"crypto",{configurable:true,value:webcrypto});
  assert.equal(await transcriptionKey("attempt",identity),expected);
  Object.defineProperty(globalThis,"crypto",{configurable:true,value:{}}); // HTTP LAN browser.
  assert.equal(await transcriptionKey("attempt",identity),expected);
  Object.defineProperty(globalThis,"crypto",{configurable:true,value:undefined});
  assert.equal(await transcriptionKey("attempt",identity),expected);
  assert.notEqual(await transcriptionKey("attempt",identity+"changed"),expected);
 } finally {if(descriptor)Object.defineProperty(globalThis,"crypto",descriptor);else Reflect.deleteProperty(globalThis,"crypto");}
});

test("Grouping review units on HTTP LAN preserves stroke ownership without randomUUID",async()=>{
 const r=await prepareCoreReview({...source,strokes:[...ink,...ink.map(s=>({...s,id:s.id+'-row2',points:s.points.map(p=>({...p,y:p.y+.2}))}))]},"a");
 const descriptor=Object.getOwnPropertyDescriptor(globalThis,"crypto");
 try {
  Object.defineProperty(globalThis,"crypto",{configurable:true,value:{}});
  const grouped=groupIrUnits(r.ir,r.ir.contentUnits.map(u=>u.id),"UNKNOWN");
  const container=grouped.contentUnits.find(u=>u.role==="CONTAINER")!;
  assert.match(container.id,/^container-[0-9a-f-]{36}$/);
  assert.deepEqual(new Set(container.sourceStrokeIds),new Set(r.ir.sourceSnapshot.strokes.map(s=>s.id)));
 } finally {if(descriptor)Object.defineProperty(globalThis,"crypto",descriptor);else Reflect.deleteProperty(globalThis,"crypto");}
});
test("Geometry core retains every physical stroke and immutable source; detector/render failure never falls back to legacy",async()=>{
 const before=structuredClone(source),plain=await prepareCoreReview(source,"attempt"),failed=await prepareCoreReview(source,"attempt",async()=>{throw Error("offline");});
 assert.deepEqual(source,before);assert.equal(plain.mode,"GEOMETRY");assert.equal(failed.mode,"GEOMETRY");assert.deepEqual(scopeIntegrity(source,plain.scopes).missing,[]);assert.deepEqual(scopeIntegrity(source,plain.scopes).duplicateOwnership,[]);assert.deepEqual(plain.scopes,failed.scopes);
 assert.notEqual(sourceIdentity(source),sourceIdentity({...source,sourceRevision:4}));
});
test("Region mapping measures crossed segments even with both endpoints outside",()=>{
 const s=stroke("cross",[[0,.3],[1,.3]]),t=renderTransform(0);const c=strokeCoverage(s,{id:"r",label:"text",score:null,box:[200,200,400,450]},t);
 assert.ok(c>.2&&c<.3);
});
test("Rerun preserves accepted manual wrong-math transcription and separates raw model evidence",async()=>{
 let r=await prepareCoreReview(source,"attempt");const id=r.ir.contentUnits[0].id;
 r.ir=editContentUnit(r.ir,id,{kind:"MATH",content:"x+1=3 \\Rightarrow x=5"});r.ir=approveContentUnit(r.ir,id);
 r=applyRecognition(r,{unitId:id,sourceStrokeIds:r.ir.contentUnits[0].sourceStrokeIds,status:"COMPLETED",result:{rawLatex:"x = 0",latex:"x=0",tokenIds:[1],durationMs:1,encoderMs:0,decoderMs:1}});
 assert.equal(r.ir.contentUnits[0].approvedContent,"x+1=3 \\Rightarrow x=5");assert.equal(r.ir.contentUnits[0].rawRecognition,"x = 0");assert.equal(r.evidence[0].result!.latex,"x=0");
});
test("Only explicit approved root boundaries produce legacy intents; raw/unconfirmed/UNKNOWN cannot save",async()=>{
 const r=await prepareCoreReview(source,"attempt"),id=r.ir.contentUnits[0].id;
 assert.throws(()=>declareStepBoundary(r,id,"CUSTOM","action"),/CONFIRMED/);
 r.ir=approveContentUnit(editContentUnit(r.ir,id,{kind:"TEXT",content:"Suy ra x = 5, theo bài làm của em."}),id);r.ir=confirmTranscriptionReadingOrder(r.ir);
 const b=declareStepBoundary(r,id,"EXPLANATION","explicit");assert.equal(b.contentLatex,null);assert.equal(b.explanationText,r.ir.contentUnits[0].approvedContent);
 r.ir=approveContentUnit(editContentUnit(r.ir,id,{kind:"UNKNOWN",content:"Ký hiệu chưa xác định"}),id);
 assert.throws(()=>declareStepBoundary(r,id,"CUSTOM","a"),/LEGACY_CANNOT/);
});
test("Containers and children cannot silently become grading steps",async()=>{
 const r=await prepareCoreReview({...source,strokes:[...ink,...ink.map(s=>({...s,id:s.id+'-row2',points:s.points.map(p=>({...p,y:p.y+.2}))}))]},"a");
 const ids=r.ir.contentUnits.map(u=>u.id);assert.ok(ids.length>=2);
 r.ir=groupIrUnits(r.ir,ids,"SYSTEM");
 assert.throws(()=>declareStepBoundary(r,ids[0],"CUSTOM","a"),/LEGACY_CANNOT/);
 assert.throws(()=>declareStepBoundary(r,r.ir.contentUnits.at(-1)!.id,"CUSTOM","a"),/LEGACY_CANNOT/);
 const restored=ungroupIrUnit(r.ir,r.ir.contentUnits.at(-1)!.id);assert.equal(restored.contentUnits.length,ids.length);assert.equal(new Set(restored.contentUnits.flatMap(u=>u.sourceStrokeIds)).size,r.ir.rawStrokeCount);
});
test("TEXT/UNKNOWN are not routed to CoMER; failed model evidence is explicit unresolved",async()=>{
 const r=await prepareCoreReview(source,"a"),id=r.ir.contentUnits[0].id;r.ir=editContentUnit(r.ir,id,{kind:"TEXT"});let calls=0;
 await assert.rejects(()=>recognizeCoreUnit(r.ir,id,async()=>{calls++;throw Error("no");}),/MATH_ATOMIC/);assert.equal(calls,0);
 r.ir=editContentUnit(r.ir,id,{kind:"MATH"});const evidence=await recognizeCoreUnit(r.ir,id,async()=>{calls++;throw Error("model unavailable");});assert.equal(evidence.status,"UNRESOLVED");assert.equal(calls,1);
});
test("Stale-source guard blocks batch mutation before API writes",async()=>{
 let writes=0;const client={createMathStep:async()=>{writes++;}} as unknown as ApiClient;
 const api=createBatchApi(client,"",async()=>{throw Error("SOURCE_CHANGED");});
 await assert.rejects(()=>api.addStep("a",{expected_attempt_revision:1,client_action_id:"a",step_type:"CUSTOM",content_latex:"x=5",explanation_text:null}),/SOURCE_CHANGED/);assert.equal(writes,0);
});
