import test from 'node:test';
import assert from 'node:assert/strict';
import { planAutomaticRouting, applyAutomaticTextProposal } from '../src/features/math-workspace/utils/ocr-automatic-routing';
import { buildScopeIR, type LabSource, type ScopeProposal } from '../src/features/math-workspace/utils/ocr-v2-experimental';
import { editContentUnit, approveContentUnit, confirmTranscriptionReadingOrder } from '../src/features/math-workspace/utils/structured-transcription-ir';

function fixture(){
  const strokes=Array.from({length:12},(_,i)=>({id:`s${i}`,tool:'PEN' as const,color:'#101010',width:2,points:[{x:(40+i*20)/794,y:100/1123,pressure:.5},{x:(48+i*20)/794,y:120/1123,pressure:.5}]}));
  for(let i=0;i<3;i++)strokes.push({id:`dot${i}`,tool:'PEN',color:'#101010',width:2,points:[{x:(45+i*60)/794,y:94/1123,pressure:.5},{x:(49+i*60)/794,y:96/1123,pressure:.5}]});
  const source:LabSource={pageIndex:0,sourceRevision:2,sourceKind:'SYNTHETIC_INK',datasetSplit:'DEV',consent:false,strokes};
  const scope:ScopeProposal={id:'arbitrary-scope',strokeIds:strokes.map(s=>s.id),candidateStrokeIds:strokes.map(s=>s.id),kind:'TEXT',rawLabel:'text',rawScore:null,regionIds:['r'],flags:[],coverage:{},method:'SOFTWARE_CONTROL'};
  const perception={status:'SOFTWARE_CONTROL',model:'M',regions:[{id:'r',label:'text',score:.5,box:[0,0,300,150]}]};
  return{source,scope,perception};
}
test('automatic TEXT requires layout plus distributed line evidence, not label or count alone',()=>{
  const f=fixture();assert.equal(planAutomaticRouting(f.source,[f.scope],f.perception)[0].action,'VIETOCR');
  assert.equal(planAutomaticRouting(f.source,[f.scope],{...f.perception,regions:[]})[0].action,'DEFER');
  const sparse={...f.scope,strokeIds:f.scope.strokeIds.slice(0,6)};
  assert.equal(planAutomaticRouting(f.source,[sparse],f.perception)[0].action,'DEFER');
});
test('automatic routing vetoes polynomial math cues and structural delimiters even under TEXT box',()=>{
  const f=fixture();
  for(const flag of ['BALANCED_CROSS_STROKES','MULTI_ROW_DELIMITER_UNRESOLVED','GEOMETRY_AMBIGUOUS']){
    const r=planAutomaticRouting(f.source,[{...f.scope,flags:[flag]}],f.perception)[0];assert.equal(r.action,'DEFER');
  }
  const math=planAutomaticRouting(f.source,[{...f.scope,kind:'MATH',flags:['PARALLEL_EQUALITY_STROKES']}],f.perception)[0];
  assert.equal(math.action,'COMER');assert.equal(math.proposedKind,'MATH');
});
test('UNKNOWN and MIXED abstain without recognizer-based reclassification',()=>{
  const f=fixture();
  const unknown=planAutomaticRouting(f.source,[{...f.scope,kind:'UNKNOWN',regionIds:[]}],f.perception)[0];assert.equal(unknown.action,'DEFER');
  const mixed=planAutomaticRouting(f.source,[{...f.scope,kind:'MIXED'}],f.perception)[0];assert.equal(mixed.action,'DEFER');assert.equal(mixed.proposedKind,'MIXED');
});
test('routing does not depend on capture IDs, references or mutation of source strokes',()=>{
  const f=fixture(),before=JSON.stringify(f),r=planAutomaticRouting(f.source,[f.scope],f.perception)[0];
  const source={...f.source,writerId:'reference-not-a-feature',strokes:f.source.strokes.map((s,i)=>({...s,id:`renamed-${i}`}))};
  const scope={...f.scope,id:'different-capture-name',strokeIds:source.strokes.map(s=>s.id)};
  const other=planAutomaticRouting(source,[scope],f.perception)[0];assert.equal(other.action,r.action);assert.deepEqual(other.features,r.features);assert.equal(JSON.stringify(f),before);
});
test('automatic text raw proposal never overwrites approved manual correction or auto-approves',()=>{
  const f=fixture(),id=`unit-${f.scope.id}`;let ir=buildScopeIR(f.source,[f.scope]);
  ir=applyAutomaticTextProposal(ir,id,'raw text.');assert.equal(ir.contentUnits[0].isManuallyCorrected,false);assert.equal(ir.contentUnits[0].reviewStatus,'NEEDS_REVIEW');
  ir=approveContentUnit(ir,id);ir=confirmTranscriptionReadingOrder(ir);ir=applyAutomaticTextProposal(ir,id,'changed raw text,');assert.equal(ir.reviewStatus,'NEEDS_REVIEW');
  ir=editContentUnit(ir,id,{content:'student literal correction'});ir=approveContentUnit(ir,id);const before=JSON.stringify(ir);
  const next=applyAutomaticTextProposal(ir,id,'new raw output');assert.equal(next.contentUnits[0].approvedContent,'student literal correction');assert.equal(next.contentUnits[0].reviewStatus,'APPROVED');assert.equal(next.contentUnits[0].rawRecognition,'new raw output');assert.equal(JSON.stringify(ir),before);
});
