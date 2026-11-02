import test from "node:test";
import assert from "node:assert/strict";
import type { InkStroke } from "../src/lib/api/contracts.js";
import { segmentPageInk_v2 } from "../src/features/math-workspace/utils/page-ocr.js";
import {
  computeBounds,
  buildStructuredTranscriptionIR,
  applyOcrToContentUnit,
  editContentUnit,
  approveContentUnit,
  projectTranscriptionToLegacySteps,
  validateSolutionTranscriptionIR,
} from "../src/features/math-workspace/utils/structured-transcription-ir.js";

function makeStroke(id: string, x: number, y: number, w = 0.15, h = 0.02): InkStroke {
  return {
    id,
    tool: "PEN",
    color: "#000000",
    width: 2,
    points: [
      { x, y, pressure: 0.5 },
      { x: x + w * 0.5, y: y + h * 0.5, pressure: 0.5 },
      { x: x + w, y: y + h, pressure: 0.5 },
    ],
  };
}

// ============================================================================
// 1. P0.1 — Bounding Box Geometry Tests
// ============================================================================

test("P0.1 — Bounding box: stroke with X > Y computes correct right boundary", () => {
  // Stroke where X (0.75 - 0.90) is much larger than Y (0.05 - 0.10)
  const stroke = makeStroke("large_x", 0.75, 0.05, 0.15, 0.05);
  const bounds = computeBounds([stroke]);

  assert.equal(bounds.left, 0.75);
  assert.equal(bounds.right, 0.90, "bounds.right must be 0.90, not distorted by small Y!");
  assert.equal(bounds.top, 0.05);
  assert.equal(bounds.bottom, 0.10);
  assert.ok(bounds.left <= bounds.right);
  assert.ok(bounds.top <= bounds.bottom);
});

test("P0.1 — Bounding box: asymmetric strokes (wide vs tall) across A4 quadrants", () => {
  // Wide horizontal stroke at bottom right: x in [0.60, 0.95], y in [0.80, 0.82]
  const wideStroke = makeStroke("wide", 0.60, 0.80, 0.35, 0.02);
  const wideBounds = computeBounds([wideStroke]);
  assert.equal(wideBounds.left, 0.60);
  assert.equal(wideBounds.right, 0.95);
  assert.equal(wideBounds.top, 0.80);
  assert.ok(Math.abs(wideBounds.bottom - 0.82) < 1e-5);

  // Tall vertical stroke at top left: x in [0.08, 0.10], y in [0.05, 0.45]
  const tallStroke = makeStroke("tall", 0.08, 0.05, 0.02, 0.40);
  const tallBounds = computeBounds([tallStroke]);
  assert.equal(tallBounds.left, 0.08);
  assert.equal(tallBounds.right, 0.10);
  assert.equal(tallBounds.top, 0.05);
  assert.equal(tallBounds.bottom, 0.45);
});

// ============================================================================
// 2. P0.2 — Source Conservation Tests
// ============================================================================

test("P0.2 — Source conservation: all pen strokes represented even if omitted by segmentation", () => {
  const s1 = makeStroke("s1", 0.1, 0.1);
  const s2 = makeStroke("s2", 0.1, 0.2);
  const orphanStroke = makeStroke("orphan_isolated", 0.85, 0.85);

  // Simulate a segmentation that completely omitted 'orphan_isolated'
  const mockRegions = [
    { id: "reg-1", strokes: [s1], bounds: computeBounds([s1]) },
    { id: "reg-2", strokes: [s2], bounds: computeBounds([s2]) },
  ];

  const ir = buildStructuredTranscriptionIR({
    pageIndex: 0,
    strokes: [s1, s2, orphanStroke],
    regions: mockRegions,
  });

  const allAssignedIds = ir.contentUnits.flatMap((u) => u.sourceStrokeIds);
  assert.equal(allAssignedIds.includes("orphan_isolated"), true, "Orphan stroke must be captured in IR!");
  assert.equal(new Set(allAssignedIds).size, 3);
  assert.equal(ir.rawStrokeCount, 3);

  const orphanUnit = ir.contentUnits.find((u) => u.sourceStrokeIds.includes("orphan_isolated"));
  assert.ok(orphanUnit);
  assert.equal(orphanUnit.kind, "UNKNOWN");
  assert.equal(orphanUnit.recognitionStatus, "UNRESOLVED");
});

// ============================================================================
// 3. P0.3 — Projection Safety & Blocked States Tests
// ============================================================================

test("P0.3 — Projection safety: unapproved or UNRESOLVED units block projection without fake placeholders", () => {
  const strokes = [makeStroke("s1", 0.1, 0.1), makeStroke("s2", 0.1, 0.2)];
  const regions = segmentPageInk_v2(strokes);
  let ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions });

  // Unit 1 is approved with math
  ir = applyOcrToContentUnit(ir, ir.contentUnits[0].id, "y = x^2");
  ir = approveContentUnit(ir, ir.contentUnits[0].id);

  // Unit 2 is left UNRESOLVED / unapproved
  const projection = projectTranscriptionToLegacySteps(ir);

  // Projection must be BLOCKED because unit 2 is unapproved!
  assert.equal(projection.isProjectionBlocked, true);
  assert.equal(projection.blockedUnits.length, 1);
  assert.equal(projection.blockedUnits[0].unitId, ir.contentUnits[1].id);
  assert.ok(projection.blockedUnits[0].reason.includes("not APPROVED"));

  // Only approved unit 1 is emitted in steps; no fake '(UNKNOWN content unit)' placeholder
  assert.equal(projection.projectedStepCount, 1);
  assert.equal(projection.steps[0].content_latex, "y = x^2");
  assert.ok(!JSON.stringify(projection).includes("(UNKNOWN content unit)"));
});

test("P0.3 — Projection safety: unit of kind UNKNOWN blocks projection with clear warnings", () => {
  const strokes = [makeStroke("s1", 0.1, 0.1)];
  const regions = segmentPageInk_v2(strokes);
  let ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions });
  const unitId = ir.contentUnits[0].id;

  ir = editContentUnit(ir, unitId, { content: "Ambiguous blob", kind: "UNKNOWN" });
  ir = approveContentUnit(ir, unitId);

  const projection = projectTranscriptionToLegacySteps(ir);
  assert.equal(projection.isProjectionBlocked, true);
  assert.equal(projection.blockedUnits.length, 1);
  assert.equal(projection.blockedUnits[0].kind, "UNKNOWN");
  assert.ok(projection.blockedUnits[0].reason.includes("UNKNOWN"));
  assert.equal(projection.projectedStepCount, 0, "UNKNOWN unit must NOT be projected into legacy step");
});

// ============================================================================
// 4. P0.4 — Approval Consistency & Parent-Child Tests
// ============================================================================

test("P0.4 — Approval consistency: parent SYSTEM cannot be approved if a child is unapproved", () => {
  const strokes = [makeStroke("p1", 0.1, 0.1), makeStroke("p2", 0.1, 0.2)];
  const regions = segmentPageInk_v2(strokes);
  const cand = {
    id: "system-1",
    kind: "SYSTEM" as const,
    sourceStrokeIds: ["p1", "p2"],
    bounds: { left: 0.1, top: 0.1, right: 0.3, bottom: 0.3 },
    children: [
      { id: "eq1", kind: "INDEPENDENT" as const, sourceStrokeIds: ["p1"], bounds: { left: 0.1, top: 0.1, right: 0.3, bottom: 0.15 }, children: [], reasons: [] },
      { id: "eq2", kind: "INDEPENDENT" as const, sourceStrokeIds: ["p2"], bounds: { left: 0.1, top: 0.2, right: 0.3, bottom: 0.25 }, children: [], reasons: [] },
    ],
    reasons: [],
  };

  let ir = buildStructuredTranscriptionIR({
    pageIndex: 0,
    strokes,
    regions,
    structuralCandidates: [cand],
  });

  const parentUnit = ir.contentUnits.find((u) => u.id === "system-1")!;
  const child1 = ir.contentUnits.find((u) => u.id === "sub-eq1")!;
  const child2 = ir.contentUnits.find((u) => u.id === "sub-eq2")!;

  // Apply OCR to both children
  ir = applyOcrToContentUnit(ir, child1.id, "x + y = 1");
  ir = applyOcrToContentUnit(ir, child2.id, "x - y = 0");

  // Approve ONLY child 1
  ir = approveContentUnit(ir, child1.id);
  assert.equal(ir.contentUnits.find((u) => u.id === child1.id)!.reviewStatus, "APPROVED");
  assert.equal(ir.contentUnits.find((u) => u.id === child2.id)!.reviewStatus, "NEEDS_REVIEW");

  // Attempting to approve parent while child 2 is unapproved MUST throw!
  assert.throws(
    () => approveContentUnit(ir, parentUnit.id),
    /TRANSCRIPTION_PARENT_CHILDREN_UNAPPROVED/,
  );

  // Overall IR reviewStatus must remain NEEDS_REVIEW
  assert.equal(ir.reviewStatus, "NEEDS_REVIEW");

  // Now approve child 2
  ir = approveContentUnit(ir, child2.id);
  assert.equal(ir.contentUnits.find((u) => u.id === child2.id)!.reviewStatus, "APPROVED");

  // Now parent approval succeeds!
  ir = approveContentUnit(ir, parentUnit.id);
  assert.equal(ir.contentUnits.find((u) => u.id === parentUnit.id)!.reviewStatus, "APPROVED");
  assert.equal(ir.reviewStatus, "APPROVED");
});

// ============================================================================
// 5. P0.5 — Comprehensive Validation Tests
// ============================================================================

test("P0.5 — Validation: rejects duplicate unit IDs, malformed bounds, and invalid child references", () => {
  const validStrokes = [makeStroke("s1", 0.1, 0.1)];
  const validRegions = segmentPageInk_v2(validStrokes);
  const ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes: validStrokes, regions: validRegions });

  // Valid IR passes
  assert.doesNotThrow(() => validateSolutionTranscriptionIR(ir));

  // Reject duplicate unit ID
  const dupIr = {
    ...ir,
    contentUnits: [
      ir.contentUnits[0],
      { ...ir.contentUnits[0] },
    ],
  };
  assert.throws(() => validateSolutionTranscriptionIR(dupIr), /DUPLICATE_UNIT_ID/);

  // Reject inverted bounds (left > right)
  const invertedBoundsIr = {
    ...ir,
    contentUnits: [
      {
        ...ir.contentUnits[0],
        bounds: { left: 0.9, right: 0.1, top: 0.1, bottom: 0.2 },
      },
    ],
  };
  assert.throws(() => validateSolutionTranscriptionIR(invertedBoundsIr), /MALFORMED_UNIT_BOUNDS/);

  // Reject child referencing non-existent child ID
  const brokenChildIr = {
    ...ir,
    contentUnits: [
      {
        ...ir.contentUnits[0],
        childIds: ["missing-child-999"],
      },
    ],
  };
  assert.throws(() => validateSolutionTranscriptionIR(brokenChildIr), /MISSING_CHILD_UNIT/);

  // Reject approved unit with empty content
  const emptyApprovedIr = {
    ...ir,
    contentUnits: [
      {
        ...ir.contentUnits[0],
        reviewStatus: "APPROVED" as const,
        approvedContent: "   ",
      },
    ],
  };
  assert.throws(() => validateSolutionTranscriptionIR(emptyApprovedIr), /APPROVED_UNIT_EMPTY_CONTENT/);
});

// ============================================================================
// 6. Invariant 4 & 5 (Manual Correction & Faithful Math Mistake)
// ============================================================================

test("Invariant 4: Re-running recognition NEVER overwrites student manual corrections", () => {
  const strokes = [makeStroke("s1", 0.1, 0.1)];
  const regions = segmentPageInk_v2(strokes);
  let ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions });
  const unitId = ir.contentUnits[0].id;

  ir = applyOcrToContentUnit(ir, unitId, "x = 1");
  ir = editContentUnit(ir, unitId, { content: "x = 2" });
  assert.equal(ir.contentUnits[0].approvedContent, "x = 2");

  // Re-run OCR
  ir = applyOcrToContentUnit(ir, unitId, "x = 3");
  assert.equal(ir.contentUnits[0].approvedContent, "x = 2", "Manual edit must be preserved!");
  assert.equal(ir.contentUnits[0].recognitionStatus, "MANUALLY_CORRECTED");
});

test("Invariant 5: Student mathematical mistake transcribed faithfully without SymPy auto-correction", () => {
  const strokes = [makeStroke("s1", 0.1, 0.1)];
  const regions = segmentPageInk_v2(strokes);
  let ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions });
  const unitId = ir.contentUnits[0].id;

  const wrongMath = "3x^2 - 3 = 0 \\Leftrightarrow x = 2";
  ir = editContentUnit(ir, unitId, { content: wrongMath });
  ir = approveContentUnit(ir, unitId);

  const projection = projectTranscriptionToLegacySteps(ir);
  assert.equal(projection.steps[0].content_latex, wrongMath);
  assert.ok(!projection.steps[0].content_latex?.includes("\\pm 1"));
});

// ============================================================================
// 7. Multi-line Calculus Solution Scenario (Grade 12 Demo)
// ============================================================================

test("Grade 12 Calculus Demo: 4-line solution transcription, human review, and projection", () => {
  const line1 = makeStroke("l1_txt", 0.1, 0.10);
  const line2 = makeStroke("l2_der", 0.1, 0.18);
  const line3 = makeStroke("l3_root", 0.1, 0.26);
  const line4 = makeStroke("l4_ext", 0.1, 0.34);

  const strokes = [line1, line2, line3, line4];
  const regions = segmentPageInk_v2(strokes);

  let ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions });
  assert.equal(ir.contentUnits.length, 4);

  const [u1, u2, u3, u4] = ir.contentUnits;
  ir = applyOcrToContentUnit(ir, u1.id, "Tập xác định: D = R");
  ir = editContentUnit(ir, u1.id, { kind: "TEXT" });

  ir = applyOcrToContentUnit(ir, u2.id, "y' = 3x^2 - 3");
  ir = applyOcrToContentUnit(ir, u3.id, "y' = 0 \\Leftrightarrow x = \\pm 1");
  ir = applyOcrToContentUnit(ir, u4.id, "y(1) = -1,\\quad y(-1) = 3");

  // Approve all units
  ir = approveContentUnit(ir, u1.id);
  ir = approveContentUnit(ir, u2.id);
  ir = approveContentUnit(ir, u3.id);
  ir = approveContentUnit(ir, u4.id);
  assert.equal(ir.reviewStatus, "APPROVED");

  const projection = projectTranscriptionToLegacySteps(ir);
  assert.equal(projection.isProjectionBlocked, false);
  assert.equal(projection.blockedUnits.length, 0);
  assert.equal(projection.projectedStepCount, 4);

  assert.equal(projection.steps[0].step_type, "EXPLANATION");
  assert.equal(projection.steps[0].explanation_text, "Tập xác định: D = R");
  assert.equal(projection.steps[1].step_type, "DERIVATIVE_CALCULATION");
  assert.equal(projection.steps[1].content_latex, "y' = 3x^2 - 3");
  assert.equal(projection.steps[2].step_type, "ROOT_FINDING");
  assert.equal(projection.steps[2].content_latex, "y' = 0 \\Leftrightarrow x = \\pm 1");
});
