import test from "node:test";
import assert from "node:assert/strict";
import type { InkStroke } from "../src/lib/api/contracts.js";
import {
  createOcrEvalCapture,
  type OcrEvalCaptureV1,
} from "../src/features/math-workspace/utils/ocr-eval-capture.js";
import {
  segmentPageInk_v1,
  segmentPageInk_v2,
  type PageOcrRegion,
} from "../src/features/math-workspace/utils/page-ocr.js";
import {
  validateOcrEvalCapture,
  reconstructSegmentationInput,
  replaySegmentationCapture,
  evaluateSegmentationAgainstGroundTruth,
  type OcrGroundTruthV1,
} from "../src/features/math-workspace/utils/ocr-eval-replay.js";

function stroke(
  id: string,
  x: number,
  y: number,
  w = 0.02,
  h = 0.015,
  tool: InkStroke["tool"] = "PEN",
): InkStroke {
  return {
    id,
    tool,
    color: "#000000",
    width: 2,
    points: [
      { x, y, pressure: 0.5 },
      { x: x + w, y: y + h, pressure: 0.5 },
    ],
  };
}

function region(id: string, strokes: InkStroke[]): PageOcrRegion {
  return {
    id,
    strokes,
    bounds: {
      left: Math.min(...strokes.flatMap((s) => s.points.map((p) => p.x))),
      top: Math.min(...strokes.flatMap((s) => s.points.map((p) => p.y))),
      right: Math.max(...strokes.flatMap((s) => s.points.map((p) => p.x))),
      bottom: Math.max(...strokes.flatMap((s) => s.points.map((p) => p.y))),
    },
  };
}

// ============================================================================
// 1. Capture Reader & Validator Tests
// ============================================================================

test("validateOcrEvalCapture accepts valid capture and reconstructs clean strokes", () => {
  const ink = [stroke("s1", 0.1, 0.1), stroke("s2", 0.1, 0.2)];
  const regions = segmentPageInk_v2(ink);
  const capture = createOcrEvalCapture(0, ink, regions);

  const validated = validateOcrEvalCapture(capture);
  assert.equal(validated.schemaVersion, 1);
  assert.equal(validated.sourceKind, "MATHCANVAS_INK");
  assert.equal(validated.pageIndex, 0);
  assert.equal(validated.strokes.length, 2);

  const restored = reconstructSegmentationInput(validated);
  assert.deepEqual(restored, ink);
  // Modifying restored strokes does not mutate validated snapshot
  restored[0].points[0].x = 0.99;
  assert.equal(validated.strokes[0].points[0].x, 0.1);
});

test("validateOcrEvalCapture rejects invalid root, unsupported schema, or wrong sourceKind", () => {
  assert.throws(() => validateOcrEvalCapture(null), /OCR_CAPTURE_INVALID_ROOT/);
  assert.throws(() => validateOcrEvalCapture("string"), /OCR_CAPTURE_INVALID_ROOT/);
  assert.throws(
    () => validateOcrEvalCapture({ schemaVersion: 2, sourceKind: "MATHCANVAS_INK" }),
    /OCR_CAPTURE_UNSUPPORTED_VERSION/,
  );
  assert.throws(
    () => validateOcrEvalCapture({ schemaVersion: 1, sourceKind: "IMAGE" }),
    /OCR_CAPTURE_INVALID_SOURCE/,
  );
});

test("validateOcrEvalCapture rejects negative or non-integer pageIndex", () => {
  const base = {
    schemaVersion: 1,
    sourceKind: "MATHCANVAS_INK",
    strokes: [],
    segmentation: { algorithm: "v2", regions: [] },
    diagnostics: { missingPenStrokeIds: [], repeatedPenStrokeIds: [], unknownRegionStrokeIds: [] },
  };
  assert.throws(() => validateOcrEvalCapture({ ...base, pageIndex: -1 }), /OCR_CAPTURE_INVALID_PAGE/);
  assert.throws(() => validateOcrEvalCapture({ ...base, pageIndex: 1.5 }), /OCR_CAPTURE_INVALID_PAGE/);
});

test("validateOcrEvalCapture rejects malformed strokes, duplicate IDs, and out-of-bound coords", () => {
  const base = {
    schemaVersion: 1,
    sourceKind: "MATHCANVAS_INK",
    pageIndex: 0,
    segmentation: { algorithm: "v2", regions: [] },
    diagnostics: { missingPenStrokeIds: [], repeatedPenStrokeIds: [], unknownRegionStrokeIds: [] },
  };

  // Duplicate stroke ID
  assert.throws(
    () =>
      validateOcrEvalCapture({
        ...base,
        strokes: [stroke("dup", 0.1, 0.1), stroke("dup", 0.2, 0.2)],
      }),
    /OCR_CAPTURE_DUPLICATE_STROKE_ID/,
  );

  // Out of bounds coordinate (> 1.2 or < -0.2)
  assert.throws(
    () =>
      validateOcrEvalCapture({
        ...base,
        strokes: [
          {
            id: "bad_coord",
            tool: "PEN",
            color: "#000",
            width: 2,
            points: [{ x: 5.5, y: 0.1, pressure: 0.5 }],
          },
        ],
      }),
    /OCR_CAPTURE_OUT_OF_BOUNDS/,
  );
});

test("validateOcrEvalCapture rejects sensitive keys, token leakage, and prototype pollution", () => {
  const base = {
    schemaVersion: 1,
    sourceKind: "MATHCANVAS_INK",
    pageIndex: 0,
    strokes: [],
    segmentation: { algorithm: "v2", regions: [] },
    diagnostics: { missingPenStrokeIds: [], repeatedPenStrokeIds: [], unknownRegionStrokeIds: [] },
  };

  assert.throws(
    () => validateOcrEvalCapture({ ...base, token: "secret-token-123" }),
    /OCR_CAPTURE_PRIVACY_VIOLATION/,
  );
  assert.throws(
    () => validateOcrEvalCapture({ ...base, attemptId: "attempt-uuid-456" }),
    /OCR_CAPTURE_PRIVACY_VIOLATION/,
  );
  assert.throws(
    () =>
      validateOcrEvalCapture(
        JSON.parse(
          JSON.stringify({ ...base, constructor: "polluted" }),
        ),
      ),
    /OCR_CAPTURE_INSECURE_PAYLOAD/,
  );
  assert.throws(
    () =>
      validateOcrEvalCapture(
        JSON.parse(
          '{"schemaVersion": 1, "sourceKind": "MATHCANVAS_INK", "pageIndex": 0, "strokes": [], "segmentation": {"algorithm": "v2", "regions": []}, "diagnostics": {"missingPenStrokeIds": [], "repeatedPenStrokeIds": [], "unknownRegionStrokeIds": []}, "__proto__": {"evil": true}}',
        ),
      ),
    /OCR_CAPTURE_INSECURE_PAYLOAD/,
  );
});

// ============================================================================
// 2. Baseline Replay Runner Tests
// ============================================================================

test("replaySegmentationCapture reports identicalToCapture for matching replay", () => {
  const ink = [
    stroke("line1_a", 0.1, 0.1, 0.2, 0.02),
    stroke("line2_a", 0.1, 0.2, 0.2, 0.02),
  ];
  const regions = segmentPageInk_v2(ink);
  const capture = createOcrEvalCapture(0, ink, regions);

  const report = replaySegmentationCapture(capture, { algorithm: "v2", sampleId: "sample-01" });
  assert.equal(report.sampleId, "sample-01");
  assert.equal(report.identicalToCapture, true);
  assert.equal(report.diff.matchingRegionCount, true);
  assert.equal(report.diff.strokeCoverageIntact, true);
  assert.equal(report.diff.missingStrokes.length, 0);
  assert.equal(report.diff.duplicateStrokes.length, 0);
  assert.equal(report.diff.membershipDifferences.length, 0);
  assert.equal(report.diff.readingOrderChanged, false);
});

test("replaySegmentationCapture detects divergence when comparing v1 replay against v2 fraction capture", () => {
  // Fraction ink: numerator, fraction bar, denominator
  const ink = [
    stroke("num", 0.12, 0.15, 0.05, 0.02),
    stroke("bar", 0.1, 0.18, 0.09, 0.003),
    stroke("den", 0.12, 0.2, 0.05, 0.02),
  ];
  // Captured with v2 (groups fraction into 1 region)
  const v2Regions = segmentPageInk_v2(ink);
  assert.equal(v2Regions.length, 1);
  const capture = createOcrEvalCapture(0, ink, v2Regions);

  // Replay with v1 (which splits fraction into 3 or 2 separate lines)
  const reportV1 = replaySegmentationCapture(capture, { algorithm: "v1" });
  assert.equal(reportV1.identicalToCapture, false);
  assert.equal(reportV1.diff.strokeCoverageIntact, true); // All strokes still covered!
  assert.ok(reportV1.diff.membershipDifferences.length > 0);
  assert.notEqual(reportV1.diff.replayedRegionCount, reportV1.diff.capturedRegionCount);
});

// ============================================================================
// 3. Ground Truth Evaluation Metrics Tests
// ============================================================================

test("evaluateSegmentationAgainstGroundTruth: perfect grouping yields 1.0 F1 and 0 false splits/merges", () => {
  const ink = [
    stroke("l1_a", 0.1, 0.1),
    stroke("l1_b", 0.15, 0.1),
    stroke("l2_a", 0.1, 0.2),
  ];
  const regions = [
    region("r1", [ink[0], ink[1]]),
    region("r2", [ink[2]]),
  ];

  const groundTruth: OcrGroundTruthV1 = {
    schemaVersion: 1,
    sampleId: "gold-01",
    expectedGroups: [
      { groupId: "g1", strokeIds: ["l1_a", "l1_b"], kind: "EQUATION" },
      { groupId: "g2", strokeIds: ["l2_a"], kind: "EQUATION" },
    ],
    expectedReadingOrder: ["g1", "g2"],
  };

  const metrics = evaluateSegmentationAgainstGroundTruth(regions, groundTruth);
  assert.equal(metrics.strokeCoverage, 1.0);
  assert.equal(metrics.missingStrokeIds.length, 0);
  assert.equal(metrics.duplicateStrokeIds.length, 0);
  assert.equal(metrics.exactGroupMatches, 2);
  assert.equal(metrics.falseSplitCount, 0);
  assert.equal(metrics.falseMergeCount, 0);
  assert.equal(metrics.groupPrecision, 1.0);
  assert.equal(metrics.groupRecall, 1.0);
  assert.equal(metrics.groupF1, 1.0);
  assert.equal(metrics.readingOrderCorrectness, 1.0);
});

test("evaluateSegmentationAgainstGroundTruth: detects false split accurately", () => {
  const ink = [
    stroke("f_num", 0.1, 0.1),
    stroke("f_bar", 0.1, 0.12),
    stroke("f_den", 0.1, 0.14),
  ];
  // Prediction splits the single fraction group into 2 regions
  const regions = [
    region("r1", [ink[0], ink[1]]),
    region("r2", [ink[2]]),
  ];

  const groundTruth: OcrGroundTruthV1 = {
    schemaVersion: 1,
    sampleId: "fraction-split",
    expectedGroups: [
      { groupId: "g_frac", strokeIds: ["f_num", "f_bar", "f_den"], kind: "FRACTION" },
    ],
  };

  const metrics = evaluateSegmentationAgainstGroundTruth(regions, groundTruth);
  assert.equal(metrics.strokeCoverage, 1.0);
  assert.equal(metrics.exactGroupMatches, 0);
  assert.equal(metrics.falseSplitCount, 1);
  assert.equal(metrics.falseMergeCount, 0);
  assert.equal(metrics.groupRecall, 0.0);
});

test("evaluateSegmentationAgainstGroundTruth: detects false merge accurately", () => {
  const ink = [
    stroke("eq1", 0.1, 0.1),
    stroke("eq2", 0.1, 0.2),
  ];
  // Prediction improperly merges two independent equations into 1 region
  const regions = [
    region("r_merged", [ink[0], ink[1]]),
  ];

  const groundTruth: OcrGroundTruthV1 = {
    schemaVersion: 1,
    sampleId: "over-merged-lines",
    expectedGroups: [
      { groupId: "g1", strokeIds: ["eq1"], kind: "EQUATION" },
      { groupId: "g2", strokeIds: ["eq2"], kind: "EQUATION" },
    ],
  };

  const metrics = evaluateSegmentationAgainstGroundTruth(regions, groundTruth);
  assert.equal(metrics.strokeCoverage, 1.0);
  assert.equal(metrics.exactGroupMatches, 0);
  assert.equal(metrics.falseSplitCount, 0);
  assert.equal(metrics.falseMergeCount, 1); // 1 region contains strokes from 2 distinct groups
  assert.equal(metrics.groupPrecision, 0.0);
});

test("evaluateSegmentationAgainstGroundTruth: detects inverted reading order", () => {
  const ink = [
    stroke("top_stroke", 0.1, 0.1),
    stroke("bottom_stroke", 0.1, 0.3),
  ];
  // Inverted: bottom region comes first in array
  const regions = [
    region("r_bottom", [ink[1]]),
    region("r_top", [ink[0]]),
  ];

  const groundTruth: OcrGroundTruthV1 = {
    schemaVersion: 1,
    sampleId: "inverted-order",
    expectedGroups: [
      { groupId: "g_top", strokeIds: ["top_stroke"] },
      { groupId: "g_bottom", strokeIds: ["bottom_stroke"] },
    ],
    expectedReadingOrder: ["g_top", "g_bottom"],
  };

  const metrics = evaluateSegmentationAgainstGroundTruth(regions, groundTruth);
  assert.equal(metrics.exactGroupMatches, 2);
  // Concordance is 0 because the order was completely inverted
  assert.equal(metrics.readingOrderCorrectness, 0.0);
});


test("reading order is not reported as perfect when a merge leaves no comparable pair", () => {
  const ink = [stroke("first", 0.1, 0.1), stroke("second", 0.1, 0.3)];
  const regions = [region("both", ink)];
  const truth: OcrGroundTruthV1 = {
    schemaVersion: 1,
    sampleId: "reading-order-unobservable",
    expectedGroups: [
      { groupId: "g1", strokeIds: ["first"] },
      { groupId: "g2", strokeIds: ["second"] },
    ],
    expectedReadingOrder: ["g1", "g2"],
  };
  const metrics = evaluateSegmentationAgainstGroundTruth(regions, truth);
  assert.equal(metrics.falseMergeCount, 1);
  assert.equal(metrics.readingOrderComparablePairs, 0);
  assert.equal(metrics.readingOrderCorrectness, null);
});
