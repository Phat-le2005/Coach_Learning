import assert from "node:assert/strict";
import test from "node:test";

import { mathWorkspaceProxyPath } from "../src/lib/api/math-workspace-path.js";

const id = "01234567-89ab-4cde-8012-3456789abcde";
const stepId = "a1234567-89ab-4cde-8012-3456789abcde";

test("Math Workspace BFF permits only the owner-scoped routes needed by the canvas", () => {
  assert.equal(mathWorkspaceProxyPath([id], "GET"), `/api/v2/math-solutions/attempts/${id}`);
  assert.equal(mathWorkspaceProxyPath([id, "ink", "pages", "0"], "PUT"), `/api/v2/math-solutions/attempts/${id}/ink/pages/0`);
  assert.equal(mathWorkspaceProxyPath([id, "ocr", "recognize"], "POST"), `/api/v2/math-solutions/attempts/${id}/ocr/recognize`);
  assert.equal(mathWorkspaceProxyPath([id, "steps"], "POST"), `/api/v2/math-solutions/attempts/${id}/steps`);
  assert.equal(mathWorkspaceProxyPath([id, "steps", stepId, "delete"], "POST"),
    `/api/v2/math-solutions/attempts/${id}/steps/${stepId}/delete`);
  assert.equal(mathWorkspaceProxyPath([id, "steps", stepId, "delete"], "GET"), null);
  assert.equal(mathWorkspaceProxyPath([id, "steps", "not-a-uuid", "delete"], "POST"), null);
  assert.equal(mathWorkspaceProxyPath([id, "steps", stepId, "restore"], "POST"), null);
  assert.equal(mathWorkspaceProxyPath([id, "steps"], "GET"), null);
  assert.equal(mathWorkspaceProxyPath([id, "ink", "pages", "30"], "PUT"), null);
  assert.equal(mathWorkspaceProxyPath([id, "submit"], "POST"), `/api/v2/math-solutions/attempts/${id}/submit`);
  assert.equal(mathWorkspaceProxyPath([id, "submit"], "GET"), null);
  assert.equal(mathWorkspaceProxyPath(["<attemptId>", "ink"], "GET"), null);
  assert.equal(mathWorkspaceProxyPath([id, "..", "auth"], "GET"), null);
});

test("student can patch only a UUID step through the Math Workspace BFF", () => {
  const attempt = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const step = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  assert.equal(mathWorkspaceProxyPath([attempt, "steps", step], "PATCH"),
    `/api/v2/math-solutions/attempts/${attempt}/steps/${step}`);
  assert.equal(mathWorkspaceProxyPath([attempt, "steps", "not-a-uuid"], "PATCH"), null);
  assert.equal(mathWorkspaceProxyPath([attempt, "steps", step, "delete"], "PATCH"), null);
});
