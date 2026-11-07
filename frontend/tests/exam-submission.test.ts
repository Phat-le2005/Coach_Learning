import assert from "node:assert/strict";
import test from "node:test";

import { getExamMissingQuestions } from "../src/features/math-workspace/utils/exam-submission.js";
import { matchesClassroomAttempt } from "../src/features/math-workspace/utils/classroom-attempt-match.js";

test("exam counts confirmed questions or questions with steps", () => {
  const questions = Array.from({ length: 10 }, (_, index) => ({
    index,
    attemptId: `attempt-${index}`,
    status: index === 9 ? "IN_PROGRESS" : "SUBMITTED",
  }));
  assert.deepEqual(getExamMissingQuestions(questions, "attempt-9", "IN_PROGRESS").map((item) => item.index), [9]);
  assert.deepEqual(getExamMissingQuestions(questions, "attempt-9", "IN_PROGRESS", true), []);
  assert.deepEqual(getExamMissingQuestions(questions, "attempt-9", "SUBMITTED"), []);
  assert.deepEqual(getExamMissingQuestions(questions, "attempt-0", "IN_PROGRESS").map((item) => item.index), [0, 9]);

  const questionsWithSteps = Array.from({ length: 10 }, (_, index) => ({
    index,
    attemptId: `attempt-${index}`,
    status: "IN_PROGRESS",
    stepCount: index === 0 ? 3 : 0,
  }));
  // index 0 has stepCount=3, so only 1..9 are missing
  assert.deepEqual(
    getExamMissingQuestions(questionsWithSteps, "attempt-9", "IN_PROGRESS").map((item) => item.index),
    [1, 2, 3, 4, 5, 6, 7, 8, 9]
  );
});

test("exam counts pre-answered questions or text responses as completed", () => {
  const questions = Array.from({ length: 10 }, (_, index) => ({
    index,
    attemptId: null,
    status: "NOT_STARTED",
    studentAnswer: index < 5 ? "A" : null,
    hasAnswer: index < 5,
  }));
  const missing = getExamMissingQuestions(questions, "none", "NOT_STARTED");
  assert.deepEqual(missing.map((q) => q.index), [5, 6, 7, 8, 9]);
});

test("missing IDs never attach all questions to the same attempt", () => {
  assert.equal(matchesClassroomAttempt({ id: "item-2", source_kind: "TEACHER_MATERIAL" },
    { id: "attempt-1", student_assignment_material_item_id: "item-1" }), false);
  assert.equal(matchesClassroomAttempt({ id: "item-2", source_kind: "TEACHER_MATERIAL" },
    { id: "attempt-2", student_assignment_material_item_id: "item-2" }), true);
  assert.equal(matchesClassroomAttempt({ id: "question-2", source_kind: "CANONICAL" },
    { id: "attempt-1", question_id: "question-1" }), false);
  assert.equal(matchesClassroomAttempt({ source_kind: "TEACHER_MATERIAL_ITEM", student_material_item_id: "item-2" },
    { id: "attempt-2", student_assignment_material_item_id: "item-2" }), true);
  assert.equal(matchesClassroomAttempt({ question_id: "question-2" },
    { id: "attempt-2", question_id: "question-2" }), true);
  assert.equal(matchesClassroomAttempt({}, {}), false);
});
