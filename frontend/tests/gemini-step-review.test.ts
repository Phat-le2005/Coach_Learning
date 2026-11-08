import test from "node:test";
import assert from "node:assert/strict";
import type { OCRRecognizeResponse, InkStroke } from "../src/lib/api/contracts.js";
import { buildGeminiStepReview } from "../src/features/math-workspace/utils/gemini-step-review.js";
import { approveContentUnit, confirmTranscriptionReadingOrder, editContentUnit, getRootContentUnits } from "../src/features/math-workspace/utils/structured-transcription-ir.js";
import { declareStepBoundary } from "../src/features/math-workspace/utils/ocr-v2-core.js";

const strokes: InkStroke[]=[.1,.35,.65].map((y,index)=>({id:`stroke-${index}`,tool:"PEN",color:"#000000",width:2,points:[{x:.1,y,pressure:.5},{x:.3,y:y+.02,pressure:.5}]}));
const source={pageIndex:0,sourceRevision:1,sourceKind:"INK" as const,strokes};
const response:OCRRecognizeResponse={latex:"whole page",confidence:.9,suggested_step_type:"CUSTOM",explanation_text:null,detected_symbols:[],alternative_latex:[],steps:[
  {title:"Đạo hàm",content_kind:"MATH",latex:"y'=2x",explanation_text:null,suggested_step_type:"DERIVATIVE_CALCULATION",source_stroke_ids:["stroke-0"]},
  {title:"Tìm nghiệm",content_kind:"MATH",latex:String.raw`x=1 \lor x=-1`,explanation_text:null,suggested_step_type:"ROOT_FINDING",source_stroke_ids:["stroke-1"]},
  {title:"Bảng biến thiên",content_kind:"MATH",latex:String.raw`\begin{array}{c|cc}x&-1&1\\y'&0&0\end{array}`,explanation_text:null,suggested_step_type:"VARIATION_TABLE",source_stroke_ids:["stroke-2"]},
]};

test("one OCR page proposes three ordered steps without confirming or saving them",()=>{
  const review=buildGeminiStepReview(source,"attempt",response);
  assert.equal(review.ir.contentUnits.length,3);
  assert.deepEqual(review.ir.sourceSnapshot.strokes,strokes);
  assert.equal(review.ir.approvedUnitCount,0);
  assert.deepEqual(review.boundaries,[]);
  assert.deepEqual(review.savedSteps,[]);
  assert.deepEqual(review.ir.contentUnits.map(u=>u.rawRecognition),response.steps!.map(s=>s.latex));
});

test("corrected proposals become separate explicit grading intents only after confirmation",()=>{
  const review=buildGeminiStepReview(source,"attempt",response);
  const ids=review.ir.contentUnits.map(u=>u.id);
  assert.throws(()=>declareStepBoundary(review,ids[0],"DERIVATIVE_CALCULATION","action"),/CONFIRMED/);
  review.ir=editContentUnit(review.ir,ids[0],{content:"y'=3x^2-3"});
  for(const id of ids) review.ir=approveContentUnit(review.ir,id);
  review.ir=confirmTranscriptionReadingOrder(review.ir);
  const plans=ids.map((id,index)=>declareStepBoundary(review,id,response.steps![index].suggested_step_type,`action-${index}`));
  assert.deepEqual(plans.map(p=>p.stepKind),["DERIVATIVE_CALCULATION","ROOT_FINDING","VARIATION_TABLE"]);
  assert.equal(plans[0].contentLatex,"y'=3x^2-3");
  assert.match(plans[2].contentLatex!,/begin\{array\}/);
});

test("incomplete, overlapping or invented stroke ownership is rejected without altering source",()=>{
  for(const ids of [["stroke-1"],["missing"]]){
    const bad=structuredClone(response);bad.steps![0].source_stroke_ids=ids;
    assert.throws(()=>buildGeminiStepReview(source,"attempt",bad),/nét gốc/);
  }
  assert.equal(source.strokes.length,3);
});

test("proposed reading order is applied atomically even when spatial order differs",()=>{
  const reversed=structuredClone(response);reversed.steps!.reverse();
  const review=buildGeminiStepReview(source,"attempt",reversed);
  assert.deepEqual(getRootContentUnits(review.ir.contentUnits).map(u=>u.sourceStrokeIds[0]),["stroke-2","stroke-1","stroke-0"]);
});
