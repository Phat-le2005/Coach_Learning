import assert from "node:assert/strict";
import test from "node:test";

import { mathWorkspaceProxyPath } from "../src/lib/api/math-workspace-path.js";

const id = "01234567-89ab-4cde-8012-3456789abcde";

test("Math Workspace BFF permits only the owner-scoped routes needed by the canvas", () => {
  assert.equal(mathWorkspaceProxyPath([id], "GET"), `/api/v2/math-solutions/attempts/${id}`);
  assert.equal(mathWorkspaceProxyPath([id, "ink", "pages", "0"], "PUT"), `/api/v2/math-solutions/attempts/${id}/ink/pages/0`);
  assert.equal(mathWorkspaceProxyPath([id, "ocr", "recognize"], "POST"), `/api/v2/math-solutions/attempts/${id}/ocr/recognize`);
  assert.equal(mathWorkspaceProxyPath([id, "steps"], "POST"), `/api/v2/math-solutions/attempts/${id}/steps`);
  assert.equal(mathWorkspaceProxyPath([id, "steps"], "GET"), null);
  assert.equal(mathWorkspaceProxyPath([id, "ink", "pages", "30"], "PUT"), null);
  assert.equal(mathWorkspaceProxyPath([id, "submit"], "POST"), null);
  assert.equal(mathWorkspaceProxyPath(["<attemptId>", "ink"], "GET"), null);
  assert.equal(mathWorkspaceProxyPath([id, "..", "auth"], "GET"), null);
});
