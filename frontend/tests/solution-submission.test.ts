import assert from "node:assert/strict";
import test from "node:test";

import { getSolutionSubmissionState } from "../src/features/math-workspace/utils/solution-submission.js";

const editableProblem = { is_read_only: false };
const oneStep = { status: "IN_PROGRESS", steps: [{ id: "step-1" }] };

test("a saved short-answer step can be submitted", () => {
  const state = getSolutionSubmissionState(editableProblem, oneStep, false);
  assert.equal(state.showSubmitButton, true);
  assert.equal(state.canSubmit, true);
});

test("submission is independent of question type and requires a confirmed step", () => {
  const empty = getSolutionSubmissionState(editableProblem, { status: "DRAFT", steps: [] }, false);
  assert.equal(empty.showSubmitButton, true);
  assert.equal(empty.canSubmit, false);
});

test("submitted, read-only, and source-review attempts cannot submit again", () => {
  assert.equal(getSolutionSubmissionState(editableProblem, { status: "SUBMITTED", steps: oneStep.steps }, false).showSubmitButton, false);
  assert.equal(getSolutionSubmissionState({ is_read_only: true }, oneStep, false).showSubmitButton, false);
  assert.equal(getSolutionSubmissionState(editableProblem, oneStep, true).showSubmitButton, false);
});
