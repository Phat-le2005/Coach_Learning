import assert from "node:assert/strict";
import test from "node:test";
import {
  organizeTheoryNotebook,
  parseExampleBody,
  formatSolutionLines,
} from "../src/features/theory-maps/notebook-organizer.js";
import type { TheoryNode } from "../src/features/theory-maps/api.js";

const makeNode = (
  id: string,
  parent_id: string | null,
  kind: TheoryNode["kind"],
  title: string,
  body = "",
  latex: string | null = null,
  learning_steps: TheoryNode["learning_steps"] = []
): TheoryNode => ({
  id,
  parent_id,
  kind,
  title,
  body,
  latex,
  learning_steps,
  source_page: 1,
  source_quote: title,
  reviewed: true,
});

test("parseExampleBody correctly separates problem statement and step-by-step solution", () => {
  const raw = "Đề bài: Tìm m để y = -x^3 + 3x^2 nghịch biến trên (0; +infty).\nLời giải: - Tính y' = -3x^2 + 6x\n- Để nghịch biến thì y' <= 0";
  const { question, solution } = parseExampleBody(raw);
  assert.equal(question, "Tìm m để y = -x^3 + 3x^2 nghịch biến trên (0; +infty).");
  assert.ok(solution.includes("Tính y' = -3x^2 + 6x"));

  const lines = formatSolutionLines(solution);
  assert.equal(lines.length, 2);
  assert.ok(lines[0].includes("Tính y'"));
  assert.ok(lines[1].includes("Để nghịch biến"));
});

test("organizeTheoryNotebook groups 4-tier pedagogical nodes into sections and dạng toán cards", () => {
  const nodes: TheoryNode[] = [
    makeNode("root", null, "ROOT", "Chuyên đề Đạo hàm"),
    makeNode("sec1", "root", "SECTION", "1. Tính đơn điệu của hàm số", "Lý thuyết chung về đơn điệu"),
    makeNode("c1", "sec1", "CONCEPT", "Dạng 1.1: Cô lập m tìm đơn điệu", "Phương pháp cô lập m"),
    makeNode("f1", "c1", "FORMULA", "📐 Công thức: Quy tắc cô lập m", "Điều kiện m >= g(x)", "m \\ge g(x)"),
    makeNode("m1", "c1", "CONCEPT", "📝 Phương pháp: Các bước cô lập", "", null, [
      { instruction: "Bước 1: Tính đạo hàm y'", latex: "y' \\le 0", source_page: 1, source_quote: null },
      { instruction: "Bước 2: Lập BBT tìm max", latex: "m \\ge \\max g(x)", source_page: 1, source_quote: null },
    ]),
    makeNode("ex1", "c1", "EXAMPLE", "💡 Ví dụ: Tìm m để hàm nghịch biến", "Đề bài: Cho hàm số... Lời giải: Ta có...", "m >= 3"),
    makeNode("no1", "c1", "NOTE", "⚠️ Bẫy sai lầm: Dấu bằng đối với hàm nhất biến", "Hàm phân thức không có dấu bằng"),
  ];

  const { root, sections } = organizeTheoryNotebook(nodes);
  assert.equal(root?.id, "root");
  assert.equal(sections.length, 1);

  const sec = sections[0];
  assert.equal(sec.section.title, "1. Tính đơn điệu của hàm số");
  assert.equal(sec.topics.length, 1);

  const topic = sec.topics[0];
  assert.equal(topic.concept.title, "Dạng 1.1: Cô lập m tìm đơn điệu");
  assert.equal(topic.formulas.length, 1);
  assert.equal(topic.formulas[0].title, "📐 Công thức: Quy tắc cô lập m");
  assert.equal(topic.methods.length, 1);
  assert.equal(topic.methods[0].learning_steps.length, 2);
  assert.equal(topic.examples.length, 1);
  assert.equal(topic.notes.length, 1);
  assert.ok(topic.notes[0].title.includes("Bẫy sai lầm"));
});

test("organizeTheoryNotebook preserves standalone or orphan nodes without data loss", () => {
  const nodes: TheoryNode[] = [
    makeNode("root", null, "ROOT", "Chuyên đề"),
    makeNode("orphan1", "non_existent_parent", "CONCEPT", "Kiến thức ngoài"),
  ];

  const { sections } = organizeTheoryNotebook(nodes);
  assert.ok(sections.length >= 1);
  const allTopicConcepts = sections.flatMap((s) => s.topics.map((t) => t.concept.id));
  assert.ok(allTopicConcepts.includes("orphan1"));
});
