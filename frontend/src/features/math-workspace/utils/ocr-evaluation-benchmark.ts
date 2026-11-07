import { constructScopeCandidates } from "./ocr-v2-scope-candidates";
import { renderLabPage, renderTransform, mapLayoutToScopes, type PerceptionResult, type ScopeProposal } from "./ocr-v2-experimental";
import { hashValue, inkHash, trustedUnits, validateAnnotation, type EvaluationPage } from "./ocr-evaluation-data";
import { measureScopes, measureTranscription, type PredictedUnit } from "./ocr-evaluation-metrics";
import { computeBounds } from "./structured-transcription-ir";
import type { MathScopeDiagnostic, fingerprintMathScope } from "./ocr-model-diagnostics";
import type { InkStroke } from "@/lib/api/contracts";

export const EVALUATION_PROFILES = ["GEOMETRY", "LAYOUT", "HYBRID", "ORACLE", "HYBRID_NO_TYPE", "HYBRID_NO_RECONCILIATION"] as const;
export type EvaluationProfile = typeof EVALUATION_PROFILES[number];
export interface CachedRecognition { diagnostic: MathScopeDiagnostic; cacheKey: string; createdAt: string }
export interface EvaluatedScope extends PredictedUnit { status: string; reasons: string[]; diagnostic?: MathScopeDiagnostic; error?: string; cacheHit: boolean; cacheKey?: string; originalEvidenceStrokeIds?: string[]; actualInferenceCalls: number | null; elapsedMs: number }
export interface EvaluationArm {
  pageId: string; sourceChecksum: string; sourceKind: EvaluationPage["sourceKind"]; split: EvaluationPage["split"]; annotationStatus: string; annotationHash: string; profile: EvaluationProfile; softwareTestOnly: boolean;
  scopes: EvaluatedScope[]; metrics: ReturnType<typeof measureScopes>; recognition: { truthId: string; scopeId?: string; status: string; unsupportedReferenceTokens?: string[] | null; raw?: ReturnType<typeof measureTranscription>; selected?: ReturnType<typeof measureTranscription> }[];
  failures: { kind: string; scopeId?: string; truthId?: string; detail: string }[];
  perception?: PerceptionResult; construction?: ReturnType<typeof constructScopeCandidates>; regionRecallAtIoU05: number | null;
  timings: { detectorActionMs: number; geometryMs: number; reconciliationMs: number; recognitionActionMs: number; totalMs: number; detectorTimingReused: boolean }; codeSignature: string;
  recognitionRequested: boolean;
}
export interface BenchmarkConfig { profiles: EvaluationProfile[]; maxCases: number; inferenceLimit: number; recognitionEnabled: boolean; codeSignature: string; vocabulary?: string[]; vocabularySha256?: string }
export interface BenchmarkResult { schemaVersion: "ocr-evaluation-results/1"; startedAt: string; completedAt: string; cancelled: boolean; config: BenchmarkConfig; arms: EvaluationArm[]; actualInferenceCalls: number; uncertainInferenceErrors: number; cacheHits: number; heldoutReadOnly: boolean; normalization: string }
type Fingerprint = Awaited<ReturnType<typeof fingerprintMathScope>>;
export async function benchmarkPages(pages: EvaluationPage[], config: BenchmarkConfig, deps: {
  detect: (png: string) => Promise<PerceptionResult>;
  recognize: (ink: InkStroke[]) => Promise<MathScopeDiagnostic>;
  fingerprint: (ink: InkStroke[]) => Promise<Fingerprint>;
  cacheGet: (key: string) => Promise<CachedRecognition | undefined>; cachePut: (key: string, value: CachedRecognition) => Promise<void>;
  progress: (message: string) => void; cancelled: () => boolean;
}): Promise<BenchmarkResult> {
  if (config.maxCases < 1 || config.maxCases > 300 || config.inferenceLimit < 0 || config.inferenceLimit > 500 || config.profiles.some(p => !EVALUATION_PROFILES.includes(p))) throw Error("INVALID_BENCHMARK_LIMITS");
  const result: BenchmarkResult = { schemaVersion: "ocr-evaluation-results/1", startedAt: new Date().toISOString(), completedAt: "", cancelled: false, config, arms: [], actualInferenceCalls: 0, uncertainInferenceErrors: 0, cacheHits: 0, heldoutReadOnly: pages.some(p => p.split === "HOLDOUT"), normalization: "Conservative lexical tokens, NFC, braces/commands retained. No CAS. Raw and repaired recognition evaluated separately. Only exact scope alignment receives recognition-only metrics; mismatches count as pipeline failures." };
  const snapshot = JSON.stringify(pages); let attempts = 0;
  for (const page of pages.slice(0, config.maxCases)) {
    if (deps.cancelled()) break;
    if (await inkHash(page.source) !== page.sourceChecksum) throw Error("BENCHMARK_SOURCE_MUTATED"); validateAnnotation(page);
    const gt = trustedUnits(page), transform = renderTransform();
    let perception: PerceptionResult = { status: "NOT_REQUESTED", model: "NONE", regions: [] }, detectorMs = 0;
    if (config.profiles.some(p => ["LAYOUT", "HYBRID", "HYBRID_NO_TYPE", "HYBRID_NO_RECONCILIATION"].includes(p))) {
      const start = performance.now(); deps.progress(`${page.title}: detector local…`);
      try { perception = await deps.detect(renderLabPage(page.source, transform).png); }
      catch (error) { perception = { status: "ERROR", model: "LAYOUT_M", regions: [], error: String(error) }; }
      detectorMs = performance.now() - start;
    }
    const annotationHash = await hashValue(page.annotation);
    for (const profile of config.profiles) {
      if (deps.cancelled()) break; deps.progress(`${page.title}: ${profile} · inference ${result.actualInferenceCalls}/${config.inferenceLimit}`);
      const armStart = performance.now(), geometryStart = performance.now(); let construction: EvaluationArm["construction"], proposed: ScopeProposal[];
      if (profile === "ORACLE") proposed = gt.map(u => ({ id: u.id, kind: u.kind === "STRUCTURE" ? "UNKNOWN" : u.kind, strokeIds: [...u.strokeIds], flags: ["CONFIRMED_GT_MEMBERSHIP_ONLY; label never fed to recognizer"], method: "ORACLE", regionIds: [], rawLabel: "ORACLE", rawScore: null, candidateStrokeIds: [...u.strokeIds], coverage: {} }));
      else if (profile === "LAYOUT") proposed = mapLayoutToScopes(page.source, perception, transform);
      else {
        const input = profile === "GEOMETRY" ? { status: "GEOMETRY_ONLY", model: "NONE", regions: [] } : profile === "HYBRID_NO_TYPE" ? { ...perception, regions: perception.regions.map(r => ({ ...r, label: "ABLATION_TYPE_REMOVED" })) } : perception;
        construction = constructScopeCandidates(page.source, input, transform, profile === "GEOMETRY" ? "GEOMETRY" : "HYBRID");
        proposed = construction.scopes;
        if (profile === "HYBRID_NO_RECONCILIATION") proposed = mapLayoutToScopes(page.source, perception, transform).map(s => {
          const exact = construction!.scopes.find(g => g.strokeIds.length === s.strokeIds.length && g.strokeIds.every(id => s.strokeIds.includes(id)));
          return { ...s, kind: exact?.kind ?? s.kind, flags: [...s.flags, "ABLATION_RAW_BOX_OWNERSHIP; only exact geometry type support retained"] };
        });
      }
      const geometryMs = performance.now() - geometryStart;
      const arm: EvaluationArm = { pageId: page.id, sourceChecksum: page.sourceChecksum, sourceKind: page.sourceKind, split: page.split, annotationStatus: page.annotation.status, annotationHash, profile, softwareTestOnly: !!page.softwareTestOnly,
        scopes: [], metrics: measureScopes(page, proposed.filter(s => s.strokeIds.length).map((s, i) => ({ id: s.id, kind: s.kind === "MIXED" ? "UNKNOWN" : s.kind, strokeIds: s.strokeIds, readingOrder: i }))), recognition: [], failures: [], construction,
        perception: profile === "GEOMETRY" || profile === "ORACLE" ? undefined : perception, regionRecallAtIoU05: null,
        timings: { detectorActionMs: profile === "GEOMETRY" || profile === "ORACLE" ? 0 : detectorMs, geometryMs, reconciliationMs: construction?.durationMs ?? 0, recognitionActionMs: 0, totalMs: 0, detectorTimingReused: true }, codeSignature: config.codeSignature, recognitionRequested: config.recognitionEnabled };
      if (arm.perception && gt.length) {
        let hit = 0, eligibleBoxes = 0;
        for (const unit of gt) { const b = computeBounds(page.source.strokes.filter(s => unit.strokeIds.includes(s.id))), area = Math.max(1e-12, (b.right - b.left) * (b.bottom - b.top));
          if (area <= 1e-11) continue; eligibleBoxes++;
          if (perception.regions.some(r => { const [l, t, right, bottom] = r.box.map((v, i) => (v - 16) / (i % 2 ? 1123 : 794)); const inter = Math.max(0, Math.min(right, b.right) - Math.max(l, b.left)) * Math.max(0, Math.min(bottom, b.bottom) - Math.max(t, b.top)); return inter / Math.max(1e-12, area + (right - l) * (bottom - t) - inter) >= .5; })) hit++;
        } arm.regionRecallAtIoU05 = eligibleBoxes ? hit / eligibleBoxes : null;
      }
      for (const [order, scope] of proposed.filter(s => s.strokeIds.length).entries()) {
        const entry: EvaluatedScope = { id: scope.id, kind: scope.kind === "MIXED" ? "UNKNOWN" : scope.kind, strokeIds: [...scope.strokeIds], readingOrder: order, status: "UNRESOLVED_KIND", reasons: [...scope.flags], cacheHit: false, actualInferenceCalls: 0, elapsedMs: 0 };
        arm.scopes.push(entry);
        if (deps.cancelled()) { entry.status = "CANCELLED"; continue; }
        if (scope.kind !== "MATH") { entry.status = scope.kind === "TEXT" ? "UNSUPPORTED_VIETNAMESE_HTR" : "UNRESOLVED_KIND"; continue; }
        if ((profile === "LAYOUT" || profile === "HYBRID_NO_RECONCILIATION") && scope.flags.some(f => /^(BOUNDARY_CROSSING|OVERLAPPING_CANDIDATES)/.test(f))) { entry.status = "BLOCKED_AMBIGUOUS_MAPPING"; continue; }
        if (!config.recognitionEnabled) { entry.status = "RECOGNITION_NOT_REQUESTED"; continue; }
        const ink = page.source.strokes.filter(s => s.tool === "PEN" && scope.strokeIds.includes(s.id)); const t = performance.now();
        try {
          const fingerprint = await deps.fingerprint(ink);
          if (fingerprint.status !== "READY") { entry.status = fingerprint.status; continue; }
          const key = await hashValue({ fingerprint, code: config.codeSignature }); let cached: CachedRecognition | undefined;
          try { cached = await deps.cacheGet(key); } catch { entry.reasons.push("CACHE_UNAVAILABLE; inference still allowed within budget"); }
          entry.cacheKey = key;
          if (cached) { entry.cacheHit = true; entry.diagnostic = cached.diagnostic; entry.originalEvidenceStrokeIds = cached.diagnostic.sourceStrokeIds; result.cacheHits++; }
          else {
            if (attempts >= config.inferenceLimit) { entry.status = "INFERENCE_BUDGET_EXHAUSTED"; continue; }
            attempts++; entry.actualInferenceCalls = null;
            entry.diagnostic = await deps.recognize(ink);
            if (entry.diagnostic.status === "COMPLETED") {
              entry.actualInferenceCalls = 1; result.actualInferenceCalls++;
              if (entry.diagnostic.preprocessing.tensorSha256 !== fingerprint.tensorSha256 || entry.diagnostic.preprocessing.maskSha256 !== fingerprint.maskSha256) throw Error("PREPROCESSING_CHANGED_BETWEEN_CACHE_KEY_AND_INFERENCE");
              try { await deps.cachePut(key, { cacheKey: key, createdAt: new Date().toISOString(), diagnostic: entry.diagnostic }); }
              catch { entry.reasons.push("CACHE_WRITE_FAILED; completed model evidence retained"); }
            } else entry.actualInferenceCalls = 0;
          }
          entry.status = entry.diagnostic.status;
        } catch (error) { entry.status = "MODEL_OR_RUNTIME_ERROR"; entry.error = String(error); if (entry.actualInferenceCalls === null) result.uncertainInferenceErrors++; arm.failures.push({ kind: entry.error.includes("PREPROCESSING_CHANGED") ? "RENDERING_PREPROCESSING_FINGERPRINT_CHANGED" : "RUNTIME_UNAVAILABLE_OR_INFERENCE_ERROR", scopeId: scope.id, detail: entry.error }); }
        finally { entry.elapsedMs = performance.now() - t; arm.timings.recognitionActionMs += entry.elapsedMs; }
      }
      if (profile === "ORACLE" && !gt.length) arm.failures.push({ kind: "BLOCKED_MISSING_CONFIRMED_GT", detail: "No dataset/generator/human-confirmed independent scope; automatic candidates are not an oracle" });
      for (const unit of gt.filter(u => u.kind === "MATH")) {
        const match = arm.metrics.matches.find(m => m.truthId === unit.id), prediction = arm.scopes.find(s => s.id === match?.predictedId);
        const unsupported = config.vocabulary && unit.transcript ? [...new Set((unit.transcript.match(/\\[a-zA-Z]+|\\.|[a-zA-Z]|[0-9]|[^\s]/g) ?? []).filter(t => !config.vocabulary!.includes(t)))] : null;
        if (unsupported?.length) arm.failures.push({ kind: "REFERENCE_TOKENS_OUTSIDE_MODEL_VOCABULARY", truthId: unit.id, detail: `Strict lexical reference contains unsupported tokens: ${unsupported.join(", ")}. Reference and exact-match denominator are NOT changed.` });
        if (!unit.transcript) { arm.recognition.push({ truthId: unit.id, status: "RECOGNITION_ACCURACY_NOT_MEASURED" }); continue; }
        if (!match || match.missing.length || match.extra.length) { arm.recognition.push({ truthId: unit.id, scopeId: prediction?.id, status: "SCOPE_MISMATCH; recognition-only score excluded" }); continue; }
        if (prediction?.diagnostic?.status === "COMPLETED") {
          if (config.vocabularySha256 && prediction.diagnostic.modelHashes.vocab !== config.vocabularySha256) throw Error("REFERENCE_VOCABULARY_CHECKSUM_DIFFERS_FROM_ACTUAL_MODEL");
          arm.recognition.push({ truthId: unit.id, scopeId: prediction.id, status: "MEASURED_EXACT_SCOPE", unsupportedReferenceTokens: unsupported, raw: measureTranscription(prediction.diagnostic.rawLatex, unit.transcript), selected: measureTranscription(prediction.diagnostic.selectedLatex, unit.transcript) });
        }
        else arm.recognition.push({ truthId: unit.id, scopeId: prediction?.id, status: prediction?.status ?? "NO_MATCHED_RECOGNITION" });
      }
      arm.metrics.falseSplit?.forEach(id => arm.failures.push({ kind: "FALSE_SPLIT", truthId: id, detail: "GT unit intersects multiple active predictions" }));
      arm.metrics.falseMerge?.forEach(id => arm.failures.push({ kind: "FALSE_MERGE", scopeId: id, detail: "Prediction intersects multiple confirmed atomic GT units" }));
      arm.metrics.matches.forEach(m => { const g = gt.find(u => u.id === m.truthId)!, p = arm.scopes.find(s => s.id === m.predictedId)!;
        if (g.kind !== p.kind) arm.failures.push({ kind: "CONTENT_TYPE_OR_ROUTING_ERROR", scopeId: p.id, truthId: g.id, detail: `${g.kind} → ${p.kind}; membership IoU=${m.iou}` });
        if (m.missing.length || m.extra.length) arm.failures.push({ kind: "STROKE_MAPPING_OR_SCOPE_ERROR", scopeId: p.id, truthId: g.id, detail: `missing=${m.missing.length}; extra=${m.extra.length}` });
      });
      if (arm.perception && perception.status !== "DETECTED") arm.failures.push({ kind: "DETECTOR_FAILURE_OR_NO_DETECTIONS", detail: perception.error ?? perception.status });
      if (construction?.readingOrder === "AMBIGUOUS") arm.failures.push({ kind: "READING_ORDER_AMBIGUOUS", detail: "Display order is a proposal; numeric order metric compares the current proposal, not human-confirmed certainty" });
      if (arm.perception && arm.regionRecallAtIoU05 !== null && arm.regionRecallAtIoU05 < 1) arm.failures.push({ kind: "DETECTION_REGION_MISS_AT_IOU_05", detail: "GT box is source-stroke bounds; not manually drawn region GT" });
      arm.recognition.filter(r => r.raw && !r.raw.tokenExact).forEach(r => arm.failures.push({ kind: r.raw!.presentationCommandsOnlyDifference ? "LEXICAL_PRESENTATION_COMMAND_DIFFERENCE" : profile === "ORACLE" ? "RECOGNITION_ERROR_WITH_ORACLE_SCOPE" : "RECOGNITION_ERROR_ON_EXACT_SCOPE", truthId: r.truthId, scopeId: r.scopeId, detail: r.raw!.presentationCommandsOnlyDifference ? "Strict exact match still fails; visible symbol sequence differs only by declared presentation commands such as limits. Not evidence of misread content symbols." : "Scope exact; model output differs lexically from confirmed source transcript. Rendering vs decoding cause not separable without further experiment." }));
      arm.recognition.filter(r => r.raw && r.selected && r.raw.tokenExact !== r.selected.tokenExact).forEach(r => arm.failures.push({ kind: "POSTPROCESSING_CHANGED_MATCH_STATUS", truthId: r.truthId, scopeId: r.scopeId, detail: "Raw and selected exact-match outcomes differ; both retained without reranking" }));
      arm.timings.totalMs = performance.now() - armStart + arm.timings.detectorActionMs;
      result.arms.push(arm);
    }
  }
  for (const arm of result.arms.filter(a => a.profile !== "ORACLE")) {
    const oracle = result.arms.find(a => a.pageId === arm.pageId && a.profile === "ORACLE");
    oracle?.recognition.filter(r => r.raw && !r.raw.tokenExact && !r.raw.presentationCommandsOnlyDifference).forEach(r => arm.failures.push({ kind: "ORACLE_RECOGNITION_ALSO_FAILS", truthId: r.truthId, detail: "Do not attribute all transcription error to segmentation; oracle membership also fails. Rendering/preprocessing versus model decoding remains UNKNOWN." }));
  }
  if (snapshot !== JSON.stringify(pages)) throw Error("BENCHMARK_MUTATED_SOURCE_OR_ANNOTATION"); result.cancelled = deps.cancelled(); result.completedAt = new Date().toISOString(); return result;
}
export function summarizeBenchmark(arms: EvaluationArm[]) {
  const groups: Record<string, EvaluationArm[]> = {};
  arms.forEach(a => { const key = `${a.softwareTestOnly ? "SOFTWARE_TEST" : a.sourceKind}/${a.split}/${a.annotationStatus}/${a.profile}`; (groups[key] ??= []).push(a); });
  return Object.entries(groups).map(([cohort, rows]) => {
    const valid = rows.filter(a => a.metrics.status === "MEASURED"), mean = (fn: (a: EvaluationArm) => number | null) => { const values = valid.map(fn).filter((v): v is number => v !== null); return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null; };
    const rec = rows.flatMap(a => a.recognition).filter(r => r.raw), selected = rec.filter(r => r.selected);
    const pipelineRows = rows.filter(a => a.recognitionRequested && !a.scopes.some(s => s.status === "INFERENCE_BUDGET_EXHAUSTED" || s.status === "CANCELLED")), references = pipelineRows.flatMap(a => a.recognition).filter(r => r.status !== "RECOGNITION_ACCURACY_NOT_MEASURED");
    return { cohort, cases: rows.length, fullyLabeledCases: valid.length, scopePrecision: mean(a => a.metrics.strokePrecision), scopeRecall: mean(a => a.metrics.strokeRecall), meanIoU: mean(a => a.metrics.meanIoU), exactMembership: mean(a => a.metrics.exactMembership), pairwiseF1: mean(a => a.metrics.pairwiseF1), readingOrderAccuracy: mean(a => a.metrics.readingOrderPairAccuracy), measuredExpressions: rec.length,
      rawExpressionExact: rec.length ? rec.filter(r => r.raw!.tokenExact).length / rec.length : null, repairedExpressionExact: selected.length ? selected.filter(r => r.selected!.tokenExact).length / selected.length : null,
      pipelineExpressionExact: references.length ? references.filter(r => r.raw?.tokenExact).length / references.length : null, pipelineReferenceExpressions: references.length,
      canonicalTokenCER: rec.reduce((n, r) => n + r.raw!.referenceCharacters, 0) ? rec.reduce((n, r) => n + r.raw!.characterEditDistance, 0) / rec.reduce((n, r) => n + r.raw!.referenceCharacters, 0) : null,
      falseSplits: valid.length ? valid.reduce((n, a) => n + (a.metrics.falseSplit?.length ?? 0), 0) : null, falseMerges: valid.length ? valid.reduce((n, a) => n + (a.metrics.falseMerge?.length ?? 0), 0) : null,
      inferenceCalls: rows.flatMap(a => a.scopes).reduce((n, s) => n + (s.actualInferenceCalls ?? 0), 0), cacheHits: rows.flatMap(a => a.scopes).filter(s => s.cacheHit).length };
  });
}
