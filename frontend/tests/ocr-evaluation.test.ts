import test from "node:test";
import assert from "node:assert/strict";
import { applyAffine, assertNoSplitLeakage, convertVectorSource, generatePages, invertAffine, nativePage, trustedUnits, validateAnnotation, validateEvaluationPage, type RawVectorSource } from "../src/features/math-workspace/utils/ocr-evaluation-data";
import { matchMembership, measureScopes, measureTranscription } from "../src/features/math-workspace/utils/ocr-evaluation-metrics";
import { benchmarkPages } from "../src/features/math-workspace/utils/ocr-evaluation-benchmark";
const raw: RawVectorSource = { id: "software-vector-fixture", dataset: "SOFTWARE_TEST", checksum: "a".repeat(64), sourcePath: "software-test.inkml", license: "SOFTWARE_TEST_ONLY", label: "x=1", originalSplit: "train", inkCreationMethod: "human", annotations: { label: "x=1", normalizedLabel: "x=1" }, traces: [
  { id: "17", points: [{ x: -30, y: 100, t: 0 }, { x: 20, y: 140, t: 7 }] },
  { id: "2", points: [{ x: 40, y: 110, t: 12 }, { x: 70, y: 110, t: 13 }] },
  { id: "9", points: [{ x: 40, y: 130, t: 16 }, { x: 70, y: 130, t: 17 }] },
  { id: "dot", points: [{ x: 90, y: 105, t: 20 }] },
] };
test("vector conversion preserves chronological trace/point order, dots, label, checksum and invertible physical aspect", async () => {
  const input = JSON.stringify(raw), p = await convertVectorSource(raw, true), matrix = p.provenance.affine as Parameters<typeof invertAffine>[0];
  assert.equal(JSON.stringify(raw), input); assert.deepEqual(p.source.strokes.map(s => s.id), raw.traces.map(t => `${raw.id}:${t.id}`));
  raw.traces.forEach((t, i) => t.points.forEach((point, j) => { const back = applyAffine(p.source.strokes[i].points[j], invertAffine(matrix)); assert.ok(Math.abs(back.x - point.x) < 1e-9 && Math.abs(back.y - point.y) < 1e-9); }));
  assert.equal(p.annotation.units[0].transcript, raw.label); assert.equal(p.provenance.sourceChecksum, raw.checksum); assert.equal(p.source.strokes.at(-1)!.points.length, 1); await validateEvaluationPage(p);
});
test("seeded composition has deterministic membership/transforms and no source/split leakage", async () => {
  const p = await convertVectorSource(raw, true); const split = p.split; const before = JSON.stringify(p);
  const config = { seed: 123, count: 12, split, family: "CYCLE" as const, expressions: 3, gapPx: 24, rotationDegrees: 2, thickness: 1 };
  const a = await generatePages([p], config), b = await generatePages([p], config); assert.deepEqual(a, b); assert.equal(JSON.stringify(p), before);
  for (const page of a) { validateAnnotation(page, true); assert.equal(page.sourceKind, "SYNTHETIC_COMPOSED_REAL_INK"); assert.equal(new Set(page.source.strokes.map(s => s.id)).size, page.source.strokes.length); }
  assertNoSplitLeakage([...a, p]); assert.throws(() => assertNoSplitLeakage([p, { ...p, split: split === "DEV" ? "HOLDOUT" : "DEV" }]), /SPLIT_LEAKAGE/);
  await assert.rejects(generatePages([p], { ...config, writerSplit: true }), /MISSING_WRITER/);
});
test("model suggestions, altered ink and fabricated human flags cannot silently become oracle GT", async () => {
  const p = await convertVectorSource(raw, false); assert.equal(trustedUnits(p).length, 0);
  p.annotation.origin = "MACHINE_PROPOSAL"; p.annotation.units[0].confirmed = true; assert.throws(() => validateAnnotation(p), /MACHINE_PREDICTIONS/);
  const source = await convertVectorSource(raw, true), changed = structuredClone(source); changed.source.strokes[0].points[0].x += .01; await assert.rejects(validateEvaluationPage(changed), /CHECKSUM/);
  const human = structuredClone(source); human.annotation.origin = "HUMAN"; human.annotation.status = "DRAFT"; assert.throws(() => validateAnnotation(human), /HUMAN_UNIT_CONFIRMATION/);
});
test("annotation hierarchy rejects cycles, missing children, unowned ink and unrelated duplicates", async () => {
  const p = await convertVectorSource(raw, true); const original = p.annotation.units[0];
  p.annotation.units.push({ ...original, id: "duplicate" }); assert.throws(() => validateAnnotation(p), /DUPLICATE_UNRELATED/); p.annotation.units.pop();
  p.annotation.units.push({ ...original, id: "parent", kind: "STRUCTURE", transcript: null, relation: "SYSTEM", childIds: ["missing"] }); assert.throws(() => validateAnnotation(p), /PARENT_REFERENCE/);
  p.annotation.units[1].childIds = ["parent"]; assert.throws(() => validateAnnotation(p), /CYCLE/);
});
test("maximum-IoU assignment is independent of array index and exposes false split/merge", async () => {
  const base = await convertVectorSource(raw, true), p = await generatePages([base], { seed: 1, count: 1, split: base.split, family: "ROWS", expressions: 2, gapPx: 24, rotationDegrees: 0, thickness: 1 });
  const g = p[0].annotation.units, exact = measureScopes(p[0], [...g].reverse().map(u => ({ ...u, readingOrder: u.readingOrder })));
  assert.equal(exact.exactMembership, 1); assert.equal(exact.pairwiseF1, 1);
  const merge = measureScopes(p[0], [{ id: "merge", kind: "MATH", strokeIds: p[0].source.strokes.map(s => s.id), readingOrder: 0 }]); assert.equal(merge.falseMerge?.length, 1); assert.equal(merge.exactMembership, 0);
  const truth = [{ ...g[0], id: "g1", strokeIds: ["a", "b", "c"] }, { ...g[1], id: "g2", strokeIds: ["d", "e"] }];
  const matches = matchMembership([{ id: "p1", kind: "MATH", strokeIds: ["a", "b", "d", "e"], readingOrder: 0 }, { id: "p2", kind: "MATH", strokeIds: ["c"], readingOrder: 1 }], truth);
  assert.equal(matches.find(m => m.predictedId === "p1")?.truthId, "g2"); assert.equal(matches.find(m => m.predictedId === "p2")?.truthId, "g1");
});
test("recognition normalization is lexical, preserves braces and wrong mathematics", () => {
  assert.equal(measureTranscription("x ^ { 2 }", "x^{2}").tokenExact, true);
  assert.equal(measureTranscription("x^2", "x^{2}").tokenExact, false);
  assert.equal(measureTranscription("x=5", "x=2").tokenExact, false);
  assert.equal(measureTranscription("\\sinx", "\\sin x").tokenExact, false);
  const style = measureTranscription("\\int\\limits_{M}BF", "\\int_{M}BF"); assert.equal(style.tokenExact, false); assert.equal(style.presentationCommandsOnlyDifference, true);
});
test("scope-only benchmark never invokes recognition and does not mutate source/GT", async () => {
  const p = await convertVectorSource(raw, true), before = JSON.stringify(p);
  const result = await benchmarkPages([p], { profiles: ["GEOMETRY", "ORACLE"], maxCases: 1, inferenceLimit: 0, recognitionEnabled: false, codeSignature: "software-test" }, {
    detect: async () => { throw Error("not expected"); }, recognize: async () => { throw Error("must not call model"); }, fingerprint: async () => { throw Error("must not initialize model"); }, cacheGet: async () => undefined, cachePut: async () => {}, progress: () => {}, cancelled: () => false,
  });
  assert.equal(result.actualInferenceCalls, 0); assert.equal(JSON.stringify(p), before); assert.equal(result.arms.find(a => a.profile === "ORACLE")?.metrics.exactMembership, 1);
  const unlabelled = await nativePage(p.source.strokes, "native", "native"); assert.equal(trustedUnits(unlabelled).length, 0);
});
