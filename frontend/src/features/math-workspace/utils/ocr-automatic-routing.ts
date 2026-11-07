import { computeBounds, validateSolutionTranscriptionIR, type SolutionTranscriptionIR } from "./structured-transcription-ir";
import { routeLabel, sourceKey, validateLabSource, type LabSource, type PerceptionResult, type ScopeProposal } from "./ocr-v2-experimental";
import type { HtrEvidence } from "./vietnamese-htr";
import { constructScopeCandidates } from "./ocr-v2-scope-candidates";
import { renderTransform } from "./ocr-v2-experimental";
import { sha256Hex } from "./ocr-digest";

export interface AutomaticRoute {
  scopeId: string; sourceStrokeIds: string[]; originalKind: ScopeProposal["kind"];
  proposedKind: ScopeProposal["kind"]; action: "COMER" | "VIETOCR" | "DEFER";
  reasons: string[]; features: { bodyPx: number; bodyMarks: number; occupiedBodyBins: number; smallMarks: number; widthBody: number; heightBody: number; layoutLabels: string[] };
  subregionCandidates?: { sourceStrokeIds: string[]; proposedKind: ScopeProposal["kind"]; status: string }[];
}
/** Conservative, uncalibrated rule evidence. No sample identity, reference or OCR output. */
export function planAutomaticRouting(source: LabSource, scopes: ScopeProposal[], perception: PerceptionResult): AutomaticRoute[] {
  const pen = validateLabSource(source), heights = pen.map(s => { const b = computeBounds([s]); return (b.bottom-b.top)*1123; }).filter(h => h >= 8).sort((a,b) => a-b);
  const body = Math.max(8, heights[Math.floor(heights.length/2)] ?? 20);
  return scopes.filter(s => s.strokeIds.length).map(s => {
    const ink = pen.filter(p => s.strokeIds.includes(p.id));
    if (ink.length !== s.strokeIds.length || new Set(s.strokeIds).size !== ink.length) throw Error("AUTOMATIC_SCOPE_MEMBERSHIP_MISMATCH");
    const b = computeBounds(ink), boxes = ink.map(p => { const a=computeBounds([p]); return { x:(a.left+a.right)*397, w:(a.right-a.left)*794, h:(a.bottom-a.top)*1123 }; });
    const regular = boxes.filter(p => p.h >= body*.45 && p.h <= body*1.8 && p.w >= body*.08 && p.w <= body*2.8);
    const small = boxes.filter(p => p.h < body*.5 && p.w < body*.9);
    const labels = perception.regions.filter(r => s.regionIds.includes(r.id)).map(r => r.label);
    const features = { bodyPx:body, bodyMarks:regular.length, occupiedBodyBins:new Set(regular.map(p => Math.floor((p.x-b.left*794)/body))).size,
      smallMarks:small.length, widthBody:(b.right-b.left)*794/body, heightBody:(b.bottom-b.top)*1123/body, layoutLabels:labels };
    const row:AutomaticRoute={scopeId:s.id,sourceStrokeIds:ink.map(p=>p.id),originalKind:s.kind,proposedKind:"UNKNOWN",action:"DEFER",reasons:[],features};
    if (s.kind === "MIXED") {
      const children=constructScopeCandidates({...source,strokes:ink},{status:"MIXED_SUBREGION_ANALYSIS",model:"NONE",regions:[]},renderTransform(),"GEOMETRY").scopes;
      return {...row,proposedKind:"MIXED",reasons:["MIXED_NEEDS_SAFE_SUBREGIONS; whole mixed crop not dispatched"],
        subregionCandidates:children.length>1&&children.length<=8?children.map(ch=>({sourceStrokeIds:ch.strokeIds,proposedKind:ch.kind,status:"ALTERNATIVE_ONLY; no active ownership or dispatch until boundaries resolved"})):[]};
    }
    if (s.flags.includes("MULTI_ROW_DELIMITER_UNRESOLVED")) return {...row,reasons:["STRUCTURAL_DELIMITER; never text inference"]};
    if (s.flags.some(f=>f.includes("GEOMETRY_AMBIGUOUS")||f.startsWith("BOUNDARY_CROSSING")||f.startsWith("OVERLAPPING_CANDIDATES")||f==="ORPHAN_SOURCE_INK")) return {...row,reasons:["UNRESOLVED_GEOMETRY; preserve/probe manually"]};
    const mathCues=["PARALLEL_EQUALITY_STROKES","FRACTION_BAR_WITH_ABOVE_BELOW_SUPPORT","BALANCED_CROSS_STROKES","LOCAL_OPERATOR_LIMITS","FORMULA_LABEL_MATCHES_INDEPENDENT_GEOMETRY"];
    const math=s.flags.filter(f=>mathCues.includes(f));
    if (s.kind === "MATH" && math.length) return {...row,proposedKind:"MATH",action:"COMER",reasons:["EXISTING_SUPPORTED_MATH_ROUTE",...math]};
    // One cross/raised-mark cue can be insufficient to classify math, but is enough
    // to veto automatic text. A wide detector TEXT box is never sufficient alone.
    if (math.length) return {...row,reasons:["POSSIBLE_MATH; TEXT_DISPATCH_VETO",...math]};
    const textSignal=labels.some(l=>routeLabel(l)==="TEXT");
    const distributedLine=features.bodyMarks>=8 && features.occupiedBodyBins>=6 && features.smallMarks>=2 && features.widthBody>=6 && features.heightBody<=3;
    if (textSignal && distributedLine) return {...row,proposedKind:"TEXT",action:"VIETOCR",reasons:["LAYOUT_TEXT_PLUS_DISTRIBUTED_BODY_AND_SMALL_MARKS; uncalibrated proposal", "NO_POSITIVE_MATH_OR_STRUCTURE_CUE; raw output still unconfirmed"]};
    return {...row,reasons:[textSignal?"TEXT_LABEL_WITHOUT_SUFFICIENT_LINE_EVIDENCE":"NO_INDEPENDENT_TEXT_EVIDENCE; short prose and math cannot be safely distinguished"]};
  });
}

/** Lab adapter only. Store raw text evidence without marking human correction. */
export function applyAutomaticTextProposal(ir: SolutionTranscriptionIR, id: string, raw: string): SolutionTranscriptionIR {
  validateSolutionTranscriptionIR(ir);
  const unit=ir.contentUnits.find(u=>u.id===id);
  if (!unit || unit.role!=="ATOMIC" || unit.kind!=="TEXT" || !raw.trim()) throw Error("AUTOMATIC_TEXT_REQUIRES_TEXT_ATOMIC_NONEMPTY");
  const invalid=new Set<string>();
  if (!unit.isManuallyCorrected && unit.rawRecognition!==raw) {
    invalid.add(id); let changed=true;
    while(changed){changed=false;for(const u of ir.contentUnits)if(!invalid.has(u.id)&&u.childIds.some(ch=>invalid.has(ch))){invalid.add(u.id);changed=true;}}
  }
  const units=ir.contentUnits.map(u=>({...u,...(u.id===id?{rawRecognition:raw,recognitionStatus:unit.isManuallyCorrected?"MANUALLY_CORRECTED" as const:"RECOGNIZED" as const,
    approvedContent:!unit.isManuallyCorrected&&invalid.has(id)?null:u.approvedContent}:{}),...(invalid.has(u.id)?{reviewStatus:"NEEDS_REVIEW" as const}:{})}));
  return validateSolutionTranscriptionIR({...ir,contentUnits:units,recognizedUnitCount:units.filter(u=>u.rawRecognition!==null).length,
    approvedUnitCount:units.filter(u=>u.reviewStatus==="APPROVED").length,reviewStatus:invalid.size?"NEEDS_REVIEW":ir.reviewStatus});
}

export async function recognizeAutomaticText(source: LabSource, scope: ScopeProposal, perception: PerceptionResult, png:string, signal?:AbortSignal):Promise<HtrEvidence> {
  if(process.env.NODE_ENV==="production")throw Error("AUTOMATIC_HTR_LAB_ONLY");
  const route=planAutomaticRouting(source,[scope],perception)[0];
  if(route?.action!=="VIETOCR")throw Error("AUTOMATIC_HTR_ROUTE_NOT_ELIGIBLE");
  const hash=sha256Hex;
  const key=await hash(new TextEncoder().encode(sourceKey(source))),imageHash=await hash(Uint8Array.from(atob(png.split(',')[1]),c=>c.charCodeAt(0)));
  const response=await fetch('/api/ocr-v2-lab/htr/scope',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source,scope,perception,png}),
    signal:signal?AbortSignal.any([signal,AbortSignal.timeout(120000)]):AbortSignal.timeout(120000)});
  const result=await response.json();if(!response.ok||result.status!=="COMPLETED")throw Error(result.error??`HTR_HTTP_${response.status}`);
  if(result.sourceSnapshotSha256!==key||result.inputImageHash!==imageHash||result.sourceRevision!==source.sourceRevision||result.pageIndex!==source.pageIndex
    ||JSON.stringify(result.sourceStrokeIds)!==JSON.stringify(route.sourceStrokeIds))throw Error("AUTOMATIC_HTR_SOURCE_MISMATCH");
  return {...result,normalizedTranscript:result.rawTranscript.normalize('NFC')};
}
