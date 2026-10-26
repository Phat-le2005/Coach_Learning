"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const math_workspace_path_js_1 = require("../src/lib/api/math-workspace-path.js");
const id = "01234567-89ab-4cde-8012-3456789abcde";
const stepId = "a1234567-89ab-4cde-8012-3456789abcde";
(0, node_test_1.default)("Math Workspace BFF permits only the owner-scoped routes needed by the canvas", () => {
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([id], "GET"), `/api/v2/math-solutions/attempts/${id}`);
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([id, "ink", "pages", "0"], "PUT"), `/api/v2/math-solutions/attempts/${id}/ink/pages/0`);
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([id, "ocr", "recognize"], "POST"), `/api/v2/math-solutions/attempts/${id}/ocr/recognize`);
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([id, "steps"], "POST"), `/api/v2/math-solutions/attempts/${id}/steps`);
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([id, "steps", stepId, "delete"], "POST"), `/api/v2/math-solutions/attempts/${id}/steps/${stepId}/delete`);
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([id, "steps", stepId, "delete"], "GET"), null);
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([id, "steps", "not-a-uuid", "delete"], "POST"), null);
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([id, "steps", stepId, "restore"], "POST"), null);
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([id, "steps"], "GET"), null);
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([id, "ink", "pages", "30"], "PUT"), null);
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([id, "submit"], "POST"), `/api/v2/math-solutions/attempts/${id}/submit`);
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([id, "submit"], "GET"), null);
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)(["<attemptId>", "ink"], "GET"), null);
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([id, "..", "auth"], "GET"), null);
});
(0, node_test_1.default)("student can patch only a UUID step through the Math Workspace BFF", () => {
    const attempt = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    const step = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([attempt, "steps", step], "PATCH"), `/api/v2/math-solutions/attempts/${attempt}/steps/${step}`);
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([attempt, "steps", "not-a-uuid"], "PATCH"), null);
    strict_1.default.equal((0, math_workspace_path_js_1.mathWorkspaceProxyPath)([attempt, "steps", step, "delete"], "PATCH"), null);
});
