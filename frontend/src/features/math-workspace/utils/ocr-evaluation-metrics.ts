import { compareRecognition } from "./ocr-scope-diagnostics";
import { trustedUnits, type EvaluationPage, type GtUnit, type Kind } from "./ocr-evaluation-data";
export interface PredictedUnit { id: string; kind: Kind; strokeIds: string[]; readingOrder: number }
export const intersection = (a: string[], b: string[]) => a.filter(id => b.includes(id));
const choose2 = (n: number) => n * (n - 1) / 2;
/** Deterministic maximum-total-IoU one-to-one assignment (Hungarian), not array index. */
export function matchMembership(predicted: PredictedUnit[], truth: GtUnit[]) {
  const size = Math.max(predicted.length, truth.length); if (!size) return [];
  const weights = Array.from({ length: size }, (_, i) => Array.from({ length: size }, (_, j) => {
    if (!predicted[i] || !truth[j]) return 0;
    const n = intersection(predicted[i].strokeIds, truth[j].strokeIds).length;
    return n / Math.max(1, new Set([...predicted[i].strokeIds, ...truth[j].strokeIds]).size);
  }));
  const u = Array(size + 1).fill(0), v = Array(size + 1).fill(0), p = Array(size + 1).fill(0), way = Array(size + 1).fill(0);
  for (let i = 1; i <= size; i++) {
    p[0] = i; let j0 = 0; const min = Array(size + 1).fill(Infinity), used = Array(size + 1).fill(false);
    do { used[j0] = true; const i0 = p[j0]; let delta = Infinity, j1 = 0;
      for (let j = 1; j <= size; j++) if (!used[j]) { const cost = 1 - weights[i0 - 1][j - 1] - u[i0] - v[j]; if (cost < min[j]) { min[j] = cost; way[j] = j0; } if (min[j] < delta) { delta = min[j]; j1 = j; } }
      for (let j = 0; j <= size; j++) if (used[j]) { u[p[j]] += delta; v[j] -= delta; } else min[j] -= delta;
      j0 = j1;
    } while (p[j0] !== 0);
    do { const j1 = way[j0]; p[j0] = p[j1]; j0 = j1; } while (j0);
  }
  return p.slice(1).flatMap((i, j) => i && predicted[i - 1] && truth[j] && weights[i - 1][j] > 0 ? [{ predictedId: predicted[i - 1].id, truthId: truth[j].id, iou: weights[i - 1][j],
    common: intersection(predicted[i - 1].strokeIds, truth[j].strokeIds), missing: truth[j].strokeIds.filter(id => !predicted[i - 1].strokeIds.includes(id)), extra: predicted[i - 1].strokeIds.filter(id => !truth[j].strokeIds.includes(id)) }] : []);
}
export function measureScopes(page: EvaluationPage, predicted: PredictedUnit[]) {
  const truth = trustedUnits(page), counts = new Map<string, number>(), pen = page.source.strokes.filter(s => s.tool === "PEN");
  predicted.forEach(p => p.strokeIds.forEach(id => counts.set(id, (counts.get(id) ?? 0) + 1)));
  const sourceIds = new Set(pen.map(s => s.id));
  const atomicIds = new Set(truth.flatMap(u => u.strokeIds));
  const framingIds = new Set(page.annotation.units.filter(u => u.kind === "STRUCTURE" && u.confirmed).flatMap(u => u.strokeIds).filter(id => !atomicIds.has(id)));
  const integrity = { orphanIds: pen.filter(s => !counts.has(s.id) && !framingIds.has(s.id)).map(s => s.id), structuralFrameIds: [...framingIds], duplicateIds: [...counts].filter(([, count]) => count > 1).map(([id]) => id), unknownIds: [...counts.keys()].filter(id => !sourceIds.has(id)) };
  if (!truth.length) return { status: "NOT_MEASURED_MISSING_CONFIRMED_GT" as const, integrity, matches: [], falseSplit: null, falseMerge: null, strokePrecision: null, strokeRecall: null, meanIoU: null, exactMembership: null, pairwiseF1: null, readingOrderPairAccuracy: null, typeConfusion: {} };
  const contentPredictions = predicted.filter(p => !p.strokeIds.every(id => framingIds.has(id)));
  const matches = matchMembership(contentPredictions, truth), common = matches.reduce((n, m) => n + m.common.length, 0);
  const totalPred = contentPredictions.reduce((n, p) => n + p.strokeIds.length, 0), totalGT = truth.reduce((n, u) => n + u.strokeIds.length, 0);
  const falseSplit = truth.filter(g => predicted.filter(p => intersection(p.strokeIds, g.strokeIds).length).length > 1).map(g => g.id);
  const falseMerge = predicted.filter(p => truth.filter(g => intersection(p.strokeIds, g.strokeIds).length).length > 1).map(p => p.id);
  const universe = new Set(truth.flatMap(u => u.strokeIds));
  const tp = predicted.reduce((n, p) => n + truth.reduce((m, g) => m + choose2(intersection(p.strokeIds, g.strokeIds).length), 0), 0);
  const pp = predicted.reduce((n, p) => n + choose2(p.strokeIds.filter(id => universe.has(id)).length), 0), gp = truth.reduce((n, g) => n + choose2(g.strokeIds.length), 0);
  const typeConfusion: Record<string, number> = {};
  matches.forEach(m => { const key = `${truth.find(g => g.id === m.truthId)!.kind} → ${predicted.find(p => p.id === m.predictedId)!.kind}`; typeConfusion[key] = (typeConfusion[key] ?? 0) + 1; });
  let ordered = 0, totalPairs = 0;
  const exact = matches.filter(m => !m.missing.length && !m.extra.length);
  for (let i = 0; i < exact.length; i++) for (let j = i + 1; j < exact.length; j++) {
    const a = exact[i], b = exact[j], gtA = truth.find(g => g.id === a.truthId)!, gtB = truth.find(g => g.id === b.truthId)!;
    // Only compare siblings: nested structure children and root-level order are different relations.
    const parent = (id: string) => page.annotation.units.find(u => u.childIds.includes(id))?.id ?? null;
    if (parent(gtA.id) !== parent(gtB.id)) continue;
    const pa = predicted.find(p => p.id === a.predictedId)!, pb = predicted.find(p => p.id === b.predictedId)!;
    totalPairs++; if (Math.sign(gtA.readingOrder - gtB.readingOrder) === Math.sign(pa.readingOrder - pb.readingOrder)) ordered++;
  }
  return { status: page.softwareTestOnly ? "SOFTWARE_WORKFLOW_ONLY" : page.annotation.status === "DRAFT" ? "PARTIAL_CONFIRMED_UNIT_GT" : "MEASURED" as const, integrity, matches, falseSplit, falseMerge,
    strokePrecision: totalPred ? common / totalPred : 0, strokeRecall: totalGT ? common / totalGT : null, meanIoU: truth.length ? matches.reduce((n, m) => n + m.iou, 0) / truth.length : null,
    exactMembership: truth.length ? exact.length / truth.length : null,
    pairwiseF1: integrity.duplicateIds.length ? null : pp + gp ? 2 * tp / (pp + gp) : 1,
    readingOrderPairAccuracy: totalPairs ? ordered / totalPairs : null, typeConfusion, gtStrokeCoverage: universe.size / Math.max(1, pen.length), denominator: "Confirmed atomic GT only; parent framing strokes excluded from grouping pairs; unmatched units remain in recall denominator" };
}
export function editDistance(a: string[], b: string[]) { let last = Array.from({ length: b.length + 1 }, (_, i) => i); for (let i = 0; i < a.length; i++) { const next = [i + 1]; for (let j = 0; j < b.length; j++) next.push(Math.min(next[j] + 1, last[j + 1] + 1, last[j] + Number(a[i] !== b[j]))); last = next; } return last[b.length]; }
export function measureTranscription(prediction: string, reference: string) {
  const lexical = compareRecognition(prediction, reference), tokenize = (s: string) => s.normalize("NFC").match(/\\[a-zA-Z]+|\\.|[a-zA-Z]|[0-9]|[^\s]/g) ?? [];
  const chars = (s: string) => [...tokenize(s).join(" ")], ref = chars(reference), d = editDistance(chars(prediction), ref);
  const formatting = new Set(["\\limits", "\\nolimits", "\\displaystyle", "\\textstyle"]);
  const contentTokens = (s: string) => tokenize(s).filter(t => !formatting.has(t));
  return { ...lexical, characterEditDistance: d, referenceCharacters: ref.length, canonicalTokenTextCER: ref.length ? d / ref.length : null,
    presentationCommandsOnlyDifference: !lexical.tokenExact && JSON.stringify(contentTokens(prediction)) === JSON.stringify(contentTokens(reference)),
    presentationDifferenceNote: "Diagnostic classification only; strict tokenExact/CER remain unchanged. No command stripping is used to improve the reported exact-match metric.",
    normalization: "NFC + conservative lexical tokens; whitespace canonicalized between tokens; braces/commands retained; no CAS or mathematical equivalence" };
}
