import test from "node:test";
import assert from "node:assert/strict";
import type { InkStroke } from "../src/lib/api/contracts.js";
import { proposeIntegralExpressionUnits } from "../src/features/math-workspace/utils/expression-reconstruction.js";

function stroke(id: string, pairs: [number, number][], tool: InkStroke["tool"] = "PEN"): InkStroke {
  return {
    id, tool, color: "#0f172a", width: 2,
    points: pairs.map(([x, y]) => ({ x, y, pressure: 0.5 })),
  };
}

function line(id: string, x: number, y: number, w: number, h: number): InkStroke {
  return stroke(id, [[x, y], [x + w / 2, y + h / 3], [x + w, y + h]]);
}

function realLikeIntegral(): InkStroke[] {
  const integral = stroke("integral", [
    [0.329, 0.150], [0.312, 0.147], [0.287, 0.180], [0.275, 0.205],
    [0.287, 0.250], [0.288, 0.280], [0.266, 0.302], [0.235, 0.295],
  ]);
  return [
    integral,
    line("lower-1", 0.245, 0.345, 0.047, 0.042),
    line("upper-2", 0.331, 0.074, 0.027, 0.033),
    line("expression", 0.351, 0.259, 0.094, 0.075),
    line("eq-top", 0.447, 0.268, 0.051, 0.002),
    line("eq-bottom", 0.441, 0.290, 0.062, 0.003),
    line("digit", 0.523, 0.218, 0.055, 0.075),
    line("digit2", 0.597, 0.224, 0.052, 0.060),
    line("suffix1", 0.669, 0.260, 0.023, 0.011),
    line("suffix2", 0.706, 0.259, 0.036, 0.020),
  ];
}

test("Integral expression: four fragmented source regions can share one 10-stroke proposal", () => {
  const original = realLikeIntegral();
  const snapshot = JSON.stringify(original);
  const units = proposeIntegralExpressionUnits(original);
  assert.equal(units.length, 1);
  const unit = units[0];
  assert.equal(unit.kind, "INTEGRAL");
  assert.equal(unit.integralStrokeId, "integral");
  assert.deepEqual(unit.upperLimitStrokeIds, ["upper-2"]);
  assert.deepEqual(unit.lowerLimitStrokeIds, ["lower-1"]);
  assert.deepEqual(new Set(unit.bodyStrokeIds),
    new Set(["expression", "eq-top", "eq-bottom", "digit", "digit2", "suffix1", "suffix2"]));
  assert.equal(new Set(unit.sourceStrokeIds).size, 10);
  assert.equal(JSON.stringify(original), snapshot, "input must remain unchanged");
});

test("Temporal invariance: drawing integral limits after body retains stroke membership", () => {
  const input = realLikeIntegral();
  const a = proposeIntegralExpressionUnits(input);
  const b = proposeIntegralExpressionUnits([...input].reverse());
  assert.equal(a.length, 1);
  assert.equal(b.length, 1);
  assert.deepEqual(new Set(a[0].sourceStrokeIds), new Set(b[0].sourceStrokeIds));
});

test("Negative: a curly brace with co-located endpoints is not an integral", () => {
  const brace = stroke("brace", [
    [0.110, 0.150], [0.092, 0.170], [0.085, 0.195], [0.110, 0.225],
    [0.085, 0.255], [0.092, 0.280], [0.110, 0.300], [0.110, 0.301],
  ]);
  const other = realLikeIntegral().slice(1);
  assert.equal(proposeIntegralExpressionUnits([brace, ...other]).length, 0);
});

test("Negative: tall sign without a two-sided limit and right-hand body is not forced", () => {
  const [sign, , upper] = realLikeIntegral();
  assert.deepEqual(proposeIntegralExpressionUnits([sign, upper, line("far", 0.8, 0.25, 0.06, 0.04)]), []);
});

test("Negative: an unrelated distant second column is not swallowed into an integral", () => {
  const input = realLikeIntegral();
  const separate = line("second-column", 0.90, 0.25, 0.05, 0.03);
  const units = proposeIntegralExpressionUnits([...input, separate]);
  assert.equal(units.length, 1);
  assert.ok(!units[0].sourceStrokeIds.includes("second-column"));
});

test("Highlighters are never part of expression proposals", () => {
  const input = realLikeIntegral();
  const highlight = line("marker", 0.48, 0.24, 0.05, 0.01);
  highlight.tool = "HIGHLIGHTER";
  const units = proposeIntegralExpressionUnits([...input, highlight]);
  assert.equal(units.length, 1);
  assert.ok(!units[0].sourceStrokeIds.includes("marker"));
});
