import assert from "node:assert/strict";
import test from "node:test";

import { parseSolutionAttemptRead, parseVariationTablePayload } from "../src/lib/api/contracts.js";
import { addVariationPoint, createVariationTableDraft, removeVariationPoint,
  toVariationTablePayload, trendForSign, validateVariationTable } from "../src/features/math-workspace/utils/variation-table.js";

test("empty table contains no invented mathematics", () => {
  const draft = createVariationTableDraft();
  assert.equal(draft.points.length, 3);
  assert.ok(draft.points.every((point) => point.x === "" && point.y === ""));
  assert.ok(draft.intervals.every((interval) => interval.sign === ""));
  assert.equal(validateVariationTable(draft), "TABLE_X_REQUIRED_OR_DUPLICATE");
});

test("student signs deterministically draw matching arrows", () => {
  assert.equal(trendForSign("+"), "UP");
  assert.equal(trendForSign("-"), "DOWN");
  assert.equal(trendForSign("0"), "FLAT");
  const draft = createVariationTableDraft();
  draft.points.forEach((point, index) => { point.x = ["-inf", "a", "+inf"][index]; });
  draft.intervals[0] = { sign: "+", trend: trendForSign("+") };
  draft.intervals[1] = { sign: "-", trend: trendForSign("-") };
  assert.equal(validateVariationTable(draft), null);
  assert.deepEqual(parseVariationTablePayload(toVariationTablePayload(draft)).intervals,
    [{ sign: "+", trend: "UP" }, { sign: "-", trend: "DOWN" }]);
});

test("adding and removing a critical point preserves aligned columns", () => {
  const draft = createVariationTableDraft();
  const added = addVariationPoint(draft);
  assert.equal(added.points.length, 4);
  assert.equal(added.intervals.length, 3);
  assert.equal(removeVariationPoint(added).points.length, 3);
  assert.equal(removeVariationPoint(added).intervals.length, 2);
});

test("duplicate x and sign-arrow conflicts are not accepted", () => {
  const draft = createVariationTableDraft();
  draft.points.forEach((point) => { point.x = "same"; });
  assert.equal(validateVariationTable(draft), "TABLE_X_REQUIRED_OR_DUPLICATE");
  draft.points.forEach((point, index) => { point.x = String(index); });
  draft.intervals[0] = { sign: "+", trend: "DOWN" };
  draft.intervals[1] = { sign: "-", trend: "DOWN" };
  assert.equal(validateVariationTable(draft), "TABLE_SIGNS_REQUIRED");
  assert.throws(() => parseVariationTablePayload({ version: 1, points: [], intervals: [] }));
});

test("saved variation table survives attempt reload as structured artifact", () => {
  const draft = createVariationTableDraft();
  draft.points.forEach((point, index) => { point.x = ["left", "middle", "right"][index]; });
  draft.intervals[0] = { sign: "+", trend: "UP" };
  draft.intervals[1] = { sign: "-", trend: "DOWN" };
  const payload = toVariationTablePayload(draft);
  const attempt = parseSolutionAttemptRead({ id: "attempt", question_id: "question", status: "IN_PROGRESS",
    attempt_revision_number: 2, started_at: "2026-10-25T00:00:00Z", steps: [{
      id: "step", step_index: 1, step_type: "VARIATION_TABLE", content_latex: null,
      explanation_text: null, step_revision_number: 1,
      artifact: { artifact_type: "VARIATION_TABLE", payload },
    }] });
  assert.deepEqual(parseVariationTablePayload(attempt.steps?.[0].artifact?.payload), payload);
});
