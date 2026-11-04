import test from "node:test";
import assert from "node:assert/strict";
import type { InkStroke } from "../src/lib/api/contracts.js";
import type { PageOcrRegion } from "../src/features/math-workspace/utils/page-ocr.js";
import { segmentPageInk_v2 } from "../src/features/math-workspace/utils/page-ocr.js";
import { createOcrEvalCapture } from "../src/features/math-workspace/utils/ocr-eval-capture.js";

function stroke(id: string, y: number, tool: InkStroke["tool"] = "PEN"): InkStroke {
  return {
    id,
    tool,
    color: "#000000",
    width: 2,
    points: [
      { x: 0.1, y, pressure: 0.5 },
      { x: 0.2, y: y + 0.01, pressure: 0.5 },
    ],
  };
}

function region(id: string, strokes: InkStroke[]): PageOcrRegion {
  return { id, strokes, bounds: { left: 0.1, top: 0.1, right: 0.2, bottom: 0.4 } };
}

test("capture preserves full source ink and v2 region mapping without uploading", () => {
  const ink = [stroke("top", 0.1), stroke("highlight", 0.2, "HIGHLIGHTER"), stroke("bottom", 0.4)];
  const regions = segmentPageInk_v2(ink);
  const captured = createOcrEvalCapture(0, ink, regions);

  assert.equal(captured.schemaVersion, 1);
  assert.equal(captured.sourceKind, "MATHCANVAS_INK");
  assert.deepEqual(captured.strokes, ink);
  assert.deepEqual(captured.segmentation.regions.map((r) => r.strokeIds),
    regions.map((r) => r.strokes.map((s) => s.id)));
  assert.deepEqual(captured.diagnostics, {
    missingPenStrokeIds: [],
    repeatedPenStrokeIds: [],
    unknownRegionStrokeIds: [],
  });
  assert.equal(JSON.stringify(captured).includes("attemptId"), false);
});

test("a broken segmentation remains capturable and reports missing/repeated/unknown pen references", () => {
  const ink = [stroke("brace", 0.1), stroke("equation1", 0.2), stroke("equation2", 0.3)];
  const malformedRegions = [
    region("a", [ink[1]]),
    region("b", [ink[1], stroke("foreign", 0.4)]),
  ];
  const captured = createOcrEvalCapture(2, ink, malformedRegions);

  assert.deepEqual(captured.strokes, ink);
  assert.deepEqual(captured.diagnostics.missingPenStrokeIds, ["brace", "equation2"]);
  assert.deepEqual(captured.diagnostics.repeatedPenStrokeIds, ["equation1"]);
  assert.deepEqual(captured.diagnostics.unknownRegionStrokeIds, ["foreign"]);
  assert.equal(captured.segmentation.regions.length, 2);
});

test("capture is a deterministic deep snapshot, independent of later pen and region edits", () => {
  const ink = [stroke("a", 0.1)];
  const regions = [region("r", ink)];
  const snapshot = createOcrEvalCapture(0, ink, regions);
  const serialized = JSON.stringify(snapshot);

  ink[0].points[0].x = 0.9;
  regions[0].bounds.left = 0.9;
  regions[0].strokes.push(stroke("b", 0.2));

  assert.equal(JSON.stringify(snapshot), serialized);
  assert.equal(snapshot.strokes[0].points[0].x, 0.1);
  assert.equal(snapshot.segmentation.regions[0].bounds.left, 0.1);
  assert.deepEqual(snapshot.segmentation.regions[0].strokeIds, ["a"]);
});

test("invalid page indices are rejected", () => {
  assert.throws(() => createOcrEvalCapture(-1, [], []), /OCR_CAPTURE_INVALID_PAGE/);
  assert.throws(() => createOcrEvalCapture(1.5, [], []), /OCR_CAPTURE_INVALID_PAGE/);
});
