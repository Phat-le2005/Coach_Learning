"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const strict_1 = __importDefault(require("node:assert/strict"));
const utils_js_1 = require("../src/features/math-solver/utils.js");
(0, node_test_1.default)("SIGN_CYCLE contains the canonical sign table symbols", () => {
    strict_1.default.deepEqual(Array.from(utils_js_1.SIGN_CYCLE), ["+", "-", "0", "||"]);
});
(0, node_test_1.default)("cycleSign advances through symbols cyclically", () => {
    strict_1.default.equal((0, utils_js_1.cycleSign)("+"), "-");
    strict_1.default.equal((0, utils_js_1.cycleSign)("-"), "0");
    strict_1.default.equal((0, utils_js_1.cycleSign)("0"), "||");
    strict_1.default.equal((0, utils_js_1.cycleSign)("||"), "+");
});
(0, node_test_1.default)("cycleSign falls back to '+' for unknown symbols", () => {
    strict_1.default.equal((0, utils_js_1.cycleSign)("?"), "+");
    strict_1.default.equal((0, utils_js_1.cycleSign)(""), "+");
});
(0, node_test_1.default)("invertSigns inverts '+' and '-' while preserving '0' and '||'", () => {
    const initial = ["+", "-", "0", "||", "+"];
    const inverted = (0, utils_js_1.invertSigns)(initial);
    strict_1.default.deepEqual(inverted, ["-", "+", "0", "||", "-"]);
    // Inverting twice restores the original state
    const doubleInverted = (0, utils_js_1.invertSigns)(inverted);
    strict_1.default.deepEqual(doubleInverted, initial);
});
(0, node_test_1.default)("addCriticalPoint inserts numeric point and maintains signs invariant (len = points + 1)", () => {
    const initial = {
        critical_points: [-1],
        signs: ["+", "-"],
    };
    const updated = (0, utils_js_1.addCriticalPoint)(initial, 3);
    strict_1.default.deepEqual(updated.critical_points, [-1, 3]);
    strict_1.default.equal(updated.signs.length, 3);
    strict_1.default.deepEqual(updated.signs, ["+", "-", "+"]);
});
(0, node_test_1.default)("addCriticalPoint handles string/latex input without NaN corruption", () => {
    const initial = {
        critical_points: [0],
        signs: ["-", "+"],
    };
    const updated = (0, utils_js_1.addCriticalPoint)(initial, "\\sqrt{3}");
    strict_1.default.deepEqual(updated.critical_points, [0, "\\sqrt{3}"]);
    strict_1.default.equal(updated.signs.length, 3);
    strict_1.default.deepEqual(updated.signs, ["-", "+", "+"]);
});
(0, node_test_1.default)("removeCriticalPoint removes point and adjusts signs array", () => {
    const initial = {
        critical_points: [-1, 3],
        signs: ["+", "-", "+"],
    };
    const updated = (0, utils_js_1.removeCriticalPoint)(initial, 0);
    strict_1.default.deepEqual(updated.critical_points, [3]);
    strict_1.default.equal(updated.signs.length, 2);
    strict_1.default.deepEqual(updated.signs, ["-", "+"]);
});
(0, node_test_1.default)("removeCriticalPoint on last point keeps at least 1 default sign", () => {
    const initial = {
        critical_points: [2],
        signs: ["-", "+"],
    };
    const updated = (0, utils_js_1.removeCriticalPoint)(initial, 0);
    strict_1.default.deepEqual(updated.critical_points, []);
    strict_1.default.equal(updated.signs.length, 1);
    strict_1.default.deepEqual(updated.signs, ["+"]);
});
(0, node_test_1.default)("reorderStepsList correctly moves a step up", () => {
    const steps = [
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
    const result = (0, utils_js_1.reorderStepsList)(steps, "step-2", "up");
    strict_1.default.ok(result !== null);
    strict_1.default.deepEqual(result.stepIds, ["step-2", "step-1", "step-3"]);
    strict_1.default.equal(result.reorderedSteps[0].id, "step-2");
    strict_1.default.equal(result.reorderedSteps[1].id, "step-1");
});
(0, node_test_1.default)("reorderStepsList correctly moves a step down", () => {
    const steps = [
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
    const result = (0, utils_js_1.reorderStepsList)(steps, "step-1", "down");
    strict_1.default.ok(result !== null);
    strict_1.default.deepEqual(result.stepIds, ["step-2", "step-1", "step-3"]);
});
(0, node_test_1.default)("reorderStepsList returns null on boundary conditions", () => {
    const steps = [
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
    strict_1.default.equal((0, utils_js_1.reorderStepsList)(steps, "step-1", "up"), null);
    // Moving bottom item down is forbidden
    strict_1.default.equal((0, utils_js_1.reorderStepsList)(steps, "step-2", "down"), null);
    // Unknown item returns null
    strict_1.default.equal((0, utils_js_1.reorderStepsList)(steps, "non-existent", "up"), null);
});
(0, node_test_1.default)("reorderStepsList ignores deleted steps", () => {
    const steps = [
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
    strict_1.default.equal((0, utils_js_1.reorderStepsList)(steps, "step-2", "up"), null);
    const result = (0, utils_js_1.reorderStepsList)(steps, "step-2", "down");
    strict_1.default.ok(result !== null);
    strict_1.default.deepEqual(result.stepIds, ["step-3", "step-2"]);
});
(0, node_test_1.default)("canSubmitAttempt validates required active steps and read-only status", () => {
    // Empty steps cannot be submitted
    strict_1.default.equal((0, utils_js_1.canSubmitAttempt)([], "IN_PROGRESS").canSubmit, false);
    strict_1.default.equal((0, utils_js_1.canSubmitAttempt)(undefined, "IN_PROGRESS").canSubmit, false);
    // All deleted steps cannot be submitted
    const deletedOnly = [
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
    strict_1.default.equal((0, utils_js_1.canSubmitAttempt)(deletedOnly, "IN_PROGRESS").canSubmit, false);
    // Already submitted or evaluated cannot be submitted again
    const activeSteps = [
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
    strict_1.default.equal((0, utils_js_1.canSubmitAttempt)(activeSteps, "SUBMITTED").canSubmit, false);
    strict_1.default.equal((0, utils_js_1.canSubmitAttempt)(activeSteps, "EVALUATED").canSubmit, false);
    // Active steps in DRAFT or IN_PROGRESS can be submitted
    strict_1.default.equal((0, utils_js_1.canSubmitAttempt)(activeSteps, "IN_PROGRESS").canSubmit, true);
    strict_1.default.equal((0, utils_js_1.canSubmitAttempt)(activeSteps, "DRAFT").canSubmit, true);
});
(0, node_test_1.default)("sign table payload strictly conforms to backend evaluator schema", () => {
    const backendExpectedPayload = {
        critical_points: [-1, 3],
        signs: ["+", "-", "+"],
    };
    strict_1.default.equal(backendExpectedPayload.critical_points.length + 1, backendExpectedPayload.signs.length);
    strict_1.default.equal(backendExpectedPayload.critical_points[0], -1);
    strict_1.default.equal(backendExpectedPayload.critical_points[1], 3);
    strict_1.default.equal(backendExpectedPayload.signs[0], "+");
    strict_1.default.equal(backendExpectedPayload.signs[1], "-");
    strict_1.default.equal(backendExpectedPayload.signs[2], "+");
});
