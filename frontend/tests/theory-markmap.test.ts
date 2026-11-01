import assert from "node:assert/strict";
import test from "node:test";
import { scopeTheoryNodes, toMarkmapTree } from "../src/features/theory-maps/markmap-tree.js";
import type { TheoryNode } from "../src/features/theory-maps/api.js";

const node = (id: string, parent_id: string | null, title: string): TheoryNode => ({
  id, parent_id, title, kind: parent_id ? "CONCEPT" : "ROOT", body: "",
  latex: null, learning_steps: [], source_page: 1, source_quote: title, reviewed: false,
});

test("Markmap tree retains source hierarchy without injecting HTML or fake nodes", () => {
  const tree = toMarkmapTree([node("root", null, "Đạo hàm"), node("a", "root", "<img src=x onerror=alert(1)>"),
    node("b", "a", "x & y")]);
  assert.equal(tree?.payload.nodeId, "root");
  assert.equal(tree?.children[0].payload.nodeId, "a");
  assert.equal(tree?.children[0].children[0].content, "x &amp; y");
  assert.equal(tree?.children[0].content, "&lt;img src=x onerror=alert(1)&gt;");
  assert.equal(tree?.children.length, 1);
  assert.equal(toMarkmapTree([]), null);
});

test("large maps can show one branch without unrelated siblings", () => {
  const nodes = [node("root", null, "Root"), node("first", "root", "First"),
    node("leaf", "first", "Leaf"), node("second", "root", "Second")];
  assert.deepEqual(scopeTheoryNodes(nodes, "first").map((item) => item.id), ["root", "first", "leaf"]);
  assert.deepEqual(scopeTheoryNodes(nodes, "root").map((item) => item.id), ["root", "first", "leaf", "second"]);
});
