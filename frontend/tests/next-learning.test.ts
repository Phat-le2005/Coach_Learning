import test from "node:test";
import assert from "node:assert/strict";
import { parseNextLearning, learningLinks, afterAttempt } from "../src/features/math-workspace/utils/next-learning";
const id="00000000-0000-4000-8000-000000000101";
const base={attempt_id:id,decision_id:null,status:"WAITING_REVIEW",score:null,evidence_recorded:false,headline:"Cần đối chiếu",
  explanation:"Chưa có điểm",criterion_gaps:[],target:null,question:null,supply_message:null};
test("provisional advice cannot acquire an invented official score",()=>{
  assert.equal(parseNextLearning(base,id).score,null);
  assert.throws(()=>parseNextLearning({...base,score:.5},id));
  assert.throws(()=>parseNextLearning({...base,attempt_id:"other"},id));
});
test("invalid or unrelated launch data is rejected before rendering controls",()=>{
  assert.throws(()=>parseNextLearning({...base,status:"CONTINUE",question:{id,content:"test",difficulty:.5}},id));
  assert.throws(()=>parseNextLearning({...base,criterion_gaps:[{title:"Bad",achieved:.8,maximum:.5,step_index:1}]},id));
});
test("theory search is scoped to the curriculum label and URL encoded",()=>{
  const value=parseNextLearning({...base,target:{id,kind:"CONCEPT",name:"Đạo hàm & dấu",reason:"Củng cố",mastery_score:null,mastery_state:null,evidence_count:0,next_review_at:null}},id);
  assert.equal(new URL(learningLinks(value).theory,"http://local").searchParams.get("topic"),"Đạo hàm & dấu");
  const plan=new URL(learningLinks(value).plan,"http://local");
  assert.equal(afterAttempt(plan.search),id);
  assert.equal(plan.hash,"#learning-pulse");
  assert.equal(afterAttempt('?after_attempt=another-student-url'),null);
});
