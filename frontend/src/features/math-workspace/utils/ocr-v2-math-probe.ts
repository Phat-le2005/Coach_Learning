import { diagnoseMathScope, DIAGNOSTIC_CONFIG, sha256, type MathScopeDiagnostic } from "./ocr-model-diagnostics";
import { routeLabel, sourceKey, validateLabSource, type LabSource, type ScopeProposal } from "./ocr-v2-experimental";

/** Availability is not classification. This function never invokes a recognizer. */
export function mathProbeOffer(scope?: ScopeProposal) {
  if (!scope?.strokeIds.length) return { eligible: false, action: "MANUAL_REVIEW", reason: "NO_VALID_SCOPE" };
  if (scope.kind === "MATH") return { eligible: false, action: "RECOGNIZE_MATH", reason: "NORMAL_MATH_ROUTING" };
  if (scope.kind === "TEXT") return { eligible: false, action: "MANUAL_REVIEW", reason: "TEXT_RECOGNIZER_MISSING" };
  if (scope.kind === "MIXED") return { eligible: false, action: "MANUAL_REVIEW", reason: "MIXED_REQUIRES_SCOPE_REVIEW" };
  if (scope.kind !== "UNKNOWN") return { eligible: false, action: "MANUAL_REVIEW", reason: "INVALID_PROBE_KIND" };
  if (scope.flags.includes("MULTI_ROW_DELIMITER_UNRESOLVED")) return { eligible: false, action: "DEFER_UNRESOLVED_STRUCTURE", reason: "UNRESOLVED_STRUCTURE" };
  if (scope.flags.some(f => f.includes("GEOMETRY_AMBIGUOUS") || f.startsWith("BOUNDARY_CROSSING") || f.startsWith("OVERLAPPING_CANDIDATES") || f === "ORPHAN_SOURCE_INK")) {
    return { eligible: false, action: "MANUAL_REVIEW", reason: "REVIEW_AMBIGUOUS_SCOPE_FIRST" };
  }
  if (scope.flags.some(f => f.startsWith("TEXT_SIGNAL")) || scope.rawLabel.split(" | ").some(label => routeLabel(label) === "TEXT")) {
    return { eligible: false, action: "MANUAL_REVIEW", reason: "TEXT_EVIDENCE_REQUIRES_MANUAL_ROUTING" };
  }
  return { eligible: true, action: "OFFER_MATH_PROBE", reason: "USER_REQUEST_ONLY; UNKNOWN is not a math classification" };
}

export interface MathProbeEvidence {
  scopeId: string; sourceStrokeIds: string[]; sourceKey: string; sourceSnapshotHash: string;
  pageIndex: number; sourceRevision: number; originalKind: "UNKNOWN"; model: typeof DIAGNOSTIC_CONFIG.model;
  timestamp: string; trigger: "USER_REQUEST"; probeReason: string; reviewRequired: true;
  status: "COMPLETED" | "ABSTAINED" | "ERROR" | "STALE_SOURCE_CHANGED";
  rawOutput: string | null; normalizedOutput: string | null; inputCropHash: string | null;
  inputCropPreview: string | null; durationMs: number; inferenceCalls: number | null; invocationCount: number;
  error?: string; diagnostic?: MathScopeDiagnostic;
}

/** Lab-only side channel: no IR, approval or content mutation API is accepted. */
export async function runLabMathProbe(
  source: LabSource, scope: ScopeProposal, currentSourceKey: () => string,
  recognize: typeof diagnoseMathScope = diagnoseMathScope,
): Promise<MathProbeEvidence> {
  if (process.env.NODE_ENV === "production") throw Error("LAB_MATH_PROBE_DISABLED_IN_PRODUCTION");
  const offer = mathProbeOffer(scope);
  if (!offer.eligible) throw Error(offer.reason);
  const frozen = structuredClone(source), key = sourceKey(frozen), pen = validateLabSource(frozen);
  if (new Set(scope.strokeIds).size !== scope.strokeIds.length || scope.strokeIds.some(id => !pen.some(s => s.id === id))) throw Error("INVALID_PROBE_STROKE_MEMBERSHIP");
  const ink = pen.filter(s => scope.strokeIds.includes(s.id));
  const started = performance.now();
  const evidence: MathProbeEvidence = {
    scopeId: scope.id, sourceStrokeIds: ink.map(s => s.id), sourceKey: key,
    sourceSnapshotHash: await sha256(new TextEncoder().encode(key)), pageIndex: frozen.pageIndex, sourceRevision: frozen.sourceRevision,
    originalKind: "UNKNOWN", model: DIAGNOSTIC_CONFIG.model, timestamp: new Date().toISOString(), trigger: "USER_REQUEST",
    probeReason: [offer.reason, ...scope.flags].join("; "), reviewRequired: true, status: "STALE_SOURCE_CHANGED",
    rawOutput: null, normalizedOutput: null, inputCropHash: null, inputCropPreview: null,
    durationMs: 0, inferenceCalls: 0, invocationCount: 0,
  };
  if (currentSourceKey() !== key) return evidence;
  try {
    evidence.invocationCount = 1;
    const diagnostic = await recognize(ink);
    if (JSON.stringify(diagnostic.sourceStrokeIds) !== JSON.stringify(evidence.sourceStrokeIds)) throw Error("PROBE_SOURCE_IDENTITY_MISMATCH");
    evidence.diagnostic = diagnostic;
    if (diagnostic.status === "COMPLETED") {
      evidence.status = "COMPLETED"; evidence.inferenceCalls = 1;
      evidence.rawOutput = diagnostic.rawLatex; evidence.normalizedOutput = diagnostic.selectedLatex;
      evidence.inputCropHash = diagnostic.preprocessing.tensorSha256;
      evidence.inputCropPreview = diagnostic.preprocessing.previewPng;
    } else { evidence.status = "ABSTAINED"; evidence.inferenceCalls = 0; }
  } catch (error) {
    evidence.status = "ERROR"; evidence.error = String(error);
    // A transport/runtime error can happen after decoding started; do not invent zero.
    evidence.inferenceCalls = null;
  }
  evidence.durationMs = performance.now() - started;
  if (currentSourceKey() !== key) evidence.status = "STALE_SOURCE_CHANGED";
  return evidence;
}
