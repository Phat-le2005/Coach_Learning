import test from "node:test";
import assert from "node:assert/strict";
import type { InkStroke } from "../src/lib/api/contracts.js";
import { segmentPageInk_v2 } from "../src/features/math-workspace/utils/page-ocr.js";
import {
  buildStructuredTranscriptionIR,
  applyOcrToContentUnit,
  editContentUnit,
  approveContentUnit,
  projectTranscriptionToLegacySteps,
  validateSolutionTranscriptionIR,
} from "../src/features/math-workspace/utils/structured-transcription-ir.js";
import { StepKind } from "../src/lib/api/contracts.js";

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
// 1. Data Invariants Tests
// ============================================================================

test("Invariant 1: Zero dropped strokes (100% stroke coverage preserved)", () => {
  const strokes = [
    makeStroke("s1", 0.1, 0.1),
    makeStroke("s2", 0.1, 0.2),
    makeStroke("s3", 0.1, 0.3),
  ];
  const regions = segmentPageInk_v2(strokes);
  const ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions });

  const assignedStrokeIds = ir.contentUnits.flatMap((u) => u.sourceStrokeIds);
  assert.equal(new Set(assignedStrokeIds).size, 3);
  assert.equal(ir.rawStrokeCount, 3);
});

test("Invariant 2: Strict reading order preservation", () => {
  // Line 1 (y=0.10), Line 2 (y=0.20), Line 3 (y=0.30)
  const strokes = [
    makeStroke("line3", 0.1, 0.30),
    makeStroke("line1", 0.1, 0.10),
    makeStroke("line2", 0.1, 0.20),
  ];
  const regions = segmentPageInk_v2(strokes);
  const ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions });

  assert.equal(ir.contentUnits.length, 3);
  // Reading order must be sorted top-to-bottom
  assert.equal(ir.contentUnits[0].readingOrder, 0);
  assert.equal(ir.contentUnits[1].readingOrder, 1);
  assert.equal(ir.contentUnits[2].readingOrder, 2);
  assert.deepEqual(ir.contentUnits[0].sourceStrokeIds, ["line1"]);
  assert.deepEqual(ir.contentUnits[1].sourceStrokeIds, ["line2"]);
  assert.deepEqual(ir.contentUnits[2].sourceStrokeIds, ["line3"]);
});

test("Invariant 3: Parent and child reference same strokes without physical duplication", () => {
  const strokes = [makeStroke("p1", 0.1, 0.1), makeStroke("p2", 0.1, 0.2)];
  const regions = segmentPageInk_v2(strokes);
  const cand = {
    id: "parent-group",
    kind: "SYSTEM" as const,
    sourceStrokeIds: ["p1", "p2"],
    bounds: { left: 0.1, top: 0.1, right: 0.3, bottom: 0.3 },
    children: [
      {
        id: "c1",
        kind: "INDEPENDENT" as const,
        sourceStrokeIds: ["p1"],
        bounds: { left: 0.1, top: 0.1, right: 0.3, bottom: 0.15 },
        children: [],
        reasons: [],
      },
    ],
    reasons: [],
  };

  const ir = buildStructuredTranscriptionIR({
    pageIndex: 0,
    strokes,
    regions,
    structuralCandidates: [cand],
  });

  const parent = ir.contentUnits.find((u) => u.id === "parent-group");
  const child = ir.contentUnits.find((u) => u.id === "sub-c1");
  assert.ok(parent);
  assert.ok(child);
  assert.deepEqual(parent.childIds, ["sub-c1"]);
  // Parent references p1 and p2; child references p1.
  assert.ok(parent.sourceStrokeIds.includes("p1"));
  assert.ok(child.sourceStrokeIds.includes("p1"));
  assert.equal(ir.rawStrokeCount, 2, "Physical stroke count must remain 2");
});

test("Invariant 4: Re-running recognition NEVER overwrites student's manual corrections", () => {
  const strokes = [makeStroke("s1", 0.1, 0.1)];
  const regions = segmentPageInk_v2(strokes);
  let ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions });
  const unitId = ir.contentUnits[0].id;

  // Initial OCR
  ir = applyOcrToContentUnit(ir, unitId, "x = 1");
  assert.equal(ir.contentUnits[0].rawRecognition, "x = 1");

  // Student manual edit
  ir = editContentUnit(ir, unitId, { content: "x = 2" });
  assert.equal(ir.contentUnits[0].approvedContent, "x = 2");
  assert.equal(ir.contentUnits[0].isManuallyCorrected, true);
  assert.equal(ir.contentUnits[0].recognitionStatus, "MANUALLY_CORRECTED");

  // Re-run OCR with a different guess
  ir = applyOcrToContentUnit(ir, unitId, "x = 3");
  assert.equal(ir.contentUnits[0].rawRecognition, "x = 3");
  assert.equal(ir.contentUnits[0].approvedContent, "x = 2", "Student correction must be preserved!");
  assert.equal(ir.contentUnits[0].recognitionStatus, "MANUALLY_CORRECTED");
});

test("Invariant 5: Student mathematical mistake creates valid IR without silent auto-correction", () => {
  const strokes = [makeStroke("s1", 0.1, 0.1)];
  const regions = segmentPageInk_v2(strokes);
  let ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions });
  const unitId = ir.contentUnits[0].id;

  // Student wrote a mathematical mistake: 3x^2 - 3 = 0 <=> x = 2
  const wrongMath = "3x^2 - 3 = 0 \\Leftrightarrow x = 2";
  ir = editContentUnit(ir, unitId, { content: wrongMath });
  ir = approveContentUnit(ir, unitId);

  assert.equal(ir.contentUnits[0].approvedContent, wrongMath);
  assert.equal(ir.contentUnits[0].reviewStatus, "APPROVED");

  // Project to legacy step
  const projection = projectTranscriptionToLegacySteps(ir);
  assert.equal(projection.steps[0].content_latex, wrongMath);
  // Faithful transcription: OCR did not rewrite to x = \pm 1!
  assert.ok(!projection.steps[0].content_latex.includes("\\pm 1"));
});

test("Invariant 6: Ambiguous/unrecognized unit has status UNRESOLVED or UNKNOWN", () => {
  const strokes = [makeStroke("s1", 0.1, 0.1)];
  const regions = segmentPageInk_v2(strokes);
  const ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions });

  assert.equal(ir.contentUnits[0].recognitionStatus, "UNRESOLVED");
  assert.equal(ir.contentUnits[0].rawRecognition, null);
  assert.equal(ir.contentUnits[0].reviewStatus, "NEEDS_REVIEW");
});

test("Invariant 7: Approval is invalidated whenever content is edited", () => {
  const strokes = [makeStroke("s1", 0.1, 0.1)];
  const regions = segmentPageInk_v2(strokes);
  let ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions });
  const unitId = ir.contentUnits[0].id;

  ir = applyOcrToContentUnit(ir, unitId, "f(x) = x^2");
  ir = approveContentUnit(ir, unitId);
  assert.equal(ir.contentUnits[0].reviewStatus, "APPROVED");
  assert.equal(ir.reviewStatus, "APPROVED");

  // Now student edits the formula
  ir = editContentUnit(ir, unitId, { content: "f(x) = x^3" });
  assert.equal(ir.contentUnits[0].reviewStatus, "NEEDS_REVIEW", "Approval must be invalidated!");
  assert.equal(ir.reviewStatus, "NEEDS_REVIEW");
});

// ============================================================================
// 2. Multi-line Calculus / Function Study Scenario (Grade 12 Demo)
// ============================================================================

test("Grade 12 Calculus Demo: 4-line handwritten solution transcription and legacy projection", () => {
  // Line 1: "Tập xác định: D = R" (Text)
  // Line 2: "y' = 3x^2 - 3" (Derivative)
  // Line 3: "y' = 0 \Leftrightarrow x = \pm 1" (Root finding)
  // Line 4: "y(1) = -1, y(-1) = 3" (Extrema values)
  const line1 = makeStroke("l1_txt", 0.1, 0.10);
  const line2 = makeStroke("l2_der", 0.1, 0.18);
  const line3 = makeStroke("l3_root", 0.1, 0.26);
  const line4 = makeStroke("l4_ext", 0.1, 0.34);

  const strokes = [line1, line2, line3, line4];
  const regions = segmentPageInk_v2(strokes);

  let ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions });
  assert.equal(ir.contentUnits.length, 4);

  // Apply OCR to lines
  const [u1, u2, u3, u4] = ir.contentUnits;
  ir = applyOcrToContentUnit(ir, u1.id, "Tập xác định: D = R");
  ir = editContentUnit(ir, u1.id, { kind: "TEXT" }); // Marked as text/explanation

  ir = applyOcrToContentUnit(ir, u2.id, "y' = 3x^2 - 3");
  ir = applyOcrToContentUnit(ir, u3.id, "y' = 0 \\Leftrightarrow x = \\pm 1");
  ir = applyOcrToContentUnit(ir, u4.id, "y(1) = -1,\\quad y(-1) = 3");

  // Approve all units
  ir = approveContentUnit(ir, u1.id);
  ir = approveContentUnit(ir, u2.id);
  ir = approveContentUnit(ir, u3.id);
  ir = approveContentUnit(ir, u4.id);
  assert.equal(ir.reviewStatus, "APPROVED");

  // Project to Legacy Steps for Phát's Evaluator
  const projection = projectTranscriptionToLegacySteps(ir);
  assert.equal(projection.projectedStepCount, 4);
  assert.equal(projection.allUnitsMapped, true);
  assert.equal(projection.unmappedUnitIds.length, 0);

  // Step 1: Text -> EXPLANATION
  assert.equal(projection.steps[0].step_type, "EXPLANATION");
  assert.equal(projection.steps[0].explanation_text, "Tập xác định: D = R");
  assert.equal(projection.steps[0].content_latex, null);

  // Step 2: Derivative -> DERIVATIVE_CALCULATION
  assert.equal(projection.steps[1].step_type, "DERIVATIVE_CALCULATION");
  assert.equal(projection.steps[1].content_latex, "y' = 3x^2 - 3");

  // Step 3: Root finding -> ROOT_FINDING
  assert.equal(projection.steps[2].step_type, "ROOT_FINDING");
  assert.equal(projection.steps[2].content_latex, "y' = 0 \\Leftrightarrow x = \\pm 1");

  // Step 4: Extrema values -> CONCLUSION / CUSTOM
  assert.ok(projection.steps[3].content_latex && projection.steps[3].content_latex.includes("y(1) = -1"));
  assert.ok(["CONCLUSION", "CUSTOM"].includes(projection.steps[3].step_type));
});
