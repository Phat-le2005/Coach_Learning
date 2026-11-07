import type { InkStroke } from "@/lib/api/contracts";
import type { OcrEvalCaptureV1 } from "./ocr-eval-capture";
import { validateOcrEvalCapture, type OcrGroundTruthV1, type GroundTruthGroup } from "./ocr-eval-replay";
import { segmentPageInk_v2 } from "./page-ocr";
import { detectStructuralCandidates } from "./structural-candidate-engine";
import { proposeIntegralExpressionUnits } from "./expression-reconstruction";
import { buildStructuredTranscriptionIR } from "./structured-transcription-ir";
import type { MathScopeDiagnostic, PreprocessVariant } from "./ocr-model-diagnostics";

export type AutoProfile = "LEGACY_REGIONS" | "IR_ATOMIC";
export interface RecognitionScope {
  id: string; strokeIds: string[]; source: "AUTO" | "HUMAN_ORACLE";
  profile: AutoProfile | "HUMAN_ANNOTATION"; kind: string;
  runnable: boolean; skipReason: string | null;
}

export function selectScopeStrokes(capture: OcrEvalCaptureV1, ids: readonly string[]): InkStroke[] {
  if (!ids.length || new Set(ids).size !== ids.length) throw new Error("EMPTY_OR_DUPLICATE_SCOPE_STROKE_IDS");
  const source = capture.strokes.filter((s) => s.tool === "PEN" && s.points.length);
  if (ids.some((id) => !source.some((s) => s.id === id))) throw new Error("ANNOTATION_UNKNOWN_SOURCE_STROKE");
  // Preserve original drawing order, never annotation JSON order.
  return structuredClone(source.filter((s) => ids.includes(s.id)));
}

export function buildAutomaticScopes(input: OcrEvalCaptureV1, profile: AutoProfile): RecognitionScope[] {
  const capture = validateOcrEvalCapture(input);
  const regions = segmentPageInk_v2(capture.strokes);
  if (profile === "LEGACY_REGIONS") return regions.map((r) => ({ id: r.id, strokeIds: r.strokes.map((s) => s.id),
    source: "AUTO", profile, kind: "MATH", runnable: true, skipReason: null }));
  if (profile !== "IR_ATOMIC") throw new Error("UNKNOWN_AUTO_PROFILE");
  const ir = buildStructuredTranscriptionIR({ pageIndex: capture.pageIndex, strokes: capture.strokes, regions,
    structuralCandidates: detectStructuralCandidates(capture.strokes), integralUnits: proposeIntegralExpressionUnits(capture.strokes) });
  return ir.contentUnits.map((u) => ({ id: u.id, strokeIds: [...u.sourceStrokeIds], source: "AUTO", profile, kind: u.kind,
    runnable: u.role === "ATOMIC" && u.kind === "MATH",
    skipReason: u.role === "CONTAINER" ? "NOT_SENT_CONTAINER_IN_CURRENT_IR_REVIEW" : u.kind !== "MATH" ? "NOT_SENT_NON_MATH" : null }));
}

export function annotationTemplate(captureSha256: string, captureFile: string): OcrGroundTruthV1 {
  return { schemaVersion: 1, sampleId: captureFile, captureFile, captureSha256, annotationStatus: "DRAFT",
    annotator: { kind: "HUMAN" }, labelSource: "HUMAN_INDEPENDENT_OF_OCR", expectedGroups: [],
    annotationNotes: "Select ink and transcribe before viewing any OCR. Mark HUMAN_VERIFIED only after independent human review." };
}

/** Extends existing OcrGroundTruthV1; never derives labels from OCR or captured predictions. */
export function validateRecognitionAnnotation(data: unknown, capture: OcrEvalCaptureV1, captureSha256: string): OcrGroundTruthV1 {
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("INVALID_ANNOTATION");
  const a = structuredClone(data) as OcrGroundTruthV1;
  if (a.schemaVersion !== 1 || !a.sampleId?.trim() || a.captureSha256 !== captureSha256 || !/^[a-f0-9]{64}$/.test(captureSha256)) throw new Error("ANNOTATION_SOURCE_IDENTITY_MISMATCH");
  if (!["DRAFT", "HUMAN_VERIFIED"].includes(a.annotationStatus ?? "") || a.annotator?.kind !== "HUMAN" || a.labelSource !== "HUMAN_INDEPENDENT_OF_OCR" || !Array.isArray(a.expectedGroups)) throw new Error("ANNOTATION_INDEPENDENT_HUMAN_PROVENANCE_REQUIRED");
  if (a.writerId !== undefined && (typeof a.writerId !== "string" || !a.writerId.trim())) throw new Error("INVALID_WRITER_ID");
  const groups = new Map<string, GroundTruthGroup>();
  for (const g of a.expectedGroups) {
    if (!g || typeof g.groupId !== "string" || !g.groupId.trim() || groups.has(g.groupId)) throw new Error("DUPLICATE_OR_INVALID_GROUP_ID");
    if (!Array.isArray(g.strokeIds) || g.strokeIds.some((id) => typeof id !== "string")) throw new Error("INVALID_ANNOTATION_STROKES");
    selectScopeStrokes(capture, g.strokeIds);
    if (!["MATH", "TEXT", "UNKNOWN", "STRUCTURE"].includes(g.contentKind ?? "")) throw new Error("INVALID_ANNOTATION_CONTENT_KIND");
    if (g.latex !== null && g.latex !== undefined && typeof g.latex !== "string") throw new Error("INVALID_ANNOTATION_LATEX");
    if (g.text !== null && g.text !== undefined && typeof g.text !== "string") throw new Error("INVALID_ANNOTATION_TEXT");
    if (a.annotationStatus === "HUMAN_VERIFIED" && g.contentKind === "MATH" && !g.latex?.trim()) throw new Error("HUMAN_MATH_LABEL_REQUIRED");
    if (g.childGroupIds && (!Array.isArray(g.childGroupIds) || new Set(g.childGroupIds).size !== g.childGroupIds.length)) throw new Error("INVALID_ANNOTATION_CHILDREN");
    groups.set(g.groupId, g);
  }
  const parents = new Map<string, string>();
  for (const g of groups.values()) for (const id of g.childGroupIds ?? []) {
    const child = groups.get(id);
    if (!child || parents.has(id) || child.strokeIds.some((sid) => !g.strokeIds.includes(sid))) throw new Error("INVALID_ANNOTATION_RELATION");
    parents.set(id, g.groupId);
  }
  const ancestor = (child: string, parent: string) => {
    const seen = new Set<string>(); let id: string | undefined = child;
    while (id !== undefined) { if (seen.has(id)) throw new Error("CYCLIC_ANNOTATION_RELATION"); seen.add(id); id = parents.get(id); if (id === parent) return true; }
    return false;
  };
  for (const g of groups.values()) if (ancestor(g.groupId, g.groupId)) throw new Error("CYCLIC_ANNOTATION_RELATION");
  const list = [...groups.values()];
  for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
    const a = list[i], b = list[j];
    if (a.strokeIds.some((id) => b.strokeIds.includes(id)) && !ancestor(a.groupId, b.groupId) && !ancestor(b.groupId, a.groupId)) throw new Error("DUPLICATE_UNRELATED_ANNOTATION_OWNERSHIP");
  }
  return a;
}

export function compareScopeSets(scope: RecognitionScope, groups: readonly GroundTruthGroup[]) {
  return groups.filter((g) => g.contentKind === "MATH").map((g) => {
    const intersection = scope.strokeIds.filter((id) => g.strokeIds.includes(id));
    const missing = g.strokeIds.filter((id) => !scope.strokeIds.includes(id));
    const extra = scope.strokeIds.filter((id) => !g.strokeIds.includes(id));
    return { groupId: g.groupId, intersection, missingStrokeIds: missing, extraStrokeIds: extra,
      match: !intersection.length ? "NO_OVERLAP" : !missing.length && !extra.length ? "EXACT" : !extra.length ? "SPLIT_FRAGMENT" : !missing.length ? "MERGED_OR_EXTRA" : "PARTIAL_OVERLAP" };
  });
}

function tokens(latex: string): string[] { return latex.match(/\\[a-zA-Z]+|\\.|[a-zA-Z]|[0-9]|[^\s]/g) ?? []; }
function distance(a: string[], b: string[]): number {
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 0; i < a.length; i++) { const next = [i + 1]; for (let j = 0; j < b.length; j++) next.push(Math.min(next[j] + 1, prev[j + 1] + 1, prev[j] + Number(a[i] !== b[j]))); prev = next; }
  return prev[b.length];
}
export function compareRecognition(prediction: string, label: string) {
  const p = tokens(prediction), g = tokens(label);
  const markers = ["\\frac", "\\sqrt", "\\int", "^", "_", "\\begin", "\\end"];
  return { tokenExact: JSON.stringify(p) === JSON.stringify(g), tokenEditDistance: distance(p, g), referenceTokenCount: g.length,
    metric: "CONSERVATIVE_LEXICAL_TOKENS; not mathematical equivalence", structureMarkerDifferences: markers.filter((m) => p.filter((t) => t === m).length !== g.filter((t) => t === m).length) };
}

export interface ScopeRun { scope: RecognitionScope; diagnostic: MathScopeDiagnostic | { status: "SKIPPED" | "ERROR"; reason: string }; }
export async function evaluateCapture(params: {
  capture: OcrEvalCaptureV1; captureSha256: string; annotation?: unknown; profiles: AutoProfile[]; e2?: boolean;
  recognize: (strokes: readonly InkStroke[], variant?: PreprocessVariant) => Promise<MathScopeDiagnostic>;
}) {
  const capture = validateOcrEvalCapture(params.capture), inputBefore = JSON.stringify(params.capture);
  const annotation = params.annotation ? validateRecognitionAnnotation(params.annotation, capture, params.captureSha256) : null;
  const trusted = annotation?.annotationStatus === "HUMAN_VERIFIED";
  const groups = annotation?.expectedGroups ?? [];
  const auto = params.profiles.flatMap((profile) => buildAutomaticScopes(capture, profile));
  const oracle: RecognitionScope[] = trusted ? groups.map((g) => ({ id: g.groupId, strokeIds: [...g.strokeIds], source: "HUMAN_ORACLE", profile: "HUMAN_ANNOTATION",
    kind: g.contentKind!, runnable: g.contentKind === "MATH", skipReason: g.contentKind === "MATH" ? null : "COMER_MATH_ONLY" })) : [];
  const runs: ScopeRun[] = [];
  for (const scope of [...auto, ...oracle]) {
    if (!scope.runnable) { runs.push({ scope, diagnostic: { status: "SKIPPED", reason: scope.skipReason! } }); continue; }
    try { runs.push({ scope, diagnostic: await params.recognize(selectScopeStrokes(capture, scope.strokeIds), "default") }); }
    catch (error) { runs.push({ scope, diagnostic: { status: "ERROR", reason: error instanceof Error ? error.message : String(error) } }); }
  }
  const comparisons = runs.map((run) => {
    const matches = compareScopeSets(run.scope, groups);
    const exact = matches.filter((m) => m.match === "EXACT");
    const ambiguous = run.scope.source === "AUTO" && (exact.length !== 1 || auto.filter((s) => s.profile === run.scope.profile && s.runnable &&
      compareScopeSets(s, groups).some((m) => m.groupId === exact[0]?.groupId && m.match === "EXACT")).length !== 1);
    const group = run.scope.source === "HUMAN_ORACLE" ? groups.find((g) => g.groupId === run.scope.id) : !ambiguous ? groups.find((g) => g.groupId === exact[0].groupId) : undefined;
    const reference = trusted && group?.contentKind === "MATH" && group.latex?.trim() ? group : null;
    const d = run.diagnostic;
    return { scopeId: run.scope.id, source: run.scope.source, profile: run.scope.profile, scopeMatches: matches,
      alignment: !trusted ? "BLOCKED_MISSING_HUMAN_GROUND_TRUTH" : run.scope.source === "HUMAN_ORACLE" ? "HUMAN_DEFINED" : ambiguous ? "SEGMENTATION_OR_ALIGNMENT_ERROR" : "EXACT",
      groundTruthGroupId: reference?.groupId ?? null,
      recognition: reference && d.status === "COMPLETED" ? { raw: compareRecognition(d.rawLatex, reference.latex!), postprocessed: compareRecognition(d.postprocessedLatex, reference.latex!),
        selected: compareRecognition(d.selectedLatex, reference.latex!) } : null };
  });
  const sensitivity: { scopeId: string; variant: PreprocessVariant; diagnostic: ScopeRun["diagnostic"] }[] = [];
  if (params.e2 && trusted) for (const scope of oracle.filter((s) => s.runnable)) for (const variant of ["width-075", "width-125"] as const) {
    try { sensitivity.push({ scopeId: scope.id, variant, diagnostic: await params.recognize(selectScopeStrokes(capture, scope.strokeIds), variant) }); }
    catch (error) { sensitivity.push({ scopeId: scope.id, variant, diagnostic: { status: "ERROR", reason: error instanceof Error ? error.message : String(error) } }); }
  }
  if (JSON.stringify(params.capture) !== inputBefore) throw new Error("CAPTURE_MUTATED_DURING_EVALUATION");
  const penIds = capture.strokes.filter((s) => s.tool === "PEN" && s.points.length).map((s) => s.id);
  const oracleRuns = runs.filter((r) => r.scope.source === "HUMAN_ORACLE" && r.scope.runnable);
  const oracleErrors = oracleRuns.filter((r) => r.diagnostic.status === "ERROR").length;
  const scoredOracle = comparisons.filter((c) => c.source === "HUMAN_ORACLE" && c.recognition);
  const oracleDenominator = oracleRuns.length - oracleErrors; // abstentions count as failures; infrastructure errors reported separately
  const oracleExact = scoredOracle.filter((c) => c.recognition!.selected.tokenExact).length;
  const scopeQuality = params.profiles.map((profile) => ({ profile,
    groups: trusted ? groups.filter((g) => g.contentKind === "MATH").map((g) => {
      const overlapping = auto.filter((s) => s.profile === profile && s.runnable && s.strokeIds.some((id) => g.strokeIds.includes(id)));
      const exact = overlapping.filter((s) => compareScopeSets(s, [g])[0].match === "EXACT");
      return { groupId: g.groupId, exactUniqueMatch: exact.length === 1, overlappingScopeIds: overlapping.map((s) => s.id),
        missingFromRunnableScopes: g.strokeIds.filter((id) => !overlapping.some((s) => s.strokeIds.includes(id))),
        splitFragmentCount: overlapping.filter((s) => compareScopeSets(s, [g])[0].match === "SPLIT_FRAGMENT").length,
        extraStrokeScopeCount: overlapping.filter((s) => compareScopeSets(s, [g])[0].extraStrokeIds.length > 0).length };
    }) : "BLOCKED_MISSING_HUMAN_GROUND_TRUTH" }));
  return { schemaVersion: "ocr-diagnostics/1", status: !penIds.length ? "BLOCKED_MISSING_REAL_INK" : trusted && groups.some((g) => g.contentKind === "MATH") ? "EVALUATED_WITH_DECLARED_HUMAN_GROUND_TRUTH" : "BLOCKED_MISSING_HUMAN_GROUND_TRUTH",
    captureSha256: params.captureSha256, annotationStatus: annotation?.annotationStatus ?? "MISSING", writerId: annotation?.writerId ?? "NOT_AVAILABLE",
    profiles: params.profiles, runs, comparisons, sensitivity, scopeQuality,
    summary: { sourcePenStrokeCount: penIds.length, annotatedGroups: groups.length, labeledMathScopes: trusted ? oracle.filter((s) => s.runnable).length : 0,
      unannotatedStrokeIds: penIds.filter((id) => !groups.some((g) => g.strokeIds.includes(id))),
      unannotatedAutomaticScopes: comparisons.filter((c) => c.source === "AUTO" && !c.recognition).length,
      inferenceCalls: runs.filter((r) => r.scope.runnable).length + sensitivity.length,
      completedInferences: runs.filter((r) => r.diagnostic.status === "COMPLETED").length + sensitivity.filter((r) => r.diagnostic.status === "COMPLETED").length,
      oracleRecognitionFailures: comparisons.filter((c) => c.source === "HUMAN_ORACLE" && c.recognition && !c.recognition.selected.tokenExact).length,
      oracleQuality: { labeled: oracleRuns.length, completed: scoredOracle.length, inferenceErrors: oracleErrors,
        abstentions: oracleRuns.filter((r) => r.diagnostic.status === "ABSTAIN_NOT_MEANINGFUL").length,
        selectedTokenExact: oracleExact, denominatorIncludingAbstentions: oracleDenominator,
        selectedTokenExactRate: oracleDenominator > 0 ? oracleExact / oracleDenominator : null,
        limitation: "Conservative lexical exactness; declared human labels, not generalization or semantic accuracy" },
      metricsAreAccuracyEvidence: trusted && oracleDenominator > 0,
      e2: !params.e2 ? "NOT_REQUESTED" : !trusted ? "BLOCKED_MISSING_HUMAN_GROUND_TRUTH" : !oracleRuns.length ? "BLOCKED_NO_LABELED_MATH_SCOPE" : "EXECUTED; no default changed or best variant selected" },
  };
}
