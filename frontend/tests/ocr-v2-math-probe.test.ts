import test from "node:test";
import assert from "node:assert/strict";
import { mathProbeOffer, runLabMathProbe } from "../src/features/math-workspace/utils/ocr-v2-math-probe";
import { sourceKey, type LabSource, type ScopeProposal } from "../src/features/math-workspace/utils/ocr-v2-experimental";
import type { MathScopeDiagnostic } from "../src/features/math-workspace/utils/ocr-model-diagnostics";

const source: LabSource = { pageIndex: 0, sourceRevision: 7, sourceKind: "SYNTHETIC_INK", datasetSplit: "DEV", consent: false,
  strokes: ["a", "b", "outside"].map((id, i) => ({ id, tool: "PEN", width: 2, color: "#000", points: [{ x: .1 + i * .1, y: .2, pressure: .5 }] })) };
const scope: ScopeProposal = { id: "unknown", kind: "UNKNOWN", strokeIds: ["b", "a"], candidateStrokeIds: ["a", "b"],
  regionIds: [], rawLabel: "ink_geometry", rawScore: null, coverage: {}, flags: ["NO_POSITIVE_MATH_EVIDENCE"], method: "software test" };
// Adapter stubs exercise identity/state only; this string is never accuracy evidence.
const diagnostic = { status: "COMPLETED", sourceStrokeIds: ["a", "b"], rawLatex: "unit-test raw", selectedLatex: "unit-test repaired",
  preprocessing: { tensorSha256: "test-tensor", previewPng: "data:image/png;base64,test" } } as unknown as MathScopeDiagnostic;

test("UNKNOWN offers a user action without classification or automatic inference", () => {
  const before = JSON.stringify(scope), offer = mathProbeOffer(scope);
  assert.equal(offer.action, "OFFER_MATH_PROBE"); assert.equal(offer.eligible, true);
  assert.equal(JSON.stringify(scope), before);
  assert.equal(mathProbeOffer({ ...scope, kind: "MATH" }).action, "RECOGNIZE_MATH");
});

test("TEXT, MIXED, structure, text evidence and ambiguous boundaries never reach a probe adapter", async () => {
  let calls = 0;
  const blocked = [{ ...scope, kind: "TEXT" as const }, { ...scope, kind: "MIXED" as const },
    { ...scope, flags: ["MULTI_ROW_DELIMITER_UNRESOLVED"] }, { ...scope, flags: ["BOUNDARY_CROSSING:a"] },
    { ...scope, rawLabel: "text" }];
  for (const item of blocked) {
    assert.equal(mathProbeOffer(item).eligible, false);
    await assert.rejects(runLabMathProbe(source, item, () => sourceKey(source), async () => { calls++; return diagnostic; }));
  }
  assert.equal(calls, 0);
  assert.equal(mathProbeOffer(blocked[0]).reason, "TEXT_RECOGNIZER_MISSING");
  assert.equal(mathProbeOffer(blocked[2]).action, "DEFER_UNRESOLVED_STRUCTURE");
});

test("probe freezes exactly selected ink and retains raw versus normalized evidence without mutating source", async () => {
  const before = JSON.stringify({ source, scope }); let ids: string[] = [];
  const evidence = await runLabMathProbe(source, scope, () => sourceKey(source), async ink => {
    ids = ink.map(s => s.id); ink[0].points[0].x = .9; return diagnostic;
  });
  assert.deepEqual(ids, ["a", "b"]); assert.deepEqual(evidence.sourceStrokeIds, ids);
  assert.equal(evidence.originalKind, "UNKNOWN"); assert.equal(evidence.reviewRequired, true);
  assert.equal(evidence.rawOutput, "unit-test raw"); assert.equal(evidence.normalizedOutput, "unit-test repaired");
  assert.equal(evidence.sourceRevision, 7); assert.equal(evidence.inferenceCalls, 1);
  assert.equal(evidence.inputCropHash, "test-tensor"); assert.equal(JSON.stringify({ source, scope }), before);
});

test("source revision changes retain historical evidence but mark results stale; already stale input makes zero calls", async () => {
  let key = sourceKey(source), calls = 0;
  const evidence = await runLabMathProbe(source, scope, () => key, async () => { calls++; key = "changed"; return diagnostic; });
  assert.equal(evidence.status, "STALE_SOURCE_CHANGED"); assert.equal(evidence.rawOutput, "unit-test raw");
  assert.equal(evidence.inferenceCalls, 1);
  const skipped = await runLabMathProbe(source, scope, () => key, async () => { calls++; return diagnostic; });
  assert.equal(skipped.status, "STALE_SOURCE_CHANGED"); assert.equal(skipped.inferenceCalls, 0); assert.equal(calls, 1);
});

test("runtime failure is explicit and never counted as a successful inference or kind change", async () => {
  const evidence = await runLabMathProbe(source, scope, () => sourceKey(source), async () => { throw Error("runtime unavailable"); });
  assert.equal(evidence.status, "ERROR"); assert.equal(evidence.rawOutput, null);
  assert.equal(evidence.inferenceCalls, null); assert.equal(evidence.invocationCount, 1);
  assert.match(evidence.error!, /runtime unavailable/); assert.equal(scope.kind, "UNKNOWN");
});
