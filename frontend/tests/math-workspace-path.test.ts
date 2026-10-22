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


test("Math Workspace BFF rejects traversal, extra route fragments, and unsupported methods", () => {
  const forbidden: Array<[string[], string]> = [
    [[id, "ink", "pages", "00"], "PUT"],
    [[id, "ink", "pages", "-1"], "GET"],
    [[id, "ink", "pages", "29", "extra"], "PUT"],
    [[id, "ink", "pages", "0", "..", "steps"], "POST"],
    [[id, "ocr", "recognize", ".."], "POST"],
    [[id, "steps"], "DELETE"],
    [[id, "ink"], "POST"],
    [[id, "submit"], "POST"],
    [[id, "steps", "other"], "POST"],
    [["wrong-id", "ink"], "GET"],
  ];
  for (const [parts, method] of forbidden) {
    assert.equal(mathWorkspaceProxyPath(parts, method), null, JSON.stringify({parts, method}));
  }
  assert.equal(mathWorkspaceProxyPath([id, "ink", "pages", "29"], "PUT"),
               `/api/v2/math-solutions/attempts/${id}/ink/pages/29`);
});
