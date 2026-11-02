import test from "node:test";
import assert from "node:assert/strict";
import type { InkStroke } from "../src/lib/api/contracts.js";
import type { PageOcrRegion } from "../src/features/math-workspace/utils/page-ocr.js";
import { segmentPageInk_v2 } from "../src/features/math-workspace/utils/page-ocr.js";
import { buildOcrShadowQaReport } from "../src/features/math-workspace/utils/ocr-shadow-qa.js";

function stroke(id: string, x: number, y: number, tool: InkStroke["tool"] = "PEN"): InkStroke {
  return {
    id,
    tool,
    color: "#000",
    width: 2,
    points: [
      { x, y, pressure: 0.5 },
      { x: x + 0.12, y: y + 0.02, pressure: 0.5 },
    ],
  };
}

function region(id: string, strokes: InkStroke[]): PageOcrRegion {
  return { id, strokes, bounds: { left: 0.1, top: 0.1, right: 0.4, bottom: 0.4 } };
}

test("shadow QA uses original baseline regions and does not alter the input", () => {
  const source = [stroke("top", 0.1, 0.1), stroke("bottom", 0.1, 0.4)];
  const baseline = segmentPageInk_v2(source);
  const originalInk = JSON.stringify(source);
  const originalRegions = JSON.stringify(baseline);

  const report = buildOcrShadowQaReport(source, baseline);
  assert.equal(report.sourcePenStrokeCount, 2);
  assert.equal(report.baselineRegionCount, baseline.length);
  assert.ok(report.structuralCandidateCount > 0);
  assert.deepEqual(report.baselineMissingStrokeIds, []);
  assert.deepEqual(report.shadowMissingStrokeIds, []);
  assert.deepEqual(report.shadowDuplicateStrokeIds, []);
  assert.equal(JSON.stringify(source), originalInk);
  assert.equal(JSON.stringify(baseline), originalRegions);
});

test("source highlighter is not counted as a pen stroke or shadow candidate", () => {
  const source = [stroke("pen", 0.1, 0.1), stroke("highlight", 0.15, 0.12, "HIGHLIGHTER")];
  const report = buildOcrShadowQaReport(source, segmentPageInk_v2(source));
  assert.equal(report.sourcePenStrokeCount, 1);
  assert.deepEqual(report.shadowMissingStrokeIds, []);
  assert.ok(report.candidates.every((candidate) => !candidate.strokeIds.includes("highlight")));
});

test("baseline diagnostics show a missing and duplicated stroke without changing predictions", () => {
  const a = stroke("a", 0.1, 0.1);
  const b = stroke("b", 0.1, 0.4);
  const report = buildOcrShadowQaReport([a, b], [
    region("duplicate-1", [a]),
    region("duplicate-2", [a]),
  ]);
  assert.deepEqual(report.baselineMissingStrokeIds, ["b"]);
  assert.deepEqual(report.baselineDuplicateStrokeIds, ["a"]);
  assert.deepEqual(report.shadowMissingStrokeIds, []);
});

test("candidate-to-baseline overlap is traced by stroke ID, not box proximity", () => {
  const a = stroke("a", 0.1, 0.1);
  const b = stroke("b", 0.1, 0.4);
  const report = buildOcrShadowQaReport([a, b], [
    region("r-a", [a]),
    region("r-b", [b]),
  ]);
  for (const candidate of report.candidates) {
    const overlaps = candidate.overlappingBaselineRegions;
    const matched = new Set(overlaps.map((item) => item.regionId));
    assert.ok([...matched].every((id) => id === "r-a" || id === "r-b"));
    const overlapTotal = overlaps.reduce((sum, item) => sum + item.strokeCount, 0);
    assert.equal(overlapTotal, candidate.strokeIds.length);
  }
});

test("no pen ink returns an empty nonauthoritative QA comparison", () => {
  const report = buildOcrShadowQaReport([], []);
  assert.equal(report.structuralCandidateCount, 0);
  assert.deepEqual(report.candidates, []);
  assert.deepEqual(report.shadowMissingStrokeIds, []);
});
