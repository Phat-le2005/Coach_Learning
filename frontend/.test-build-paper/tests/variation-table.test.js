"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const contracts_js_1 = require("../src/lib/api/contracts.js");
const variation_table_js_1 = require("../src/features/math-workspace/utils/variation-table.js");
(0, node_test_1.default)("empty table contains no invented mathematics", () => {
    const draft = (0, variation_table_js_1.createVariationTableDraft)();
    strict_1.default.equal(draft.points.length, 3);
    strict_1.default.ok(draft.points.every((point) => point.x === "" && point.y === ""));
    strict_1.default.ok(draft.intervals.every((interval) => interval.sign === ""));
    strict_1.default.equal((0, variation_table_js_1.validateVariationTable)(draft), "TABLE_X_REQUIRED_OR_DUPLICATE");
});
(0, node_test_1.default)("student signs deterministically draw matching arrows", () => {
    strict_1.default.equal((0, variation_table_js_1.trendForSign)("+"), "UP");
    strict_1.default.equal((0, variation_table_js_1.trendForSign)("-"), "DOWN");
    strict_1.default.equal((0, variation_table_js_1.trendForSign)("0"), "FLAT");
    const draft = (0, variation_table_js_1.createVariationTableDraft)();
    draft.points.forEach((point, index) => { point.x = ["-inf", "a", "+inf"][index]; });
    draft.intervals[0] = { sign: "+", trend: (0, variation_table_js_1.trendForSign)("+") };
    draft.intervals[1] = { sign: "-", trend: (0, variation_table_js_1.trendForSign)("-") };
    strict_1.default.equal((0, variation_table_js_1.validateVariationTable)(draft), null);
    strict_1.default.deepEqual((0, contracts_js_1.parseVariationTablePayload)((0, variation_table_js_1.toVariationTablePayload)(draft)).intervals, [{ sign: "+", trend: "UP" }, { sign: "-", trend: "DOWN" }]);
});
(0, node_test_1.default)("adding and removing a critical point preserves aligned columns", () => {
    const draft = (0, variation_table_js_1.createVariationTableDraft)();
    const added = (0, variation_table_js_1.addVariationPoint)(draft);
    strict_1.default.equal(added.points.length, 4);
    strict_1.default.equal(added.intervals.length, 3);
    strict_1.default.equal((0, variation_table_js_1.removeVariationPoint)(added).points.length, 3);
    strict_1.default.equal((0, variation_table_js_1.removeVariationPoint)(added).intervals.length, 2);
});
(0, node_test_1.default)("duplicate x and sign-arrow conflicts are not accepted", () => {
    const draft = (0, variation_table_js_1.createVariationTableDraft)();
    draft.points.forEach((point) => { point.x = "same"; });
    strict_1.default.equal((0, variation_table_js_1.validateVariationTable)(draft), "TABLE_X_REQUIRED_OR_DUPLICATE");
    draft.points.forEach((point, index) => { point.x = String(index); });
    draft.intervals[0] = { sign: "+", trend: "DOWN" };
    draft.intervals[1] = { sign: "-", trend: "DOWN" };
    strict_1.default.equal((0, variation_table_js_1.validateVariationTable)(draft), "TABLE_SIGNS_REQUIRED");
    strict_1.default.throws(() => (0, contracts_js_1.parseVariationTablePayload)({ version: 1, points: [], intervals: [] }));
});
(0, node_test_1.default)("saved variation table survives attempt reload as structured artifact", () => {
    var _a, _b;
    const draft = (0, variation_table_js_1.createVariationTableDraft)();
    draft.points.forEach((point, index) => { point.x = ["left", "middle", "right"][index]; });
    draft.intervals[0] = { sign: "+", trend: "UP" };
    draft.intervals[1] = { sign: "-", trend: "DOWN" };
    const payload = (0, variation_table_js_1.toVariationTablePayload)(draft);
    const attempt = (0, contracts_js_1.parseSolutionAttemptRead)({ id: "attempt", question_id: "question", status: "IN_PROGRESS",
        attempt_revision_number: 2, started_at: "2026-10-25T00:00:00Z", steps: [{
                id: "step", step_index: 1, step_type: "VARIATION_TABLE", content_latex: null,
                explanation_text: null, step_revision_number: 1,
                artifact: { artifact_type: "VARIATION_TABLE", payload },
            }] });
    strict_1.default.deepEqual((0, contracts_js_1.parseVariationTablePayload)((_b = (_a = attempt.steps) === null || _a === void 0 ? void 0 : _a[0].artifact) === null || _b === void 0 ? void 0 : _b.payload), payload);
});
