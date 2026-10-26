"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const solution_submission_js_1 = require("../src/features/math-workspace/utils/solution-submission.js");
const editableProblem = { is_read_only: false };
const oneStep = { status: "IN_PROGRESS", steps: [{ id: "step-1" }] };
(0, node_test_1.default)("a saved short-answer step can be submitted", () => {
    const state = (0, solution_submission_js_1.getSolutionSubmissionState)(editableProblem, oneStep, false);
    strict_1.default.equal(state.showSubmitButton, true);
    strict_1.default.equal(state.canSubmit, true);
});
(0, node_test_1.default)("submission is independent of question type and requires a confirmed step", () => {
    const empty = (0, solution_submission_js_1.getSolutionSubmissionState)(editableProblem, { status: "DRAFT", steps: [] }, false);
    strict_1.default.equal(empty.showSubmitButton, true);
    strict_1.default.equal(empty.canSubmit, false);
});
(0, node_test_1.default)("submitted, read-only, and source-review attempts cannot submit again", () => {
    strict_1.default.equal((0, solution_submission_js_1.getSolutionSubmissionState)(editableProblem, { status: "SUBMITTED", steps: oneStep.steps }, false).showSubmitButton, false);
    strict_1.default.equal((0, solution_submission_js_1.getSolutionSubmissionState)({ is_read_only: true }, oneStep, false).showSubmitButton, false);
    strict_1.default.equal((0, solution_submission_js_1.getSolutionSubmissionState)(editableProblem, oneStep, true).showSubmitButton, false);
});
