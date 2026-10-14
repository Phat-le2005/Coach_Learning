import test from "node:test";
import assert from "node:assert/strict";

import {
  normalizeCoordinate,
  denormalizeCoordinate,
  distanceSquared,
  distanceToSegmentSquared,
  strokeIntersectsPoint,
  calculateStrokeBoundingBox,
} from "../src/features/math-workspace/utils/ink-math.js";
import { A4_WIDTH, A4_HEIGHT, A4_ASPECT_RATIO } from "../src/features/math-workspace/types.js";
import type { InkStroke } from "../src/features/math-workspace/types.js";

test("A4 dimensions conform to standard 1 : sqrt(2) aspect ratio", () => {
  const ratio = A4_HEIGHT / A4_WIDTH;
  const sqrt2 = Math.SQRT2;
  // Standard A4 794x1123 is within 0.1% of sqrt(2)
  assert.ok(Math.abs(ratio - sqrt2) < 0.01);
  assert.equal(A4_ASPECT_RATIO, A4_HEIGHT / A4_WIDTH);
});

test("normalizeCoordinate clamps and normalizes within [0, 1]", () => {
  assert.equal(normalizeCoordinate(0, 1000), 0);
  assert.equal(normalizeCoordinate(500, 1000), 0.5);
  assert.equal(normalizeCoordinate(1000, 1000), 1);
  assert.equal(normalizeCoordinate(-50, 1000), 0);
  assert.equal(normalizeCoordinate(1200, 1000), 1);
});

test("denormalizeCoordinate maps normalized value back to target dimension", () => {
  assert.equal(denormalizeCoordinate(0.5, 794), 397);
  assert.equal(denormalizeCoordinate(0, 1123), 0);
  assert.equal(denormalizeCoordinate(1, 1123), 1123);
});

test("distanceToSegmentSquared calculates exact squared perpendicular distance", () => {
  // Segment along X axis from (0, 0) to (10, 0)
  // Point at (5, 4) -> perpendicular distance is 4, distance squared is 16
  const distSq = distanceToSegmentSquared(5, 4, 0, 0, 10, 0);
  assert.equal(distSq, 16);

  // Point beyond the end at (15, 0) -> closest point is (10, 0), distance squared is 25
  const endDistSq = distanceToSegmentSquared(15, 0, 0, 0, 10, 0);
  assert.equal(endDistSq, 25);
});

test("strokeIntersectsPoint detects intersection for stroke eraser", () => {
  const stroke: InkStroke = {
    id: "test-stroke-1",
    tool: "PEN",
    color: "#0f172a",
    width: 2,
    points: [
      { x: 0.1, y: 0.1, pressure: 0.5 },
      { x: 0.5, y: 0.5, pressure: 0.5 },
    ],
  };

  // Point exactly on the midpoint (0.3, 0.3)
  assert.ok(strokeIntersectsPoint(stroke, 0.3, 0.3, 0.02));

  // Point near the stroke (0.31, 0.3)
  assert.ok(strokeIntersectsPoint(stroke, 0.31, 0.3, 0.02));

  // Point far away from stroke (0.8, 0.2)
  assert.ok(!strokeIntersectsPoint(stroke, 0.8, 0.2, 0.02));
});

test("calculateStrokeBoundingBox calculates correct normalized bounds", () => {
  const stroke: InkStroke = {
    id: "test-stroke-2",
    tool: "PEN",
    color: "#0f172a",
    width: 2,
    points: [
      { x: 0.2, y: 0.4, pressure: 0.5 },
      { x: 0.7, y: 0.1, pressure: 0.5 },
      { x: 0.5, y: 0.9, pressure: 0.5 },
    ],
  };

  const bbox = calculateStrokeBoundingBox(stroke);
  assert.equal(bbox.minX, 0.2);
  assert.equal(bbox.minY, 0.1);
  assert.equal(bbox.maxX, 0.7);
  assert.equal(bbox.maxY, 0.9);
});
