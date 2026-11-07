import test from "node:test";
import assert from "node:assert/strict";
import { createOcrEvalCapture } from "../src/features/math-workspace/utils/ocr-eval-capture.js";
import { segmentPageInk_v2 } from "../src/features/math-workspace/utils/page-ocr.js";
import { annotationTemplate, validateRecognitionAnnotation, selectScopeStrokes, buildAutomaticScopes, compareScopeSets, compareRecognition, evaluateCapture } from "../src/features/math-workspace/utils/ocr-scope-diagnostics.js";
import { observeRecognition, type ObservableEngine } from "../src/features/math-workspace/utils/ocr-model-diagnostics.js";
import type { InkStroke } from "../src/lib/api/contracts.js";

// Software-contract tests only. These strokes and injected diagnostics are NOT OCR evidence.
const strokes: InkStroke[] = [0.1, 0.3].map((y, i) => ({ id: `s${i}`, tool: "PEN", color: "#000000", width: 2,
  points: [{ x: 0.1, y, pressure: 0.5 }, { x: 0.2, y: y + 0.02, pressure: 0.5 }] }));
const capture = () => createOcrEvalCapture(0, strokes, segmentPageInk_v2(strokes));
const hash = "a".repeat(64);
const annotation = () => ({ ...annotationTemplate(hash, "test.json"), annotationStatus: "HUMAN_VERIFIED" as const,
  expectedGroups: [{ groupId: "whole", strokeIds: ["s0", "s1"], contentKind: "MATH" as const, latex: "x=1" }] });

test("scope construction conserves pen IDs and cannot mutate source or drawing order", () => {
  const input = capture(), before = JSON.stringify(input);
  for (const profile of ["LEGACY_REGIONS", "IR_ATOMIC"] as const) {
    const scopes = buildAutomaticScopes(input, profile);
    assert.deepEqual(new Set(scopes.flatMap((s) => s.strokeIds)), new Set(["s0", "s1"]));
    assert.equal(scopes.filter((s) => s.runnable).flatMap((s) => s.strokeIds).length, 2);
  }
  const selected = selectScopeStrokes(input, ["s1", "s0"]);
  assert.deepEqual(selected.map((s) => s.id), ["s0", "s1"]);
  selected[0].points[0].x = 0.9;
  assert.equal(JSON.stringify(input), before);
});

test("annotation binds the exact capture and rejects unknown, duplicate and overlapping independent ownership", () => {
  const a = annotation(); assert.doesNotThrow(() => validateRecognitionAnnotation(a, capture(), hash));
  const text = { ...a, expectedGroups: [{ ...a.expectedGroups[0], contentKind: "TEXT", latex: null, text: "Suy ra" }] };
  assert.equal(validateRecognitionAnnotation(text, capture(), hash).expectedGroups[0].text, "Suy ra");
  assert.throws(() => validateRecognitionAnnotation(a, capture(), "b".repeat(64)), /IDENTITY_MISMATCH/);
  assert.throws(() => selectScopeStrokes(capture(), ["s0", "s0"]), /DUPLICATE/);
  assert.throws(() => validateRecognitionAnnotation({ ...a, expectedGroups: [{ ...a.expectedGroups[0], strokeIds: ["absent"] }] }, capture(), hash), /UNKNOWN_SOURCE/);
  assert.throws(() => validateRecognitionAnnotation({ ...a, expectedGroups: [...a.expectedGroups, { ...a.expectedGroups[0], groupId: "duplicate-owner" }] }, capture(), hash), /OWNERSHIP/);
  assert.throws(() => validateRecognitionAnnotation({ ...a, expectedGroups: [{ ...a.expectedGroups[0], latex: "" }] }, capture(), hash), /LABEL_REQUIRED/);
});

test("annotation relations may reference ancestor ink but reject missing children and cycles", () => {
  const a = annotation();
  const parent = { ...a.expectedGroups[0], childGroupIds: ["leaf"] };
  const leaf = { groupId: "leaf", strokeIds: ["s0"], contentKind: "MATH", latex: "x" };
  assert.doesNotThrow(() => validateRecognitionAnnotation({ ...a, expectedGroups: [parent, leaf] }, capture(), hash));
  assert.throws(() => validateRecognitionAnnotation({ ...a, expectedGroups: [parent] }, capture(), hash), /RELATION/);
  assert.throws(() => validateRecognitionAnnotation({ ...a, expectedGroups: [{ ...parent, childGroupIds: ["whole"] }] }, capture(), hash), /CYCLIC/);
});

test("scope alignment uses stroke sets, never index; split fragments are excluded from recognition accuracy", async () => {
  const a = annotation(); let calls = 0;
  const result = await evaluateCapture({ capture: capture(), captureSha256: hash, annotation: a, profiles: ["LEGACY_REGIONS"],
    recognize: async () => { calls++; return { status: "ABSTAIN_NOT_MEANINGFUL", sourceStrokeIds: [], variant: "default",
      config: { model: "test" }, modelHashes: {}, confidence: "NOT_AVAILABLE" } as never; } });
  assert.equal(calls, 3); // two automatic fragments and one whole oracle; same injected interface
  const auto = result.comparisons.filter((c) => c.source === "AUTO");
  assert.ok(auto.every((c) => c.alignment === "SEGMENTATION_OR_ALIGNMENT_ERROR" && c.recognition === null));
  assert.ok(auto.every((c) => c.scopeMatches[0].match === "SPLIT_FRAGMENT"));
  assert.deepEqual(auto[0].scopeMatches[0].missingStrokeIds, ["s1"]);
  const match = compareScopeSets({ id: "x", strokeIds: ["s1", "s0"], source: "AUTO", profile: "LEGACY_REGIONS", kind: "MATH", runnable: true, skipReason: null }, a.expectedGroups);
  assert.equal(match[0].match, "EXACT");
});

test("default A/B uses same recognizer/preprocessing and excludes missing human labels and non-math", async () => {
  const seen: unknown[] = [];
  const input = capture(), before = JSON.stringify(input);
  const result = await evaluateCapture({ capture: input, captureSha256: hash, profiles: ["LEGACY_REGIONS"], e2: true,
    recognize: async (s, variant) => { seen.push({ ids: s.map((v) => v.id), variant }); return { status: "ABSTAIN_NOT_MEANINGFUL" } as never; } });
  assert.equal(result.status, "BLOCKED_MISSING_HUMAN_GROUND_TRUTH");
  assert.equal(result.summary.metricsAreAccuracyEvidence, false);
  assert.equal(result.summary.e2, "BLOCKED_MISSING_HUMAN_GROUND_TRUTH");
  assert.equal(seen.length, 2); assert.equal(result.sensitivity.length, 0);
  assert.equal(JSON.stringify(input), before);
  assert.ok(seen.every((s) => (s as { variant: string }).variant === "default"));
});

test("beam observer preserves object/results and restores original method on success and failure", async () => {
  const beams = [{ ids: [1, 2], logProb: -3 }];
  const engine: ObservableEngine = { beamDecode: async () => beams, recognize: async function () {
    assert.equal(await this.beamDecode(), beams);
    return { latex: "{ x }", tokenIds: [1, 2], encoderMs: 1, decoderMs: 2, totalMs: 3 };
  } };
  const original = engine.beamDecode;
  const result = await observeRecognition(engine, {}, {});
  assert.equal(engine.beamDecode, original); assert.deepEqual(result.beams, beams); assert.notEqual(result.beams, beams);
  engine.recognize = async () => { throw new Error("inference failure"); };
  await assert.rejects(observeRecognition(engine, {}, {}), /inference failure/);
  assert.equal(engine.beamDecode, original);
});

test("lexical comparison preserves command boundaries, case and mathematical mistakes", () => {
  assert.equal(compareRecognition("x = 2", "x=2").tokenExact, true);
  assert.equal(compareRecognition("X=2", "x=2").tokenExact, false);
  assert.equal(compareRecognition("\\sin x", "\\sinx").tokenExact, false);
  assert.ok(compareRecognition("x=2", "x=1").tokenEditDistance > 0);
  assert.deepEqual(compareRecognition("x", "x^2").structureMarkerDifferences, ["^"]);
});

test("A/B and E2 map shuffled labels by source and retain raw/postprocessed differences", async () => {
  const a = { ...annotation(), expectedGroups: [
    { groupId: "second", strokeIds: ["s1"], contentKind: "MATH", latex: "y" },
    { groupId: "first", strokeIds: ["s0"], contentKind: "MATH", latex: "x" },
  ] };
  const calls: { ids: string[]; variant: unknown }[] = [];
  const result = await evaluateCapture({ capture: capture(), captureSha256: hash, annotation: a, profiles: ["LEGACY_REGIONS"], e2: true,
    recognize: async (s, variant) => {
      calls.push({ ids: s.map((v) => v.id), variant });
      const value = s[0].id === "s0" ? "x" : "y";
      return { status: "COMPLETED", rawLatex: `${value} }`, postprocessedLatex: value, selectedLatex: value } as never;
    } });
  assert.equal(result.comparisons[0].groundTruthGroupId, "first");
  assert.equal(result.comparisons[1].groundTruthGroupId, "second");
  assert.ok(result.comparisons.every((c) => c.recognition?.selected.tokenExact && !c.recognition.raw.tokenExact));
  assert.equal(result.sensitivity.length, 4);
  assert.equal(calls.length, 8);
  for (const id of ["s0", "s1"]) assert.deepEqual(calls.filter((c) => c.ids[0] === id).map((c) => c.variant), ["default", "default", "width-075", "width-125"]);
});

test("IR automatic baseline records containers as skipped and sends only the current atomic scopes", () => {
  const brace: InkStroke = { ...strokes[0], id: "brace", points: [
    { x: 0.11, y: 0.10, pressure: 0.5 }, { x: 0.095, y: 0.14, pressure: 0.5 }, { x: 0.08, y: 0.19, pressure: 0.5 },
    { x: 0.095, y: 0.24, pressure: 0.5 }, { x: 0.11, y: 0.28, pressure: 0.5 },
  ] };
  const lines: InkStroke[] = [0.12, 0.22].map((y, i) => ({ ...strokes[0], id: `eq${i}`, points: [
    { x: 0.13, y, pressure: 0.5 }, { x: 0.18, y: y + 0.02, pressure: 0.5 },
  ] }));
  const source = [brace, ...lines];
  const scopes = buildAutomaticScopes(createOcrEvalCapture(0, source, segmentPageInk_v2(source)), "IR_ATOMIC");
  const container = scopes.find((s) => s.kind === "STRUCTURE");
  assert.ok(container); assert.equal(container.runnable, false);
  assert.equal(container.skipReason, "NOT_SENT_CONTAINER_IN_CURRENT_IR_REVIEW");
  assert.deepEqual(new Set(container.strokeIds), new Set(source.map((s) => s.id)));
  assert.deepEqual(new Set(scopes.filter((s) => s.runnable).flatMap((s) => s.strokeIds)), new Set(["eq0", "eq1"]));
});
