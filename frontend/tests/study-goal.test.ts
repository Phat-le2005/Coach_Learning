import test from "node:test";
import assert from "node:assert/strict";
import { studyGoalPayload } from "../src/features/student-home/study-goal.js";

test("a missing goal date cannot silently become a fixed exam", () => {
  assert.throws(() => studyGoalPayload({ subject_id: "subject" }), /mốc hoàn thành/i);
});
test("invalid calendar dates are rejected rather than normalized to a different month", () => {
  for (const exam_date of ["2027-02-30", "invalid", "2027-13-01"]) assert.throws(() => studyGoalPayload({ exam_date }));
});
test("explicit goal metadata and a real zero current score are preserved", () => {
  const payload = studyGoalPayload({ exam_date: "2027-06-20", target_exam: "Mục tiêu của tôi", subject_id: "subject", current_score: 0, target_score: 7 });
  assert.equal(payload.exam_date, "2027-06-20");
  assert.equal(payload.target_exam, "Mục tiêu của tôi");
  assert.equal(payload.subject_goals[0].current_score, 0);
  assert.equal(studyGoalPayload({ exam_date: "2027-06-20" }).target_exam, "Mục tiêu học tập cá nhân");
});
