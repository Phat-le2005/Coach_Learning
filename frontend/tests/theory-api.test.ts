import assert from "node:assert/strict";
import test from "node:test";
import { parseMap, parseNotebook, theoryApi } from "../src/features/theory-maps/api.js";

const id = "00000000-0000-4000-8000-000000000001";
const summary = { id, classroom_id: id, subject_id: id, title: "Đạo hàm", file_name: "theory.pdf",
  sha256: "a".repeat(64), page_count: 1, status: "PUBLISHED", revision: 3, source_available: true };

test("theory map contract requires cited, typed nodes", () => {
  const map = parseMap({ ...summary, ai_model: "gemini", extraction_warning_pages: [1], nodes: [{ id: "root", parent_id: null,
    kind: "ROOT", title: "Đạo hàm", body: "", latex: null, source_page: 1,
    source_quote: "Đạo hàm", reviewed: true }] });
  assert.equal(map.nodes[0].source_page, 1);
  assert.deepEqual(map.extraction_warning_pages, [1]);
  assert.throws(() => parseMap({ ...summary, ai_model: null, extraction_warning_pages: [], nodes: [{ ...map.nodes[0], reviewed: "yes" }] }));
  assert.throws(() => parseMap({ ...summary, status: "UNREVIEWED", ai_model: null, extraction_warning_pages: [], nodes: [] }));
  assert.throws(() => parseMap({ ...summary, ai_model: null, extraction_warning_pages: ["one"], nodes: [] }));
});

test("teacher-authored learning steps and formulas are validated without inventing content", () => {
  const node = { id: "exercise", parent_id: null, kind: "ROOT", title: "Exercise",
    body: "Review the method", latex: "f'(x)", source_page: 1, source_quote: "Exercise", reviewed: true,
    learning_steps: [{ instruction: "Differentiate", latex: "f'(x)", source_page: 1 }] };
  const map = parseMap({ ...summary, ai_model: null, extraction_warning_pages: [], nodes: [node] });
  assert.deepEqual(map.nodes[0].learning_steps, [{ ...node.learning_steps[0], source_quote: null }]);
  assert.throws(() => parseMap({ ...summary, ai_model: null, extraction_warning_pages: [], nodes: [
    { ...node, learning_steps: [{ ...node.learning_steps[0], source_page: "first" }] },
  ] }));
});

test("student theory list uses live BFF and surfaces backend errors", async () => {
  const original = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    calls.push(String(input));
    return new Response(JSON.stringify([summary]), { status: 200 });
  }) as typeof fetch;
  try {
    const rows = await theoryApi.studentList();
    assert.equal(rows.length, 1);
    assert.equal(calls[0], "/api/student/theory");
  } finally { globalThis.fetch = original; }
  globalThis.fetch = (async () => new Response(JSON.stringify({ error: { message: "Unavailable" } }), { status: 503 })) as typeof fetch;
  try { await assert.rejects(() => theoryApi.studentList(), /Unavailable/); }
  finally { globalThis.fetch = original; }
});

test("source publication is separate from map review and must be typed", () => {
  const sourceOnly = parseMap({ ...summary, status: "DRAFT", source_available: true,
    ai_model: null, extraction_warning_pages: [], nodes: [], source_outline: [
      { title: "Bài 1. Đơn điệu", source_page: 2, kind: "CHAPTER" },
    ] });
  assert.equal(sourceOnly.source_available, true);
  assert.equal(sourceOnly.status, "DRAFT");
  assert.equal(sourceOnly.source_outline[0].source_page, 2);
  assert.throws(() => parseMap({ ...summary, source_available: "yes", ai_model: null,
    extraction_warning_pages: [], nodes: [] }));
  assert.throws(() => parseMap({ ...summary, ai_model: null, extraction_warning_pages: [], nodes: [],
    source_outline: [{ title: "Invented", source_page: 1, kind: "FORMULA" }] }));
});

test("notebook contract preserves source order and rejects invented or broken cards", () => {
  const value = { page_count: 2, total_blocks: 2, sections: [{
    id: "section-1", title: "Method 1.1", chapter_number: 1, chapter_title: "Chapter 1",
    blocks: [
      { id: "p1-b0", page: 1, ordinal: 0, kind: "METHOD", title: "Method 1.1" },
      { id: "p2-b0", page: 2, ordinal: 0, kind: "EXAMPLE", title: "Example 1" },
    ],
  }] };
  assert.equal(parseNotebook(value).sections[0].blocks[1].page, 2);
  assert.equal(parseNotebook({ ...value, sections: [{ ...value.sections[0], blocks: [{ ...value.sections[0].blocks[0], kind: "STEP" }, value.sections[0].blocks[1]] }] }).sections[0].blocks[0].kind, "STEP");
  assert.throws(() => parseNotebook({ ...value, total_blocks: 3 }));
  assert.throws(() => parseNotebook({ ...value, sections: [{
    ...value.sections[0], blocks: [{ ...value.sections[0].blocks[0], kind: "SYNTHETIC" }],
  }] }));
  assert.throws(() => parseNotebook({ ...value, sections: [{
    ...value.sections[0], blocks: [{ ...value.sections[0].blocks[0], page: 3 }],
  }] }));
});