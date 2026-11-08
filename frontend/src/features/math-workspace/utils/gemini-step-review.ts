import type { OCRRecognizeResponse, StepKind } from "@/lib/api/contracts";
import { buildScopeIR, type OcrSource, type ScopeProposal } from "./ocr-v2-geometry";
import { applyOcrToContentUnit, validateSolutionTranscriptionIR, type SolutionTranscriptionIR } from "./structured-transcription-ir";
import type { CoreReview } from "./ocr-v2-core";

/** Source scopes use the shared constructor. Logical boundaries are proposals
 * until the student confirms them; no server steps or grades are created here. */
export function buildGeminiStepReview(source: OcrSource, attemptId: string, response?: OCRRecognizeResponse): CoreReview {
  const pen = source.strokes.filter(stroke => stroke.tool === "PEN");
  const proposed = response?.steps ?? [];
  const ids = proposed.flatMap(step => step.source_stroke_ids);
  if (proposed.length && (new Set(ids).size !== ids.length || ids.length !== pen.length
      || ids.some(id => !pen.some(stroke => stroke.id === id)))) throw Error("Ranh giới bước chưa khớp toàn bộ nét gốc. Hãy nhận diện lại.");
  const scopes: ScopeProposal[] = proposed.length ? proposed.map((step, index) => ({
    id: `gemini-step-${index + 1}`, regionIds: [`gemini-region-${index + 1}`],
    rawLabel: step.content_kind === "MATH" ? "formula" : "text", rawScore: null, kind: step.content_kind,
    strokeIds: [...step.source_stroke_ids], candidateStrokeIds: [...step.source_stroke_ids], coverage: {},
    flags: ["GEMINI_LOGICAL_STEP_PROPOSAL_NOT_CONFIRMED"], method: "GEMINI_LOGICAL_STEP_IMAGE_BOUNDARY",
  })) : pen.length ? [{ id: "gemini-1", regionIds: ["gemini-region-1"], rawLabel: "formula", rawScore: null,
    kind: "MATH", strokeIds: pen.map(s => s.id), candidateStrokeIds: pen.map(s => s.id), coverage: {},
    flags: ["UNSEGMENTED_TRANSCRIPTION_REQUIRES_REVIEW"], method: "GEMINI_UNSEGMENTED_PAGE" }] : [];
  let ir: SolutionTranscriptionIR = { ...buildScopeIR(source, scopes), attemptId };
  const stepHints: NonNullable<CoreReview["stepHints"]> = {};
  for (const [index, scope] of scopes.entries()) {
    const id = `unit-${scope.id}`, step = proposed[index];
    const text = step ? step.content_kind === "TEXT" ? step.explanation_text || step.latex : step.latex : response?.latex;
    if (text?.trim()) ir = applyOcrToContentUnit(ir, id, text);
    stepHints[id] = { title: step?.title ?? "Bản chép chưa tách bước", stepKind: step?.suggested_step_type ?? response?.suggested_step_type ?? "CUSTOM",
      explanationText: step?.content_kind === "MATH" ? step.explanation_text ?? "" : "" };
  }
  ir.contentUnits = ir.contentUnits.map(unit => ({ ...unit, readingOrder: scopes.findIndex(scope => unit.id === `unit-${scope.id}`) }));
  return { schemaVersion: "ocr-core-review/1", ir: validateSolutionTranscriptionIR(ir, pen), scopes,
    mode: "HYBRID", detectorStatus: "GEMINI_VISION", relations: [], evidence: [], savedUnitIds: [], savedSteps: [], boundaries: [],
    stepHints, segmentationVersion: proposed.length ? "gemini-logical-steps/1" : undefined,
    segmentationWarning: response?.segmentation_warning ?? (response && !proposed.length ? "Bản chép chưa có đề xuất chia bước. Có thể nhận diện lại hoặc chia phạm vi thủ công." : null) };
}

export function suggestedStepKind(review: CoreReview | null, id: string): StepKind | "" {
  return review?.stepHints?.[id]?.stepKind ?? "";
}
