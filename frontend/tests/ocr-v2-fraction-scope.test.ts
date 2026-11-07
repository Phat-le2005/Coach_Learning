import test from "node:test";
import assert from "node:assert/strict";
import type { InkStroke } from "../src/lib/api/contracts";
import { constructScopeCandidates } from "../src/features/math-workspace/utils/ocr-v2-scope-candidates";
import { renderTransform, scopeIntegrity, type LabSource } from "../src/features/math-workspace/utils/ocr-v2-experimental";

// Geometry software controls only. Real-ink before/after evidence is kept separately.
const mark = (id: string, points: number[][]): InkStroke => ({ id, tool: "PEN", color: "#000", width: 2,
  points: points.map(([x, y]) => ({ x: x / 794, y: y / 1123, pressure: .5 })) });
const source = (strokes: InkStroke[]): LabSource => ({ strokes, pageIndex: 0, sourceRevision: 1,
  sourceKind: "SYNTHETIC_INK", datasetSplit: "DEV", consent: false });
const run = (s: LabSource) => constructScopeCandidates(s, { status: "GEOMETRY_ONLY", model: "NONE", regions: [] }, renderTransform(), "GEOMETRY");
const numerator = mark("numerator", [[120, 100], [136, 125], [150, 100]]);
const denominator = mark("denominator", [[120, 180], [136, 205], [150, 180]]);
const sloped = mark("rule", [[90, 140], [180, 148], [270, 156]]);

test("sloped fraction rule retains both sides, physical IDs and immutable source", () => {
  const s = source([numerator, sloped, denominator]), before = JSON.stringify(s), result = run(s);
  assert.ok(result.scopes.some(scope => scope.kind === "MATH" && s.strokes.every(st => scope.strokeIds.includes(st.id))));
  assert.ok(result.trace.some(row => (row as { stage: string }).stage === "SLOPED_FRACTION_RULE"));
  assert.deepEqual(scopeIntegrity(s, result.scopes).missing, []);
  assert.deepEqual(scopeIntegrity(s, result.scopes).duplicateOwnership, []);
  assert.equal(JSON.stringify(s), before);
});

test("fraction rule evidence survives reverse drawing and uniform scale", () => {
  for (const scale of [.75, 1.5]) {
    const strokes = [numerator, sloped, denominator].map(st => ({ ...st, points: [...st.points].reverse().map(p => ({ ...p, x: p.x * scale, y: p.y * scale })) }));
    const result = run(source(strokes));
    assert.ok(result.scopes.some(scope => strokes.every(st => scope.strokeIds.includes(st.id))));
  }
});

test("sloped separator cannot merge two independently anchored equations", () => {
  const equation = (prefix: string, y: number) => [mark(prefix + "lhs", [[110, y], [120, y + 20], [130, y]]),
    mark(prefix + "eq1", [[155, y + 6], [175, y + 6]]), mark(prefix + "eq2", [[155, y + 14], [170, y + 14]]),
    mark(prefix + "rhs", [[210, y], [220, y + 20], [230, y]])];
  const s = source([...equation("a", 100), sloped, ...equation("b", 180)]), result = run(s);
  assert.ok(result.scopes.every(scope => !(scope.strokeIds.includes("alhs") && scope.strokeIds.includes("blhs"))));
  assert.ok(result.trace.some(row => (row as { reason?: string }).reason === "INDEPENDENT_EQUALITY_ROWS"));
  assert.deepEqual(scopeIntegrity(s, result.scopes).missing, []);
});

test("bent glyph and radical stem are not accepted as sloped fraction rules", () => {
  for (const points of [[[90, 140], [180, 170], [270, 156]], [[90, 140], [100, 160], [115, 135], [270, 151]]]) {
    const s = source([numerator, mark("curved", points), denominator]), result = run(s);
    assert.ok(!result.trace.some(row => { const r = row as { stage: string; ids?: string[] }; return r.stage === "SLOPED_FRACTION_RULE" && r.ids?.includes("curved"); }));
    assert.ok(!result.trace.some(row => { const r = row as { stage: string; bar?: string[] }; return r.stage === "FRACTION_SUPPORT" && r.bar?.includes("curved"); }));
    assert.deepEqual(scopeIntegrity(s, result.scopes).duplicateOwnership, []);
  }
});
