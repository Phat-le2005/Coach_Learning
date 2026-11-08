import type { InkStroke, StepKind } from "@/lib/api/contracts";
import { STEP_KINDS } from "../../../lib/api/contracts";
import { constructScopeCandidates, type ScopeConstruction } from "./ocr-v2-scope-candidates";
import { buildScopeIR, renderOcrPage, renderTransform, type OcrSource, type PerceptionResult, type ScopeProposal } from "./ocr-v2-geometry";
import { applyOcrToContentUnit, validateSolutionTranscriptionIR, getRootContentUnits, type SolutionTranscriptionIR } from "./structured-transcription-ir";
import { recognizeHandwrittenMathEvidence, type HandwrittenMathEvidence } from "./handwritten-ocr";
import { renderOcrLatexHtml } from "./ocr-math-preview";

export interface RecognitionEvidence { unitId: string; sourceStrokeIds: string[]; status: string; result?: HandwrittenMathEvidence; error?: string }
export interface CoreReview {
  localVersion?: string;
  schemaVersion: "ocr-core-review/1"; ir: SolutionTranscriptionIR; scopes: ScopeProposal[];
  mode: "GEOMETRY" | "HYBRID"; detectorStatus: string; detectorError?: string;
  relations: ScopeConstruction["relations"]; evidence: RecognitionEvidence[];
  savedUnitIds: string[]; savedSteps: { unitId: string; stepId?: string | null; actionId: string }[];
  boundaries: ExplicitBoundary[];
  stepHints?: Record<string, { title: string; stepKind: StepKind | ""; explanationText?: string }>;
  segmentationVersion?: string;
  segmentationWarning?: string | null;
}
export interface ExplicitBoundary { unitId: string; stepKind: StepKind; actionId: string; contentLatex: string | null; explanationText: string }
export function sourceIdentity(source: OcrSource) { return JSON.stringify([source.pageIndex, source.sourceRevision, source.strokes]); }
export async function prepareCoreReview(source: OcrSource, attemptId: string, detector?: (png: string) => Promise<PerceptionResult>): Promise<CoreReview> {
  const snapshot = structuredClone(source), transform = renderTransform();
  let perception: PerceptionResult = { status: "NOT_CONFIGURED", model: "NONE", regions: [] };
  if (detector) {
    try { perception = await detector(renderOcrPage(snapshot, transform).png); }
    catch (error) { perception = { status: "UNAVAILABLE", model: "LAYOUT_M", regions: [], error: String(error) }; }
  }
  const mode = perception.status === "DETECTED" && perception.regions.length ? "HYBRID" : "GEOMETRY";
  const construction = constructScopeCandidates(snapshot, perception, transform, mode);
  const ir = { ...buildScopeIR(snapshot, construction.scopes), attemptId };
  if (construction.readingOrder === "AMBIGUOUS") ir.readingOrderStatus = "AMBIGUOUS";
  return { schemaVersion: "ocr-core-review/1", ir: validateSolutionTranscriptionIR(ir), scopes: construction.scopes, mode,
    detectorStatus: perception.status, detectorError: perception.error, relations: construction.relations, evidence: [], savedUnitIds: [], savedSteps: [], boundaries: [] };
}
/** No GT, exercise text, StepKind heuristic or evaluator is involved in recognition. */
export async function recognizeCoreUnit(ir: SolutionTranscriptionIR, id: string, recognize = recognizeHandwrittenMathEvidence): Promise<RecognitionEvidence> {
  const unit = ir.contentUnits.find(u => u.id === id);
  if (!unit || unit.role !== "ATOMIC" || unit.kind !== "MATH") throw Error("MATH_ATOMIC_SCOPE_REQUIRED");
  const ink = ir.sourceSnapshot.strokes.filter(s => unit.sourceStrokeIds.includes(s.id));
  try { return { unitId: id, sourceStrokeIds: [...unit.sourceStrokeIds], status: "COMPLETED", result: await recognize(ink) }; }
  catch (error) { return { unitId: id, sourceStrokeIds: [...unit.sourceStrokeIds], status: "UNRESOLVED", error: String(error) }; }
}
export function applyRecognition(review: CoreReview, evidence: RecognitionEvidence): CoreReview {
  return { ...review, evidence: [...review.evidence, evidence], ir: evidence.result ? applyOcrToContentUnit(review.ir, evidence.unitId, evidence.result.rawLatex) : review.ir };
}
/** A human explicitly declares one root content unit as one legacy step. Never an automatic projection. */
export function declareStepBoundary(review: CoreReview, unitId: string, stepKind: StepKind, actionId: string): ExplicitBoundary {
  if (!STEP_KINDS.includes(stepKind) || !actionId.trim()) throw Error("EXPLICIT_STEP_KIND_AND_ACTION_REQUIRED");
  validateSolutionTranscriptionIR(review.ir);
  const unit = getRootContentUnits(review.ir.contentUnits).find(u => u.id === unitId);
  if (!unit || unit.role !== "ATOMIC" || !["MATH", "TEXT"].includes(unit.kind)) throw Error("LEGACY_CANNOT_PRESERVE_STRUCTURE_OR_UNKNOWN");
  if (review.ir.readingOrderStatus !== "CONFIRMED" || unit.reviewStatus !== "APPROVED" || !unit.approvedContent?.trim()) throw Error("CONFIRMED_TRANSCRIPTION_AND_ORDER_REQUIRED");
  if (review.savedUnitIds.includes(unitId)) throw Error("UNIT_ALREADY_SAVED");
  if (unit.kind === "MATH" && !renderOcrLatexHtml(unit.approvedContent)) throw Error("LATEX_NOT_REPRESENTABLE; keep transcription for manual correction");
  return { unitId, stepKind, actionId, contentLatex: unit.kind === "MATH" ? unit.approvedContent : null, explanationText: unit.kind === "TEXT" ? unit.approvedContent : review.stepHints?.[unitId]?.explanationText ?? "" };
}
/** Same-origin optional layout. Absent service always means V2 Geometry, never legacy segmentation. */
export async function optionalLayout(png: string): Promise<PerceptionResult> {
  const response = await fetch("/api/ocr/layout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ png }), signal: AbortSignal.timeout(15000) });
  const body = await response.json();
  return { ...body, regions: Array.isArray(body.regions) ? body.regions : [], model: "LAYOUT_M", status: body.status ?? `HTTP_${response.status}` };
}
