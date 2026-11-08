import assert from "node:assert/strict";
import test from "node:test";
import { resolveTheoryDocument } from "../src/features/theory-maps/theory-target";
import type { TheorySummary } from "../src/features/theory-maps/api";

const item = (id: string, title: string): TheorySummary => ({
  id, title, classroom_id: "class", subject_id: "math", file_name: "lesson.pdf", sha256: "fixture",
  page_count: 2, status: "PUBLISHED", revision: 1, source_available: true,
});
const docs = [item("derivative", "Đạo hàm"), item("integral", "Tích phân")];

test("theory links resolve a unique label after Unicode normalization", () => {
  assert.equal(resolveTheoryDocument(docs, "  ĐẠO HÀM ".normalize("NFD"))?.id, "derivative");
  assert.equal(resolveTheoryDocument(docs, "Ứng dụng đạo hàm")?.id, "derivative");
});
test("missing or ambiguous explicit topics do not open an unrelated document", () => {
  assert.equal(resolveTheoryDocument(docs, "Hình học không gian"), null);
  assert.equal(resolveTheoryDocument([item("a", "Đạo hàm cơ bản"), item("b", "Ứng dụng đạo hàm")], "Đạo hàm"), null);
  assert.equal(resolveTheoryDocument([item("a", "Đạo hàm"), item("b", "Đạo hàm")], "Đạo hàm"), null);
});
test("opening the library without an explicit target keeps its normal first-document behavior", () => {
  assert.equal(resolveTheoryDocument(docs)?.id, "derivative");
  assert.equal(resolveTheoryDocument([], "Đạo hàm"), null);
});
