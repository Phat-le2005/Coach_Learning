import assert from "node:assert/strict";
import test from "node:test";
import { computeTheory3DLayout, getNodeKindColor } from "../src/features/theory-maps/theory-3d-layout.js";
import type { TheoryNode } from "../src/features/theory-maps/api.js";

const makeNode = (
  id: string,
  parent_id: string | null,
  kind: TheoryNode["kind"],
  title: string
): TheoryNode => ({
  id,
  parent_id,
  kind,
  title,
  body: "",
  latex: null,
  learning_steps: [],
  source_page: 1,
  source_quote: title,
  reviewed: true,
});

test("computeTheory3DLayout places root at center and sections in orbital circle", () => {
  const nodes: TheoryNode[] = [
    makeNode("root", null, "ROOT", "Toán 12"),
    makeNode("s1", "root", "SECTION", "1. Đơn điệu"),
    makeNode("s2", "root", "SECTION", "2. Cực trị"),
    makeNode("c1", "s1", "CONCEPT", "Dạng cô lập m"),
    makeNode("f1", "c1", "FORMULA", "Công thức"),
  ];

  const layout = computeTheory3DLayout(nodes);

  assert.equal(layout.nodes.length, 5);
  const rootItem = layout.nodeMap.get("root");
  assert.ok(rootItem);
  assert.equal(rootItem.position.x, 0);
  assert.equal(rootItem.position.y, 0);
  assert.equal(rootItem.position.z, 0);

  const s1 = layout.nodeMap.get("s1");
  const s2 = layout.nodeMap.get("s2");
  assert.ok(s1 && s2);
  assert.notEqual(s1.position.x, 0);
  assert.notEqual(s2.position.x, 0);

  // Connection exists
  assert.ok(layout.connections.length >= 4);
  assert.equal(layout.sections.length, 2);
});

test("getNodeKindColor returns designated color by node category", () => {
  assert.equal(getNodeKindColor("FORMULA", "Công thức", "#fff"), "#34d399");
  assert.equal(getNodeKindColor("EXAMPLE", "💡 Ví dụ", "#fff"), "#fbbf24");
  assert.equal(getNodeKindColor("NOTE", "⚠️ Bẫy", "#fff"), "#f87171");
  assert.equal(getNodeKindColor("CONCEPT", "📝 Phương pháp", "#fff"), "#38bdf8");
  assert.equal(getNodeKindColor("ROOT", "Tiêu đề", "#fallback"), "#fallback");
});
