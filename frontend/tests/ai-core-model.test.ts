import assert from "node:assert/strict";
import test from "node:test";
import type { StudentMasteryRead } from "../src/lib/api/contracts.js";
import { coreGraph, coreMasteryRows, masteryChange } from "../src/features/ai-core/model.js";

const metric = { mastery_score: 0, confidence: 0, attempt_count: 0, correct_count: 0, last_practiced_at: null, last_updated_at: null, state: "NOT_STARTED" as const };
const mastery: StudentMasteryRead = {
  student_id: "student-a", subjects: [{ ...metric, subject_id: "math", code: "MATH", name: "Toán", problem_type_count: 0, started_problem_type_count: 0, chapters: [],
    concepts: [
      { ...metric, concept_id: "unknown", subject_id: "math", code: "NEW", name: "Chưa học" },
      { ...metric, concept_id: "known", subject_id: "math", code: "DERIVATIVE", name: "Đạo hàm", attempt_count: 2, mastery_score: 0, confidence: .4, state: "WEAK" },
    ],
  }],
};
const snapshot = {
  basic_profile: { student_id: "student-a", is_synthetic: true, email: "private@example.invalid", date_of_birth: "2008-01-01" },
  knowledge_state: {
    concepts: [{ concept_id: "known", name: "Đạo hàm", prerequisites: [{ concept_id: "pre", name: "Giới hạn" }] }],
    problem_type_concept_links: [
      { problem_type_id: "problem", concept_id: "known" }, { problem_type_id: "problem", concept_id: "known" },
    ],
  },
};

test("Missing evidence stays unknown while an observed zero score remains zero", () => {
  const rows = coreMasteryRows(mastery);
  assert.equal(rows[0].id, "known");
  assert.equal(rows[0].score, 0);
  assert.equal(rows[0].confidence, .4);
  assert.equal(rows[1].score, null);
  assert.equal(rows[1].confidence, null);
});

test("Graph projection enforces student identity and excludes private profile fields", () => {
  assert.throws(() => coreGraph(snapshot, "student-b", []), /CORE_IDENTITY_MISMATCH/);
  const graph = coreGraph(snapshot, "student-a", coreMasteryRows(mastery));
  assert.equal(graph.synthetic, true);
  assert.equal(graph.concepts, 1);
  assert.equal(graph.prerequisites, 1);
  assert.equal(graph.mappings, 1);
  assert.deepEqual(graph.relations[0], { from: "Giới hạn", to: "Đạo hàm", kind: "Tiên quyết" });
  assert.equal(JSON.stringify(graph).includes("private@example.invalid"), false);
  assert.equal(JSON.stringify(graph).includes("2008-01-01"), false);
});

test("A broken graph contract fails instead of becoming a fabricated empty graph", () => {
  assert.throws(() => coreGraph({ basic_profile: snapshot.basic_profile, knowledge_state: {} }, "student-a", []), /INVALID_CORE_SNAPSHOT/);
});

test("Before/after mastery deltas require evidence at both checkpoints", () => {
  assert.equal(masteryChange(null, .4), null);
  assert.equal(masteryChange(undefined, .4), null);
  assert.equal(masteryChange(.4, null), null);
  assert.equal(masteryChange(.4, .52), 12);
  assert.equal(masteryChange(.5, .4), -10);
});
