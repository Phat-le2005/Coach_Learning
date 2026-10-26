import test from "node:test";
import assert from "node:assert/strict";
import type { InkStroke } from "../src/lib/api/contracts.js";
import { mergePageOcrRegions, segmentPageInk, splitPageOcrRegion } from "../src/features/math-workspace/utils/page-ocr.js";

function stroke(id: string, x: number, y: number, height = 0.012, tool: InkStroke["tool"] = "PEN"): InkStroke {
  return { id, tool, color: "#000", width: 2, points: [
    { x, y, pressure: 0.5 }, { x: x + 0.015, y: y + height, pressure: 0.5 },
  ] };
}

// Page OCR regions are suggested visual rows.
test('blank page has no regions', () => {
  assert.deepEqual(segmentPageInk([]), []);
});

test('page rows preserve every pen stroke exactly once', () => {
  const ink = [stroke('a', 0.1, 0.1), stroke('h', 0.1, 0.1, 0.01, 'HIGHLIGHTER'),
    stroke('c', 0.1, 0.23), stroke('b', 0.5, 0.105)];
  const regions = segmentPageInk(ink);
  assert.deepEqual(regions.map((item) => item.strokes.map((s) => s.id)), [['a', 'b'], ['c']]);
  assert.deepEqual(segmentPageInk(ink), regions);
});

test('a full page of twenty handwritten lines keeps all regions in visual order', () => {
  const ink = Array.from({ length: 20 }, (_, line) => [
    stroke(`line-${line}-left`, 0.1, 0.03 + line * 0.043),
    stroke(`line-${line}-right`, 0.55, 0.034 + line * 0.043),
  ]).flat();
  const regions = segmentPageInk(ink);
  assert.equal(regions.length, 20);
  assert.deepEqual(regions.map((item) => item.strokes.length), Array(20).fill(2));
  assert.deepEqual(new Set(regions.flatMap((item) => item.strokes.map((s) => s.id))).size, 40);
  assert.ok(regions.every((item, index) => index === 0 || item.bounds.top > regions[index - 1].bounds.top));
});

test('merge and split preserve every stroke and its page order', () => {
  const ink = [stroke('first', 0.1, 0.1), stroke('second', 0.3, 0.15), stroke('third', 0.1, 0.4)];
  const segmented = segmentPageInk(ink);
  const merged = mergePageOcrRegions(segmented, 0, ink);
  assert.deepEqual(merged[0].strokes.map((s) => s.id), ['first', 'second']);
  const restored = splitPageOcrRegion(merged, 0, 0.14);
  assert.deepEqual(restored.flatMap((item) => item.strokes.map((s) => s.id)), ['first', 'second', 'third']);
  assert.equal(splitPageOcrRegion(merged, 0, 0), merged);
});
