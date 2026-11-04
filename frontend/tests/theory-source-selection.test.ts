import assert from "node:assert/strict";
import test from "node:test";
import type { TheoryNode, TheoryNotebook } from "../src/features/theory-maps/api.js";
import { findNotebookPosition, groupSourceRegions, resolveNotebookLesson } from "../src/features/theory-maps/notebook-selection.js";

const book: TheoryNotebook = {
  page_count: 9, total_blocks: 7,
  sections: [{ id: "s1", title: "Lý thuyết", chapter_number: 1, chapter_title: "Chủ đề 1", blocks: [
    { id: "p4-b0", page: 4, ordinal: 0, kind: "THEORY", title: "Định nghĩa 01" },
    { id: "p4-b1", page: 4, ordinal: 1, kind: "THEORY", title: "Định lý. 01" },
  ] }, { id: "s2", title: "Dạng 1.3", chapter_number: 1, chapter_title: "Chủ đề 1", blocks: [
    { id: "p8-b0", page: 8, ordinal: 0, kind: "METHOD", title: "Dạng 1.3. Hàm phân thức" },
    { id: "p8-b1", page: 8, ordinal: 1, kind: "STEP", title: "Bước 01" },
    { id: "p8-b2", page: 8, ordinal: 2, kind: "STEP", title: "Bước 02" },
    { id: "p8-b3", page: 8, ordinal: 3, kind: "EXAMPLE", title: "Ví dụ 1.3.1" },
    { id: "p9-b0", page: 9, ordinal: 0, kind: "CONTINUATION", title: "Tiếp theo" },
  ] }],
};
const node = (title: string, page: number): TheoryNode => ({
  id: "selected", parent_id: null, kind: "SECTION", title, source_page: page,
  body: "", latex: null, source_quote: title, learning_steps: [], reviewed: false,
});

test("inline lesson includes every method step and example continuation instead of only a heading", () => {
  const blocks = resolveNotebookLesson(book, node("Dạng 1.3. Hàm phân thức.", 8));
  assert.deepEqual(blocks.map((b) => b.id), ["p8-b0", "p8-b1", "p8-b2", "p8-b3", "p9-b0"]);
  const regions = groupSourceRegions(blocks);
  assert.deepEqual(regions.map((r) => r.length), [4, 1]);
  assert.equal(regions[1][0].page, 9);
});

test("a definition does not borrow content from the next theorem", () => {
  assert.deepEqual(resolveNotebookLesson(book, node("Định nghĩa 1.", 4)).map((b) => b.id), ["p4-b0"]);
});

test("stale ordinals resolve by heading; a missing heading never becomes the first card", () => {
  const selected = { ...node("Định lý 01.", 4), block_id: "p4-b0" };
  assert.deepEqual(resolveNotebookLesson(book, selected).map((b) => b.id), ["p4-b1"]);
  assert.deepEqual(resolveNotebookLesson(book, { ...selected, title: "Nhận xét 02" }), []);
  assert.equal(findNotebookPosition(book, { page: 4, title: "Nhận xét 02", blockId: "p4-b0" }), null);
});

test("an example keeps its continuation without unrelated method steps", () => {
  assert.deepEqual(resolveNotebookLesson(book, node("Ví dụ 1.3.1", 8)).map((b) => b.id), ["p8-b3", "p9-b0"]);
});
