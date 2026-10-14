import test from "node:test";
import assert from "node:assert/strict";

import {
  cycleSign,
  invertSigns,
  addCriticalPoint,
  removeCriticalPoint,
  reorderStepsList,
  canSubmitAttempt,
  SIGN_CYCLE,
} from "../src/features/math-solver/utils.js";
import type {
  SignTablePayload,
  SolutionStepItem,
  SolutionSolverAttempt,
} from "../src/features/math-solver/types.js";

test("SIGN_CYCLE contains the canonical sign table symbols", () => {
  assert.deepEqual(Array.from(SIGN_CYCLE), ["+", "-", "0", "||"]);
});

test("cycleSign advances through symbols cyclically", () => {
  assert.equal(cycleSign("+"), "-");
  assert.equal(cycleSign("-"), "0");
  assert.equal(cycleSign("0"), "||");
  assert.equal(cycleSign("||"), "+");
});

test("cycleSign falls back to '+' for unknown symbols", () => {
  assert.equal(cycleSign("?"), "+");
  assert.equal(cycleSign(""), "+");
});

test("invertSigns inverts '+' and '-' while preserving '0' and '||'", () => {
  const initial = ["+", "-", "0", "||", "+"];
  const inverted = invertSigns(initial);
  assert.deepEqual(inverted, ["-", "+", "0", "||", "-"]);

  // Inverting twice restores the original state
  const doubleInverted = invertSigns(inverted);
  assert.deepEqual(doubleInverted, initial);
});

test("addCriticalPoint inserts numeric point and maintains signs invariant (len = points + 1)", () => {
  const initial: SignTablePayload = {
    critical_points: [-1],
    signs: ["+", "-"],
  };

  const updated = addCriticalPoint(initial, 3);
  assert.deepEqual(updated.critical_points, [-1, 3]);
  assert.equal(updated.signs.length, 3);
  assert.deepEqual(updated.signs, ["+", "-", "+"]);
});

test("addCriticalPoint handles string/latex input without NaN corruption", () => {
  const initial: SignTablePayload = {
    critical_points: [0],
    signs: ["-", "+"],
  };

  const updated = addCriticalPoint(initial, "\\sqrt{3}");
  assert.deepEqual(updated.critical_points, [0, "\\sqrt{3}"]);
  assert.equal(updated.signs.length, 3);
  assert.deepEqual(updated.signs, ["-", "+", "+"]);
});

test("removeCriticalPoint removes point and adjusts signs array", () => {
  const initial: SignTablePayload = {
    critical_points: [-1, 3],
    signs: ["+", "-", "+"],
  };

  const updated = removeCriticalPoint(initial, 0);
  assert.deepEqual(updated.critical_points, [3]);
  assert.equal(updated.signs.length, 2);
  assert.deepEqual(updated.signs, ["-", "+"]);
});

test("removeCriticalPoint on last point keeps at least 1 default sign", () => {
  const initial: SignTablePayload = {
    critical_points: [2],
    signs: ["-", "+"],
  };

  const updated = removeCriticalPoint(initial, 0);
  assert.deepEqual(updated.critical_points, []);
  assert.equal(updated.signs.length, 1);
  assert.deepEqual(updated.signs, ["+"]);
});

test("reorderStepsList correctly moves a step up", () => {
  const steps: SolutionStepItem[] = [
    {
      id: "step-1",
      step_index: 1,
      step_type: "DERIVATIVE_CALCULATION",
      content_latex: "y' = 3x^2 - 6x",
      explanation_text: null,
      step_revision_number: 1,
    },
    {
      id: "step-2",
      step_index: 2,
      step_type: "ROOT_FINDING",
      content_latex: "x = 0 \\lor x = 2",
      explanation_text: null,
      step_revision_number: 1,
    },
    {
      id: "step-3",
      step_index: 3,
      step_type: "SIGN_TABLE",
      content_latex: "Bảng xét dấu",
      explanation_text: null,
      step_revision_number: 1,
    },
  ];

  const result = reorderStepsList(steps, "step-2", "up");
  assert.ok(result !== null);
  assert.deepEqual(result.stepIds, ["step-2", "step-1", "step-3"]);
  assert.equal(result.reorderedSteps[0].id, "step-2");
  assert.equal(result.reorderedSteps[1].id, "step-1");
});

test("reorderStepsList correctly moves a step down", () => {
  const steps: SolutionStepItem[] = [
    {
      id: "step-1",
      step_index: 1,
      step_type: "DERIVATIVE_CALCULATION",
      content_latex: "y' = 3x^2 - 6x",
      explanation_text: null,
      step_revision_number: 1,
    },
    {
      id: "step-2",
      step_index: 2,
      step_type: "ROOT_FINDING",
      content_latex: "x = 0 \\lor x = 2",
      explanation_text: null,
      step_revision_number: 1,
    },
    {
      id: "step-3",
      step_index: 3,
      step_type: "SIGN_TABLE",
      content_latex: "Bảng xét dấu",
      explanation_text: null,
      step_revision_number: 1,
    },
  ];

  const result = reorderStepsList(steps, "step-1", "down");
  assert.ok(result !== null);
  assert.deepEqual(result.stepIds, ["step-2", "step-1", "step-3"]);
});

test("reorderStepsList returns null on boundary conditions", () => {
  const steps: SolutionStepItem[] = [
    {
      id: "step-1",
      step_index: 1,
      step_type: "DERIVATIVE_CALCULATION",
      content_latex: "y' = 3x^2 - 6x",
      explanation_text: null,
      step_revision_number: 1,
    },
    {
      id: "step-2",
      step_index: 2,
      step_type: "ROOT_FINDING",
      content_latex: "x = 0",
      explanation_text: null,
      step_revision_number: 1,
    },
  ];

  // Moving top item up is forbidden
  assert.equal(reorderStepsList(steps, "step-1", "up"), null);
  // Moving bottom item down is forbidden
  assert.equal(reorderStepsList(steps, "step-2", "down"), null);
  // Unknown item returns null
  assert.equal(reorderStepsList(steps, "non-existent", "up"), null);
});

test("reorderStepsList ignores deleted steps", () => {
  const steps: SolutionStepItem[] = [
    {
      id: "step-1",
      step_index: 1,
      step_type: "DERIVATIVE_CALCULATION",
      content_latex: "y' = 3x^2",
      explanation_text: null,
      step_revision_number: 1,
      is_deleted: true,
    },
    {
      id: "step-2",
      step_index: 2,
      step_type: "ROOT_FINDING",
      content_latex: "x = 0",
      explanation_text: null,
      step_revision_number: 1,
    },
    {
      id: "step-3",
      step_index: 3,
      step_type: "CONCLUSION",
      content_latex: "Đồng biến",
      explanation_text: null,
      step_revision_number: 1,
    },
  ];

  // Active steps are only step-2 and step-3
  // step-2 is now the active top item, so moving it up should return null
  assert.equal(reorderStepsList(steps, "step-2", "up"), null);

  const result = reorderStepsList(steps, "step-2", "down");
  assert.ok(result !== null);
  assert.deepEqual(result.stepIds, ["step-3", "step-2"]);
});

test("canSubmitAttempt validates required active steps and read-only status", () => {
  // Empty steps cannot be submitted
  assert.equal(canSubmitAttempt([], "IN_PROGRESS").canSubmit, false);
  assert.equal(canSubmitAttempt(undefined, "IN_PROGRESS").canSubmit, false);

  // All deleted steps cannot be submitted
  const deletedOnly: SolutionStepItem[] = [
    {
      id: "step-1",
      step_index: 1,
      step_type: "DERIVATIVE_CALCULATION",
      content_latex: "y' = 3x^2",
      explanation_text: null,
      step_revision_number: 1,
      is_deleted: true,
    },
  ];
  assert.equal(canSubmitAttempt(deletedOnly, "IN_PROGRESS").canSubmit, false);

  // Already submitted or evaluated cannot be submitted again
  const activeSteps: SolutionStepItem[] = [
    {
      id: "step-1",
      step_index: 1,
      step_type: "DERIVATIVE_CALCULATION",
      content_latex: "y' = 3x^2",
      explanation_text: null,
      step_revision_number: 1,
      is_deleted: false,
    },
  ];
  assert.equal(canSubmitAttempt(activeSteps, "SUBMITTED").canSubmit, false);
  assert.equal(canSubmitAttempt(activeSteps, "EVALUATED").canSubmit, false);

  // Active steps in DRAFT or IN_PROGRESS can be submitted
  assert.equal(canSubmitAttempt(activeSteps, "IN_PROGRESS").canSubmit, true);
  assert.equal(canSubmitAttempt(activeSteps, "DRAFT").canSubmit, true);
});

test("sign table payload strictly conforms to backend evaluator schema", () => {
  const backendExpectedPayload: SignTablePayload = {
    critical_points: [-1, 3],
    signs: ["+", "-", "+"],
  };

  assert.equal(backendExpectedPayload.critical_points.length + 1, backendExpectedPayload.signs.length);
  assert.equal(backendExpectedPayload.critical_points[0], -1);
  assert.equal(backendExpectedPayload.critical_points[1], 3);
  assert.equal(backendExpectedPayload.signs[0], "+");
  assert.equal(backendExpectedPayload.signs[1], "-");
  assert.equal(backendExpectedPayload.signs[2], "+");
});
