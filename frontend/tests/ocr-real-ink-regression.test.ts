import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import type { InkStroke } from "../src/lib/api/contracts.js";
import { validateOcrEvalCapture, reconstructSegmentationInput } from "../src/features/math-workspace/utils/ocr-eval-replay.js";
import { segmentPageInk_v2 } from "../src/features/math-workspace/utils/page-ocr.js";
import { detectStructuralCandidates } from "../src/features/math-workspace/utils/structural-candidate-engine.js";
import { buildOcrShadowQaReport } from "../src/features/math-workspace/utils/ocr-shadow-qa.js";

// Helper to construct synthetic strokes
function makeStroke(id: string, points: Array<{ x: number; y: number; pressure?: number }>, tool: InkStroke["tool"] = "PEN"): InkStroke {
  return {
    id,
    tool,
    color: "#000000",
    width: 2,
    points: points.map((p) => ({ ...p, pressure: p.pressure ?? 0.5 })),
  };
}

function makeLine(id: string, x: number, y: number, w = 0.2, h = 0.02): InkStroke {
  return makeStroke(id, [
    { x, y },
    { x: x + w * 0.5, y: y + h * 0.5 },
    { x: x + w, y: y + h },
  ]);
}

function makeCurlyBrace(id: string, x = 0.08, yTop = 0.1, yBottom = 0.3): InkStroke {
  const yMid = (yTop + yBottom) / 2;
  return makeStroke(id, [
    { x: x + 0.03, y: yTop },
    { x: x + 0.015, y: yTop + 0.04 },
    { x, y: yMid },
    { x: x + 0.015, y: yBottom - 0.04 },
    { x: x + 0.03, y: yBottom },
  ]);
}

function makeSquareBracket(id: string, x = 0.08, yTop = 0.1, yBottom = 0.3): InkStroke {
  const yMid = (yTop + yBottom) / 2;
  return makeStroke(id, [
    { x: x + 0.03, y: yTop },
    { x, y: yTop },
    { x, y: yMid },
    { x, y: yBottom },
    { x: x + 0.03, y: yBottom },
  ]);
}

// ============================================================================
// 1. Real Ink Negative Regression (REAL_INK_NEGATIVE_TESTED)
// ============================================================================

function findRealInkPath(): string {
  const candidates = [
    path.resolve(process.cwd(), "../.tmp/tri-ocr-native/integral_case_01.json"),
    path.resolve(process.cwd(), ".tmp/tri-ocr-native/integral_case_01.json"),
    path.resolve(__dirname, "../../../.tmp/tri-ocr-native/integral_case_01.json"),
    path.resolve(__dirname, "../../.tmp/tri-ocr-native/integral_case_01.json"),
    "D:/SGU/DuAn/Coach_Learning_OCR_QA32/.tmp/tri-ocr-native/integral_case_01.json",
  ];
  return candidates.find((p) => fs.existsSync(p)) ?? candidates[0];
}

const realInkPath = findRealInkPath();

test("REAL_INK_NEGATIVE_TESTED: integral handwriting capture preserves all 10 strokes with zero false SYSTEM", (t) => {
  if (!fs.existsSync(realInkPath)) {
    t.skip("Real ink capture fixture .tmp/tri-ocr-native/integral_case_01.json not found on disk");
    return;
  }

  const rawBytes = fs.readFileSync(realInkPath, "utf-8");
  const captureRaw = JSON.parse(rawBytes);

  // 1. Validate schema
  const capture = validateOcrEvalCapture(captureRaw);
  assert.equal(capture.schemaVersion, 1);
  assert.equal(capture.sourceKind, "MATHCANVAS_INK");
  assert.equal(capture.pageIndex, 0);
  assert.equal(capture.strokes.length, 10);

  // 2. Reconstruct input & test immutability
  const strokes = reconstructSegmentationInput(capture);
  const serializedBefore = JSON.stringify(strokes);

  // 3. Replay segmentation
  const regions = segmentPageInk_v2(strokes);
  assert.equal(regions.length, 4, "Segmentation v2 must match recorded 4 regions");
  const replayedStrokeIds = regions.flatMap((r) => r.strokes.map((s) => s.id));
  assert.equal(replayedStrokeIds.length, 10);
  assert.deepEqual(
    regions.map((r) => r.strokes.map((s) => s.id)),
    capture.segmentation.regions.map((r) => r.strokeIds),
    "Replayed regions must match captured regions snapshot",
  );

  // 4. Structural candidates & Integral Guard
  const candidates = detectStructuralCandidates(strokes);
  assert.equal(candidates.length, 4);

  // Assert Integral Guard: zero false SYSTEM or ALTERNATIVES
  const hasSystem = candidates.some((c) => c.kind === "SYSTEM");
  const hasAlternatives = candidates.some((c) => c.kind === "ALTERNATIVES");
  assert.equal(hasSystem, false, "Integral stroke must NOT be classified as SYSTEM");
  assert.equal(hasAlternatives, false, "Integral stroke must NOT be classified as ALTERNATIVES");
  assert.ok(candidates.every((c) => c.kind === "INDEPENDENT"));

  // 5. Shadow QA Report invariants
  const qaReport = buildOcrShadowQaReport(strokes, regions);
  assert.equal(qaReport.sourcePenStrokeCount, 10);
  assert.equal(qaReport.baselineRegionCount, 4);
  assert.equal(qaReport.structuralCandidateCount, 4);
  assert.equal(qaReport.baselineMissingStrokeIds.length, 0);
  assert.equal(qaReport.baselineDuplicateStrokeIds.length, 0);
  assert.equal(qaReport.shadowMissingStrokeIds.length, 0);
  assert.equal(qaReport.shadowDuplicateStrokeIds.length, 0);
  assert.equal(qaReport.shadowUnknownStrokeIds.length, 0);

  // 6. Input immutability
  assert.equal(JSON.stringify(strokes), serializedBefore, "Input strokes must not be mutated");

  // 7. Determinism: 5 repeated runs yield identical results
  for (let i = 0; i < 5; i++) {
    const repeated = detectStructuralCandidates(strokes);
    assert.deepEqual(
      repeated.map((c) => ({ id: c.id, kind: c.kind, strokes: c.sourceStrokeIds })),
      candidates.map((c) => ({ id: c.id, kind: c.kind, strokes: c.sourceStrokeIds })),
    );
  }
});

// ============================================================================
// 2. Synthetic Positive Regression (SYNTHETIC_POSITIVE_TESTED)
// ============================================================================

test("SYNTHETIC_POSITIVE_TESTED: curly brace enclosing two equations triggers SYSTEM", () => {
  const brace = makeCurlyBrace("brace", 0.08, 0.1, 0.28);
  const eq1 = makeLine("eq1", 0.13, 0.12);
  const eq2 = makeLine("eq2", 0.13, 0.22);

  const candidates = detectStructuralCandidates([brace, eq1, eq2]);
  const system = candidates.find((c) => c.kind === "SYSTEM");
  assert.ok(system, "Expected SYSTEM candidate");
  assert.equal(system.children.length, 2);
  assert.deepEqual(new Set(system.sourceStrokeIds), new Set(["brace", "eq1", "eq2"]));
});

test("SYNTHETIC_POSITIVE_TESTED: square bracket enclosing two root branches triggers ALTERNATIVES", () => {
  const bracket = makeSquareBracket("bracket", 0.08, 0.1, 0.28);
  const br1 = makeLine("root1", 0.13, 0.12);
  const br2 = makeLine("root2", 0.13, 0.22);

  const candidates = detectStructuralCandidates([bracket, br1, br2]);
  const alt = candidates.find((c) => c.kind === "ALTERNATIVES");
  assert.ok(alt, "Expected ALTERNATIVES candidate");
  assert.equal(alt.children.length, 2);
  assert.deepEqual(new Set(alt.sourceStrokeIds), new Set(["bracket", "root1", "root2"]));
});

test("SYNTHETIC_POSITIVE_TESTED: temporal invariance: bracket drawn after equations yields identical SYSTEM", () => {
  const eq1 = makeLine("eq1", 0.13, 0.12);
  const eq2 = makeLine("eq2", 0.13, 0.22);
  const braceAfter = makeCurlyBrace("brace_after", 0.08, 0.1, 0.28);

  // Equations drawn 1st and 2nd, brace drawn LAST
  const candidates = detectStructuralCandidates([eq1, eq2, braceAfter]);
  const system = candidates.find((c) => c.kind === "SYSTEM");
  assert.ok(system);
  assert.equal(system.children.length, 2);
  assert.deepEqual(new Set(system.sourceStrokeIds), new Set(["eq1", "eq2", "brace_after"]));
});

// ============================================================================
// 3. Negative Boundary Regressions (Guards against False Merges)
// ============================================================================

test("Negative: minus sign between lines does not trigger FRACTION", () => {
  const line1 = makeLine("l1", 0.1, 0.1);
  const minus = makeStroke("minus", [{ x: 0.15, y: 0.14 }, { x: 0.17, y: 0.14 }]);
  const line2 = makeLine("l2", 0.1, 0.17);

  const candidates = detectStructuralCandidates([line1, minus, line2]);
  assert.ok(candidates.every((c) => c.kind !== "FRACTION"));
});

test("Negative: equals sign does not trigger FRACTION", () => {
  const eq1 = makeStroke("eq1", [{ x: 0.1, y: 0.12 }, { x: 0.15, y: 0.12 }]);
  const eq2 = makeStroke("eq2", [{ x: 0.1, y: 0.128 }, { x: 0.15, y: 0.128 }]);
  const line = makeLine("l", 0.1, 0.2);

  const candidates = detectStructuralCandidates([eq1, eq2, line]);
  assert.ok(candidates.every((c) => c.kind !== "FRACTION"));
});

test("Negative: horizontal siblings on a single line do not form SYSTEM", () => {
  const tall = makeStroke("T_stem", [{ x: 0.08, y: 0.1 }, { x: 0.08, y: 0.25 }]);
  const plus = makeLine("plus", 0.12, 0.18, 0.03, 0.02);
  const charA = makeLine("A", 0.18, 0.18, 0.04, 0.02);

  const candidates = detectStructuralCandidates([tall, plus, charA]);
  assert.ok(candidates.every((c) => c.kind !== "SYSTEM" && c.kind !== "ALTERNATIVES"));
});
