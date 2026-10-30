import test from "node:test";
import assert from "node:assert/strict";
import type { InkStroke } from "../src/lib/api/contracts.js";
import {
  mergePageOcrRegions,
  segmentPageInk,
  segmentPageInk_v1,
  segmentPageInk_v2,
  splitPageOcrRegion,
} from "../src/features/math-workspace/utils/page-ocr.js";

function stroke(
  id: string,
  x: number,
  y: number,
  w = 0.015,
  h = 0.012,
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

// ---------------------------------------------------------------------------
// 1. Existing Baseline Tests (Must continue to pass for regression safety)
// ---------------------------------------------------------------------------

test("blank page has no regions", () => {
  assert.deepEqual(segmentPageInk([]), []);
  assert.deepEqual(segmentPageInk([], { algorithm: "v1" }), []);
  assert.deepEqual(segmentPageInk([], { algorithm: "v2" }), []);
});

test("page rows preserve every pen stroke exactly once", () => {
  const ink = [
    stroke("a", 0.1, 0.1),
    stroke("h", 0.1, 0.1, 0.01, 0.01, "HIGHLIGHTER"),
    stroke("c", 0.1, 0.23),
    stroke("b", 0.5, 0.105),
  ];
  const regions = segmentPageInk(ink);
  assert.deepEqual(
    regions.map((item) => item.strokes.map((s) => s.id)),
    [["a", "b"], ["c"]],
  );
  assert.deepEqual(segmentPageInk(ink), regions);
});

test("a full page of twenty handwritten lines keeps all regions in visual order", () => {
  const ink = Array.from({ length: 20 }, (_, line) => [
    stroke(`line-${line}-left`, 0.1, 0.03 + line * 0.043),
    stroke(`line-${line}-right`, 0.55, 0.034 + line * 0.043),
  ]).flat();
  const regions = segmentPageInk(ink);
  assert.equal(regions.length, 20);
  assert.deepEqual(
    regions.map((item) => item.strokes.length),
    Array(20).fill(2),
  );
  assert.deepEqual(
    new Set(regions.flatMap((item) => item.strokes.map((s) => s.id))).size,
    40,
  );
  assert.ok(
    regions.every((item, index) => index === 0 || item.bounds.top > regions[index - 1].bounds.top),
  );
});

test("merge and split preserve every stroke and its page order", () => {
  const ink = [
    stroke("first", 0.1, 0.1),
    stroke("second", 0.3, 0.15),
    stroke("third", 0.1, 0.4),
  ];
  const segmented = segmentPageInk(ink);
  const merged = mergePageOcrRegions(segmented, 0, ink);
  assert.deepEqual(
    merged[0].strokes.map((s) => s.id),
    ["first", "second"],
  );
  const restored = splitPageOcrRegion(merged, 0, 0.14);
  assert.deepEqual(
    restored.flatMap((item) => item.strokes.map((s) => s.id)),
    ["first", "second", "third"],
  );
  assert.equal(splitPageOcrRegion(merged, 0, 0), merged);
});

// ---------------------------------------------------------------------------
// 2. New PR1 Tests: Algorithm Switch & Invariants
// ---------------------------------------------------------------------------

test("options.algorithm allows explicit toggle between v1 and v2", () => {
  const ink = [
    stroke("frac_bar", 0.1, 0.15, 0.12, 0.002), // Thin & wide fraction bar
    stroke("num", 0.12, 0.12, 0.04, 0.02),      // Numerator above
    stroke("den", 0.12, 0.17, 0.04, 0.02),      // Denominator below
  ];
  const v1 = segmentPageInk(ink, { algorithm: "v1" });
  const v2 = segmentPageInk(ink, { algorithm: "v2" });
  const def = segmentPageInk(ink); // default should be v2

  // v1 splits fraction into separate regions (num+bar in one, den in another)
  assert.equal(v1.length, 2);
  // v2 binds entire fraction into 1 coherent region
  assert.equal(v2.length, 1);
  assert.deepEqual(def, v2);
});

test("invariants: stroke conservation and tool isolation across all configurations", () => {
  const ink = [
    stroke("pen1", 0.1, 0.1),
    stroke("hl1", 0.1, 0.1, 0.05, 0.05, "HIGHLIGHTER"),
    stroke("pen2", 0.2, 0.1),
    stroke("hl2", 0.3, 0.2, 0.05, 0.05, "HIGHLIGHTER"),
    stroke("pen3", 0.1, 0.2),
  ];
  for (const algo of ["v1", "v2"] as const) {
    const regions = segmentPageInk(ink, { algorithm: algo });
    const allResultStrokes = regions.flatMap((r) => r.strokes);
    const resultIds = allResultStrokes.map((s) => s.id);

    // No highlighters
    assert.ok(allResultStrokes.every((s) => s.tool === "PEN"));
    // Exactly the 3 pen strokes
    assert.deepEqual(resultIds.sort(), ["pen1", "pen2", "pen3"].sort());
    // Zero duplicates
    assert.equal(new Set(resultIds).size, 3);
  }
});

test("deterministic output: identical inputs produce identical regions and bounds", () => {
  const ink = [
    stroke("s1", 0.1, 0.1),
    stroke("s2", 0.15, 0.1),
    stroke("s3", 0.1, 0.25),
  ];
  const r1 = segmentPageInk(ink, { algorithm: "v2" });
  const r2 = segmentPageInk(ink, { algorithm: "v2" });
  assert.deepEqual(r1, r2);
});

// ---------------------------------------------------------------------------
// 3. New PR1 Tests: Geometric Edge Cases & Minus Sign Guard
// ---------------------------------------------------------------------------

test("fraction binding binds numerator, bar, and denominator into 1 region", () => {
  const ink = [
    stroke("f_bar", 0.15, 0.2, 0.1, 0.003),
    stroke("f_num", 0.16, 0.16, 0.04, 0.025),
    stroke("f_den", 0.16, 0.22, 0.04, 0.025),
  ];
  const regions = segmentPageInk_v2(ink);
  assert.equal(regions.length, 1);
  assert.deepEqual(
    new Set(regions[0].strokes.map((s) => s.id)),
    new Set(["f_bar", "f_num", "f_den"]),
  );
});

test("minus sign guard: a horizontal minus sign '-' does not trigger fraction binding", () => {
  // Formula: "x - 2 = 0" on line 1, "y = 4" on line 2
  // Minus sign has wide aspect ratio, but strokes are on left/right, NOT above/below!
  const ink = [
    stroke("x_var", 0.1, 0.1, 0.03, 0.025),
    stroke("minus", 0.14, 0.112, 0.02, 0.003), // thin wide stroke, but no stacked strokes
    stroke("two", 0.17, 0.1, 0.03, 0.025),
    stroke("eq", 0.21, 0.11, 0.025, 0.01),
    stroke("zero", 0.24, 0.1, 0.025, 0.025),
    // Distinct line below
    stroke("line2", 0.1, 0.18, 0.15, 0.025),
  ];
  const regions = segmentPageInk_v2(ink);
  assert.equal(regions.length, 2);
  assert.ok(regions[0].strokes.map((s) => s.id).includes("minus"));
  assert.ok(!regions[0].strokes.map((s) => s.id).includes("line2"));
});

test("tight consecutive lines are not overmerged in v2", () => {
  const ink = [
    stroke("l1_a", 0.1, 0.1, 0.15, 0.02),
    stroke("l1_b", 0.28, 0.1, 0.15, 0.02),
    stroke("l2_a", 0.1, 0.138, 0.15, 0.02), // tight vertical gap = 0.018 (~20px)
    stroke("l2_b", 0.28, 0.138, 0.15, 0.02),
  ];
  const regions = segmentPageInk_v2(ink);
  assert.equal(regions.length, 2);
  assert.deepEqual(regions[0].strokes.map((s) => s.id), ["l1_a", "l1_b"]);
  assert.deepEqual(regions[1].strokes.map((s) => s.id), ["l2_a", "l2_b"]);
});

test("dynamic column gutter: off-center two-column layout preserves natural reading order", () => {
  // Off-center layout: Left column at x in [0.05, 0.38], Right column at x in [0.55, 0.90]
  // Gutter is between 0.38 and 0.55 (~135px gap)
  const ink = [
    // Left Column line 1 & 2
    stroke("colL_1", 0.05, 0.1, 0.25, 0.025),
    stroke("colL_2", 0.05, 0.2, 0.25, 0.025),
    // Right Column line 1 & 2
    stroke("colR_1", 0.55, 0.1, 0.25, 0.025),
    stroke("colR_2", 0.55, 0.2, 0.25, 0.025),
  ];
  const regions = segmentPageInk_v2(ink);
  assert.equal(regions.length, 4);
  // Natural reading order: Left col first, then Right col
  assert.equal(regions[0].strokes[0].id, "colL_1");
  assert.equal(regions[1].strokes[0].id, "colL_2");
  assert.equal(regions[2].strokes[0].id, "colR_1");
  assert.equal(regions[3].strokes[0].id, "colR_2");
});

test("two columns without clean gutter fallback to single column flow safely", () => {
  // Crossing stroke in the middle breaks the gutter
  const ink = [
    stroke("left1", 0.1, 0.1, 0.15, 0.02),
    stroke("cross", 0.2, 0.15, 0.55, 0.02), // stroke spanning across the page
    stroke("right1", 0.65, 0.2, 0.15, 0.02),
  ];
  const regions = segmentPageInk_v2(ink);
  // Does not crash, preserves all strokes
  const allIds = regions.flatMap((r) => r.strokes.map((s) => s.id));
  assert.deepEqual(allIds.sort(), ["cross", "left1", "right1"].sort());
});

test("temporal order vs visual reading order: strokes within a region keep chronological drawing order", () => {
  // User drew denominator first, then numerator, then fraction bar
  const ink = [
    stroke("den", 0.12, 0.22, 0.04, 0.025),     // drawn 1st
    stroke("num", 0.12, 0.16, 0.04, 0.025),     // drawn 2nd
    stroke("f_bar", 0.1, 0.2, 0.1, 0.003),       // drawn 3rd
  ];
  const regions = segmentPageInk_v2(ink);
  assert.equal(regions.length, 1);
  // Strokes inside the region must be ordered by original drawing sequence for HMER!
  assert.deepEqual(
    regions[0].strokes.map((s) => s.id),
    ["den", "num", "f_bar"],
  );
});
