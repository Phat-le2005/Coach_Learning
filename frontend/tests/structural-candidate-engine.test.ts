import test from "node:test";
import assert from "node:assert/strict";
import type { InkStroke, InkPoint } from "../src/lib/api/contracts.js";
import {
  detectStructuralCandidates,
  classifyBracketGeometry,
  type StructureCandidate,
} from "../src/features/math-workspace/utils/structural-candidate-engine.js";
import { segmentPageInk_v2 } from "../src/features/math-workspace/utils/page-ocr.js";

// ============================================================================
// Helpers to generate realistic stroke geometry
// ============================================================================

function makeStroke(id: string, points: InkPoint[], tool: InkStroke["tool"] = "PEN"): InkStroke {
  return {
    id,
    tool,
    color: "#000000",
    width: 2,
    points,
  };
}

/** Horizontal line segment (e.g. text or equation line) */
function makeLineStroke(id: string, x: number, y: number, w = 0.18, h = 0.02): InkStroke {
  return makeStroke(id, [
    { x, y, pressure: 0.5 },
    { x: x + w * 0.5, y: y + h * 0.5, pressure: 0.5 },
    { x: x + w, y: y + h, pressure: 0.5 },
  ]);
}

/** Curly brace '{': has central cusp pointing left in the vertical middle third */
function makeCurlyBraceStroke(id: string, x = 0.08, yTop = 0.1, yBottom = 0.3): InkStroke {
  const yMid = (yTop + yBottom) / 2;
  return makeStroke(id, [
    { x: x + 0.03, y: yTop, pressure: 0.5 },              // Top tip curves right
    { x: x + 0.015, y: yTop + 0.04, pressure: 0.5 },
    { x: x, y: yMid, pressure: 0.6 },                     // Central cusp at minX!
    { x: x + 0.015, y: yBottom - 0.04, pressure: 0.5 },
    { x: x + 0.03, y: yBottom, pressure: 0.5 },           // Bottom tip curves right
  ]);
}

/** Square bracket '[': straight vertical spine with horizontal arms at top and bottom */
function makeSquareBracketStroke(id: string, x = 0.08, yTop = 0.1, yBottom = 0.3): InkStroke {
  const yMid = (yTop + yBottom) / 2;
  return makeStroke(id, [
    { x: x + 0.03, y: yTop, pressure: 0.5 },              // Top horizontal arm
    { x, y: yTop, pressure: 0.5 },
    { x, y: yMid, pressure: 0.5 },                        // Straight vertical spine
    { x, y: yBottom, pressure: 0.5 },
    { x: x + 0.03, y: yBottom, pressure: 0.5 },           // Bottom horizontal arm
  ]);
}

// ============================================================================
// 1. Unit Tests: Bracket Classification Geometry
// ============================================================================

test("classifyBracketGeometry: accurately classifies Curly brace '{' with central cusp", () => {
  const curly = makeCurlyBraceStroke("curly-1", 0.08, 0.1, 0.3);
  const result = classifyBracketGeometry(curly);
  assert.equal(result.type, "CURLY");
  assert.ok(result.heuristicScore >= 0.8);
  assert.ok(result.reasons.some((r) => r.includes("cusp")));
});

test("classifyBracketGeometry: accurately classifies Square bracket '[' with orthogonal arms", () => {
  const square = makeSquareBracketStroke("square-1", 0.08, 0.1, 0.3);
  const result = classifyBracketGeometry(square);
  assert.equal(result.type, "SQUARE");
  assert.ok(result.heuristicScore >= 0.8);
  assert.ok(result.reasons.some((r) => r.includes("spine") || r.includes("arms")));
});

test("classifyBracketGeometry: degenerate or straight single point returns UNKNOWN", () => {
  const degen = makeStroke("degen", [{ x: 0.1, y: 0.1, pressure: 0.5 }]);
  const result = classifyBracketGeometry(degen);
  assert.equal(result.type, "UNKNOWN");
  assert.equal(result.heuristicScore, 0);
});

// ============================================================================
// 2. Case A: System of Equations (SYSTEM)
// ============================================================================

test("Case A — SYSTEM: Curly brace enclosing two equations forms a parent SYSTEM candidate with children", () => {
  const brace = makeCurlyBraceStroke("brace_sys", 0.08, 0.1, 0.28);
  const eq1 = makeLineStroke("eq1", 0.13, 0.12, 0.2, 0.02);
  const eq2 = makeLineStroke("eq2", 0.13, 0.22, 0.2, 0.02);

  const strokes = [brace, eq1, eq2];
  const candidates = detectStructuralCandidates(strokes);

  assert.equal(candidates.length, 1);
  const sys = candidates[0];
  assert.equal(sys.kind, "SYSTEM");
  assert.ok(sys.sourceStrokeIds.includes("brace_sys"));
  assert.ok(sys.sourceStrokeIds.includes("eq1"));
  assert.ok(sys.sourceStrokeIds.includes("eq2"));

  // Must have 2 child candidates for the 2 enclosed equations
  assert.equal(sys.children.length, 2);
  assert.deepEqual(sys.children[0].sourceStrokeIds, ["eq1"]);
  assert.deepEqual(sys.children[1].sourceStrokeIds, ["eq2"]);
  assert.equal(sys.children[0].kind, "INDEPENDENT");
  assert.equal(sys.children[1].kind, "INDEPENDENT");
});

// ============================================================================
// 3. Case B: Solution Alternatives (ALTERNATIVES)
// ============================================================================

test("Case B — ALTERNATIVES: Square bracket enclosing two root branches forms an ALTERNATIVES candidate", () => {
  const bracket = makeSquareBracketStroke("bracket_alt", 0.08, 0.1, 0.28);
  const branch1 = makeLineStroke("x_eq_1", 0.13, 0.12, 0.15, 0.02);
  const branch2 = makeLineStroke("x_eq_2", 0.13, 0.22, 0.15, 0.02);

  const strokes = [bracket, branch1, branch2];
  const candidates = detectStructuralCandidates(strokes);

  assert.equal(candidates.length, 1);
  const alt = candidates[0];
  assert.equal(alt.kind, "ALTERNATIVES");
  assert.notEqual(alt.kind, "SYSTEM");
  assert.equal(alt.children.length, 2);
  assert.deepEqual(alt.children[0].sourceStrokeIds, ["x_eq_1"]);
  assert.deepEqual(alt.children[1].sourceStrokeIds, ["x_eq_2"]);
});

// ============================================================================
// 4. Case C: Fraction Structure (FRACTION)
// ============================================================================

test("Case C — FRACTION: Numerator, fraction bar, and denominator form a structured FRACTION candidate", () => {
  // Numerator: y = 0.12
  const num = makeStroke("num", [
    { x: 0.15, y: 0.12, pressure: 0.5 },
    { x: 0.20, y: 0.135, pressure: 0.5 },
  ]);
  // Fraction bar: y = 0.15, width = 0.12, height = 0.003
  const bar = makeStroke("bar", [
    { x: 0.12, y: 0.15, pressure: 0.5 },
    { x: 0.24, y: 0.15, pressure: 0.5 },
  ]);
  // Denominator: y = 0.17
  const den = makeStroke("den", [
    { x: 0.15, y: 0.17, pressure: 0.5 },
    { x: 0.20, y: 0.185, pressure: 0.5 },
  ]);

  const strokes = [num, bar, den];
  const candidates = detectStructuralCandidates(strokes);

  assert.equal(candidates.length, 1);
  const frac = candidates[0];
  assert.equal(frac.kind, "FRACTION");
  assert.equal(frac.children.length, 2);
  assert.deepEqual(frac.children[0].sourceStrokeIds, ["num"]);
  assert.deepEqual(frac.children[1].sourceStrokeIds, ["den"]);
});

// ============================================================================
// 5. Case D: Two Independent Lines (No False Merges)
// ============================================================================

test("Case D — INDEPENDENT: Two adjacent lines without enclosing delimiter remain two separate candidates", () => {
  const line1 = makeLineStroke("line1", 0.1, 0.1, 0.25, 0.02);
  const line2 = makeLineStroke("line2", 0.1, 0.18, 0.25, 0.02);

  const strokes = [line1, line2];
  const candidates = detectStructuralCandidates(strokes);

  // Must NOT merge into 1 single candidate!
  assert.equal(candidates.length, 2);
  assert.equal(candidates[0].kind, "INDEPENDENT");
  assert.equal(candidates[1].kind, "INDEPENDENT");
  assert.deepEqual(candidates[0].sourceStrokeIds, ["line1"]);
  assert.deepEqual(candidates[1].sourceStrokeIds, ["line2"]);
});

// ============================================================================
// 6. Case E: Drawing Sequence Invariance (Bracket Drawn AFTER Equations)
// ============================================================================

test("Case E — Temporal Invariance: Bracket drawn after equations produces identical structure to drawn first", () => {
  const eq1 = makeLineStroke("eq1", 0.13, 0.12, 0.2, 0.02);
  const eq2 = makeLineStroke("eq2", 0.13, 0.22, 0.2, 0.02);
  const braceAfter = makeCurlyBraceStroke("brace_late", 0.08, 0.1, 0.28);

  // Equation 1 drawn 1st, Equation 2 drawn 2nd, Brace drawn LAST (index 2)
  const strokesLate = [eq1, eq2, braceAfter];
  const candidatesLate = detectStructuralCandidates(strokesLate);

  assert.equal(candidatesLate.length, 1);
  assert.equal(candidatesLate[0].kind, "SYSTEM");
  assert.equal(candidatesLate[0].children.length, 2);
  assert.deepEqual(candidatesLate[0].children[0].sourceStrokeIds, ["eq1"]);
  assert.deepEqual(candidatesLate[0].children[1].sourceStrokeIds, ["eq2"]);

  // Contrast with Brace drawn FIRST (index 0)
  const braceEarly = makeCurlyBraceStroke("brace_early", 0.08, 0.1, 0.28);
  const strokesEarly = [braceEarly, eq1, eq2];
  const candidatesEarly = detectStructuralCandidates(strokesEarly);

  assert.equal(candidatesEarly.length, 1);
  assert.equal(candidatesEarly[0].kind, "SYSTEM");
  assert.equal(candidatesEarly[0].children.length, 2);
  assert.deepEqual(candidatesEarly[0].children.map((c) => c.sourceStrokeIds), candidatesLate[0].children.map((c) => c.sourceStrokeIds));
});

// ============================================================================
// 7. Negative Tests: Guards against False Positives
// ============================================================================

test("Negative: Minus sign '-' between two lines does NOT trigger fraction grouping", () => {
  const line1 = makeLineStroke("line1", 0.1, 0.1, 0.2, 0.02);
  // Short dash between lines
  const minus = makeStroke("minus", [
    { x: 0.15, y: 0.14, pressure: 0.5 },
    { x: 0.17, y: 0.14, pressure: 0.5 },
  ]);
  const line2 = makeLineStroke("line2", 0.1, 0.17, 0.2, 0.02);

  const strokes = [line1, minus, line2];
  const candidates = detectStructuralCandidates(strokes);

  // Minus must NOT cause a FRACTION with line1 as numerator and line2 as denominator!
  const hasFraction = candidates.some((c) => c.kind === "FRACTION");
  assert.equal(hasFraction, false, "Minus sign must not create a false FRACTION candidate");
});

test("Negative: Equals sign '=' does NOT trigger fraction grouping", () => {
  const eqTop = makeStroke("eq_t", [{ x: 0.1, y: 0.12, pressure: 0.5 }, { x: 0.15, y: 0.12, pressure: 0.5 }]);
  const eqBot = makeStroke("eq_b", [{ x: 0.1, y: 0.128, pressure: 0.5 }, { x: 0.15, y: 0.128, pressure: 0.5 }]);
  const other = makeLineStroke("other", 0.1, 0.2, 0.2, 0.02);

  const strokes = [eqTop, eqBot, other];
  const candidates = detectStructuralCandidates(strokes);

  const hasFraction = candidates.some((c) => c.kind === "FRACTION");
  assert.equal(hasFraction, false, "Equals sign must not trigger false FRACTION");
});

test("Negative: Small inline parenthesis does NOT trigger multi-line SYSTEM or ALTERNATIVES", () => {
  // Small parenthesis (x: 0.1 to 0.11, y: 0.1 to 0.125) inside a single line
  const paren = makeStroke("paren", [
    { x: 0.11, y: 0.1, pressure: 0.5 },
    { x: 0.1, y: 0.112, pressure: 0.5 },
    { x: 0.11, y: 0.125, pressure: 0.5 },
  ]);
  const varX = makeLineStroke("var_x", 0.12, 0.105, 0.05, 0.015);

  const strokes = [paren, varX];
  const candidates = detectStructuralCandidates(strokes);

  assert.equal(candidates.length, 1);
  assert.equal(candidates[0].kind, "INDEPENDENT");
  assert.notEqual(candidates[0].kind, "SYSTEM");
  assert.notEqual(candidates[0].kind, "ALTERNATIVES");
});

// ============================================================================
// 8. Metamorphic Tests: Translation and Scaling Invariance
// ============================================================================

test("Metamorphic: Translating coordinates (dx, dy) preserves structural kind and children hierarchy", () => {
  const brace = makeCurlyBraceStroke("brace", 0.08, 0.1, 0.28);
  const eq1 = makeLineStroke("eq1", 0.13, 0.12, 0.2, 0.02);
  const eq2 = makeLineStroke("eq2", 0.13, 0.22, 0.2, 0.02);

  const originalCandidates = detectStructuralCandidates([brace, eq1, eq2]);

  // Translate by dx = +0.2, dy = +0.15
  const dx = 0.2, dy = 0.15;
  const translateStroke = (s: InkStroke, newId: string): InkStroke => ({
    ...s,
    id: newId,
    points: s.points.map((p) => ({ ...p, x: p.x + dx, y: p.y + dy })),
  });

  const translatedStrokes = [
    translateStroke(brace, "brace_t"),
    translateStroke(eq1, "eq1_t"),
    translateStroke(eq2, "eq2_t"),
  ];

  const translatedCandidates = detectStructuralCandidates(translatedStrokes);
  assert.equal(translatedCandidates.length, originalCandidates.length);
  assert.equal(translatedCandidates[0].kind, originalCandidates[0].kind);
  assert.equal(translatedCandidates[0].children.length, originalCandidates[0].children.length);
});

// ============================================================================
// 9. Baseline Comparison: segmentPageInk_v2 vs detectStructuralCandidates
// ============================================================================

test("Baseline Comparison: structural candidate engine preserves 100% stroke provenance while adding hierarchy", () => {
  const brace = makeCurlyBraceStroke("b", 0.08, 0.1, 0.28);
  const eq1 = makeLineStroke("e1", 0.13, 0.12, 0.2, 0.02);
  const eq2 = makeLineStroke("e2", 0.13, 0.22, 0.2, 0.02);
  const line3 = makeLineStroke("e3", 0.08, 0.35, 0.3, 0.02);

  const allStrokes = [brace, eq1, eq2, line3];

  // Flat segmentation v2 baseline
  const flatRegions = segmentPageInk_v2(allStrokes);
  const flatStrokeIds = new Set(flatRegions.flatMap((r) => r.strokes.map((s) => s.id)));
  assert.equal(flatStrokeIds.size, 4, "v2 segmentation covers all 4 strokes");

  // Structural recognition prototype
  const structCandidates = detectStructuralCandidates(allStrokes);
  const structStrokeIds = new Set(structCandidates.flatMap((c) => c.sourceStrokeIds));
  assert.equal(structStrokeIds.size, 4, "StructureCandidate engine covers all 4 strokes without dropping any");

  // Unlike flat v2 which outputs 2 or 3 flat lines, structural engine represents:
  // Candidate 1: SYSTEM with 2 equation children
  // Candidate 2: INDEPENDENT for line 3
  assert.equal(structCandidates.length, 2);
  assert.equal(structCandidates[0].kind, "SYSTEM");
  assert.equal(structCandidates[0].children.length, 2);
  assert.equal(structCandidates[1].kind, "INDEPENDENT");
});


test("Regular left curly brace with a right-facing middle cusp is classified as CURLY", () => {
  const brace = makeStroke("regular-curly", [
    { x: 0.11, y: 0.10, pressure: 0.5 },
    { x: 0.08, y: 0.13, pressure: 0.5 },
    { x: 0.11, y: 0.19, pressure: 0.5 },
    { x: 0.08, y: 0.24, pressure: 0.5 },
    { x: 0.11, y: 0.28, pressure: 0.5 },
  ]);
  const classification = classifyBracketGeometry(brace);
  assert.equal(classification.type, "CURLY");
  assert.ok(classification.reasons.some((r) => r.includes("rightward cusp")));
});

test("Negative: a brace may not swallow independent equations in a second column", () => {
  const brace = makeCurlyBraceStroke("brace", 0.08, 0.10, 0.28);
  const left1 = makeLineStroke("left1", 0.13, 0.12, 0.20, 0.02);
  const left2 = makeLineStroke("left2", 0.13, 0.22, 0.20, 0.02);
  const right1 = makeLineStroke("right1", 0.62, 0.12, 0.17, 0.02);
  const right2 = makeLineStroke("right2", 0.62, 0.22, 0.17, 0.02);

  const candidates = detectStructuralCandidates([brace, left1, right1, left2, right2]);
  const system = candidates.find((candidate) => candidate.kind === "SYSTEM");
  assert.ok(system);
  assert.deepEqual(new Set(system.sourceStrokeIds), new Set(["brace", "left1", "left2"]));
  assert.equal(system.children.length, 2);
  assert.equal(candidates.filter((c) => c.sourceStrokeIds.includes("right1")).length, 1);
  assert.equal(candidates.filter((c) => c.sourceStrokeIds.includes("right2")).length, 1);
});

test("A fraction parent never includes an unrelated inline suffix even if segmentation groups it", () => {
  const num = makeStroke("num", [
    { x: 0.15, y: 0.12, pressure: 0.5 },
    { x: 0.20, y: 0.135, pressure: 0.5 },
  ]);
  const bar = makeStroke("bar", [
    { x: 0.12, y: 0.15, pressure: 0.5 },
    { x: 0.24, y: 0.15, pressure: 0.5 },
  ]);
  const den = makeStroke("den", [
    { x: 0.15, y: 0.17, pressure: 0.5 },
    { x: 0.20, y: 0.185, pressure: 0.5 },
  ]);
  const suffix = makeLineStroke("suffix", 0.25, 0.15, 0.05, 0.012);

  const candidates = detectStructuralCandidates([num, bar, den, suffix]);
  const fraction = candidates.find((candidate) => candidate.kind === "FRACTION");
  assert.ok(fraction, "Expected an isolated structured fraction");
  assert.deepEqual(new Set(fraction.sourceStrokeIds), new Set(["num", "bar", "den"]));
  assert.ok(!fraction.sourceStrokeIds.includes("suffix"));
  assert.ok(candidates.some((candidate) =>
    candidate.kind === "INDEPENDENT" && candidate.sourceStrokeIds.includes("suffix")));
});
