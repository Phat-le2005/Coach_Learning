"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const draft_recovery_js_1 = require("../src/features/math-workspace/utils/draft-recovery.js");
const stroke = { id: "local-stroke", tool: "PEN", color: "#000000", width: 2,
    points: [{ x: 0.1, y: 0.2, pressure: 0.5 }] };
function draft(pageIndex, isDirty = true) {
    return { attemptId: "attempt", pageIndex, strokes: [stroke], documentRevision: 4,
        clientActionId: "action", isDirty, updatedAt: 1 };
}
(0, node_test_1.default)("recovers unsaved strokes over the server copy and restores additional pages", () => {
    var _a, _b;
    const serverPage = { strokes: [], past: [], future: [], isDirty: false };
    const original = new Map([[0, serverPage]]);
    const result = (0, draft_recovery_js_1.restoreDirtyPageDrafts)(original, [draft(0), draft(2)], new Set(), 30);
    strict_1.default.equal(result.restored.length, 2);
    strict_1.default.deepEqual((_a = result.pages.get(0)) === null || _a === void 0 ? void 0 : _a.strokes, [stroke]);
    strict_1.default.equal((_b = result.pages.get(2)) === null || _b === void 0 ? void 0 : _b.isDirty, true);
    strict_1.default.equal(original.get(0), serverPage);
});
(0, node_test_1.default)("does not overwrite newer in-memory edits or a clean local page", () => {
    const newer = { strokes: [], past: [], future: [], isDirty: true };
    const original = new Map([[0, newer]]);
    const result = (0, draft_recovery_js_1.restoreDirtyPageDrafts)(original, [draft(0), draft(1), draft(2, false), draft(30)], new Set([1]), 30);
    strict_1.default.equal(result.restored.length, 0);
    strict_1.default.equal(result.pages.get(0), newer);
    strict_1.default.equal(result.pages.has(1), false);
    strict_1.default.equal(result.pages.has(2), false);
});
(0, node_test_1.default)("a recovered draft rebases over an unchanged or empty server page", () => {
    strict_1.default.equal((0, draft_recovery_js_1.canSafelyRebaseInkDraft)([stroke], []), true);
    strict_1.default.equal((0, draft_recovery_js_1.canSafelyRebaseInkDraft)([stroke], [stroke]), true);
});
(0, node_test_1.default)("an append-only draft preserves existing server ink despite a newer document revision", () => {
    const first = { id: "first", tool: "PEN", color: "#000000", width: 2,
        points: [{ x: 0.1, y: 0.2, pressure: 0.5 }] };
    const second = Object.assign(Object.assign({}, first), { id: "second" });
    strict_1.default.equal((0, draft_recovery_js_1.canSafelyRebaseInkDraft)([first, second], [Object.assign({}, first)]), true);
});
(0, node_test_1.default)("a changed server stroke or a local erasure needs explicit conflict resolution", () => {
    const first = { id: "first", tool: "PEN", color: "#000000", width: 2,
        points: [{ x: 0.1, y: 0.2, pressure: 0.5 }] };
    const changed = Object.assign(Object.assign({}, first), { points: [{ x: 0.4, y: 0.2, pressure: 0.5 }] });
    strict_1.default.equal((0, draft_recovery_js_1.canSafelyRebaseInkDraft)([first], [changed]), false);
    strict_1.default.equal((0, draft_recovery_js_1.canSafelyRebaseInkDraft)([], [first]), false);
    strict_1.default.equal((0, draft_recovery_js_1.canSafelyRebaseInkDraft)([first], [first, Object.assign(Object.assign({}, first), { id: "newer" })]), false);
});
