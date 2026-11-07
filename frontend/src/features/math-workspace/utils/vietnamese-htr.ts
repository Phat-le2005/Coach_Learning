/** Research-only selected-crop HTR. No IR, routing, approval or persistence API. */
export interface HtrCandidate {
  candidateId: string; pageId: string; scopeId: string; pageIndex: number; sourceRevision: number;
  sourceSnapshotSha256: string; sourceStrokeIds: string[]; originalKind: string;
  inputImageHash: string; png: string;
  reference: { id: string; text: string; status: string };
}
export interface HtrEvidence {
  status: "COMPLETED"; candidateId: string; modelId: string; modelVersion: string; weightSha256: string;
  runtime: string; device: string; rawTranscript: string; normalizedTranscript: string;
  durationMs: number; modelLoadMs: number; inputImageHash: string; sourceStrokeIds: string[];
  sourceSnapshotSha256: string; sourceRevision: number; pageIndex: number; originalKind: string;
  reviewRequired: true; inferenceCalls: number; preprocessing: unknown;
}
export function assertHtrCandidate(c: HtrCandidate): void {
  const count: Record<string, number> = { "HTR-1": 6, "HTR-2": 4, "HTR-3": 19 };
  if (!Object.hasOwn(count, c.candidateId) || c.sourceStrokeIds.length !== count[c.candidateId]
    || new Set(c.sourceStrokeIds).size !== c.sourceStrokeIds.length || c.sourceStrokeIds.some(id => !id)) throw Error("ONLY_EXACT_CONFIRMED_HTR_SCOPES; HTR-3 is19, never33");
  if (![c.sourceSnapshotSha256, c.inputImageHash].every(h => /^[a-f0-9]{64}$/.test(h))) throw Error("HTR_SOURCE_HASH_REQUIRED");
  if (!c.reference.text || c.reference.text.includes("?") || c.reference.text !== c.reference.text.normalize("NFC")) throw Error("INVALID_UTF8_NFC_HTR_REFERENCE");
}
export async function runSelectedHtrProbe(c: HtrCandidate, signal?: AbortSignal, request: typeof fetch = fetch): Promise<HtrEvidence> {
  if (process.env.NODE_ENV === "production") throw Error("HTR_LAB_ONLY");
  assertHtrCandidate(c);
  // Only an allowlisted ID crosses the wire: never reference text, arbitrary PNG or filesystem URL.
  const response = await request("/api/ocr-v2-lab/htr", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidateId: c.candidateId }), signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(120000)]) : AbortSignal.timeout(120000) });
  const body = await response.json();
  if (!response.ok || body.status !== "COMPLETED") throw Error(body.error ?? `HTR_HTTP_${response.status}`);
  if (body.candidateId !== c.candidateId || body.inputImageHash !== c.inputImageHash || body.sourceSnapshotSha256 !== c.sourceSnapshotSha256
    || body.sourceRevision !== c.sourceRevision || body.pageIndex !== c.pageIndex || body.originalKind !== c.originalKind
    || JSON.stringify(body.sourceStrokeIds) !== JSON.stringify(c.sourceStrokeIds) || body.reviewRequired !== true || typeof body.rawTranscript !== "string") throw Error("HTR_EVIDENCE_SOURCE_MISMATCH");
  return { ...body, normalizedTranscript: body.rawTranscript.normalize("NFC") };
}

/** Deterministic Levenshtein alignment. NFC is a separate metric, never spell correction. */
function edits(reference: string[], prediction: string[]) {
  const d = Array.from({ length: reference.length + 1 }, () => Array(prediction.length + 1).fill(0) as number[]);
  for (let i = 0; i <= reference.length; i++) d[i][0] = i;
  for (let j = 0; j <= prediction.length; j++) d[0][j] = j;
  for (let i = 1; i <= reference.length; i++) for (let j = 1; j <= prediction.length; j++) d[i][j] = Math.min(d[i-1][j]+1, d[i][j-1]+1, d[i-1][j-1]+Number(reference[i-1] !== prediction[j-1]));
  let i = reference.length, j = prediction.length;
  const operations: { type: "SUBSTITUTION" | "DELETION" | "INSERTION"; reference: string; prediction: string }[] = [];
  while (i || j) {
    if (i && j && reference[i-1] === prediction[j-1] && d[i][j] === d[i-1][j-1]) { i--; j--; }
    else if (i && j && d[i][j] === d[i-1][j-1]+1) { operations.push({ type: "SUBSTITUTION", reference: reference[--i], prediction: prediction[--j] }); }
    else if (i && d[i][j] === d[i-1][j]+1) operations.push({ type: "DELETION", reference: reference[--i], prediction: "" });
    else operations.push({ type: "INSERTION", reference: "", prediction: prediction[--j] });
  }
  return { distance: d[reference.length][prediction.length], operations: operations.reverse() };
}
export function htrMetrics(raw: string, reference: string) {
  const measure = (p: string, r: string) => {
    const chars = edits(Array.from(r), Array.from(p)), words = edits(r.trim().split(/\s+/u).filter(Boolean), p.trim().split(/\s+/u).filter(Boolean));
    const base = (s: string) => s.normalize("NFD").replace(/\p{M}/gu, "");
    return { exact: p === r, characterErrors: chars.distance, referenceCharacters: Array.from(r).length,
      CER: Array.from(r).length ? chars.distance / Array.from(r).length : null,
      wordErrors: words.distance, referenceWords: r.trim().split(/\s+/u).filter(Boolean).length,
      WER: r.trim() ? words.distance / r.trim().split(/\s+/u).length : null,
      operations: chars.operations, diacriticSubstitutions: chars.operations.filter(o => o.type === "SUBSTITUTION" && o.reference !== o.prediction && base(o.reference) === base(o.prediction)) };
  };
  return { strict: measure(raw, reference), NFC: measure(raw.normalize("NFC"), reference.normalize("NFC")), method: "Case-sensitive Unicode codepoints including spaces; word tokens split whitespace; no accent stripping/CAS/spellcheck in scoring" };
}
