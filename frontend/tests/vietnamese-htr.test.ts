import test from "node:test";
import assert from "node:assert/strict";
import { assertHtrCandidate, htrMetrics, runSelectedHtrProbe, type HtrCandidate } from "../src/features/math-workspace/utils/vietnamese-htr";
const candidate = (id = "HTR-2", n = 4): HtrCandidate => ({ candidateId: id, pageId: "software-source", scopeId: "confirmed-subset",
  pageIndex: 0, sourceRevision: 2, sourceSnapshotSha256: "a".repeat(64), sourceStrokeIds: Array.from({ length: n }, (_, i) => `s${i}`),
  originalKind: "UNKNOWN", inputImageHash: "b".repeat(64), png: "data:image/png;base64,fixture", reference: { id: "ref-2", text: "N\u00ean", status: "HUMAN_CONFIRMED_ASSISTED" } });
test("HTR references preserve UTF-8/NFC and damaged diacritics cannot be scored silently", () => {
  const c = candidate(); assertHtrCandidate(c); assert.equal(JSON.parse(JSON.stringify(c)).reference.text, "Nên");
  assert.throws(() => assertHtrCandidate({ ...c, reference: { ...c.reference, text: "N?n" } }), /REFERENCE/);
  const m = htrMetrics("Ne\u0302n", c.reference.text); assert.equal(m.strict.exact, false); assert.equal(m.NFC.exact, true);
});
test("HTR only accepts selected6/4/19 references, never active33 or arbitrary TEXT scope", () => {
  assertHtrCandidate(candidate("HTR-3", 19));
  assert.throws(() => assertHtrCandidate(candidate("HTR-3", 33)), /EXACT_CONFIRMED/);
  assert.throws(() => assertHtrCandidate(candidate("polynomial-text", 11)), /EXACT_CONFIRMED/);
});
test("HTR sends candidate ID only, retains raw output, and cannot change caller review/correction", async () => {
  const c = candidate(), state = { kind: "UNKNOWN", reviewStatus: "APPROVED", correction: "student literal text" }, before = JSON.stringify({ c, state });
  let calls = 0;
  const request: typeof fetch = async (_url, init) => {
    calls++; assert.deepEqual(JSON.parse(init!.body as string), { candidateId: c.candidateId });
    assert.ok(!(init!.body as string).includes(c.reference.text));
    return Response.json({ ...c, reference: undefined, status: "COMPLETED", rawTranscript: "Ne\u0302n", reviewRequired: true });
  };
  const result = await runSelectedHtrProbe(c, undefined, request);
  assert.equal(calls, 1); assert.equal(result.rawTranscript, "Ne\u0302n"); assert.equal(result.normalizedTranscript, "Nên");
  assert.equal(JSON.stringify({ c, state }), before);
});
test("HTR evidence must match crop/source and metrics preserve accent errors", async () => {
  const c = candidate();
  const request: typeof fetch = async () => Response.json({ ...c, status: "COMPLETED", rawTranscript: "Nên", reviewRequired: true, inputImageHash: "c".repeat(64) });
  await assert.rejects(runSelectedHtrProbe(c, undefined, request), /SOURCE_MISMATCH/);
  const m = htrMetrics("Ta co", "Ta có"); assert.equal(m.strict.exact, false); assert.equal(m.strict.CER, 1/5); assert.equal(m.strict.WER, 1/2);
  assert.equal(m.strict.diacriticSubstitutions.length, 1);
});
