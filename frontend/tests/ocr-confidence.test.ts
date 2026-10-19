import test from "node:test";
import assert from "node:assert/strict";
import { getOcrConfidenceDisplay } from "../src/features/math-workspace/utils/ocr-confidence.js";

test("uncalibrated OCR confidence must never be shown as 0 percent correct", () => {
  assert.deepEqual(getOcrConfidenceDisplay(0), {
    label: "Chưa có điểm tin cậy", known: false, percent: null,
  });
});
test("positive calibrated scores have explicit reference-only label", () => {
  const actual = getOcrConfidenceDisplay(0.856);
  assert.equal(actual.known, true);
  assert.equal(actual.percent, 86);
  assert.match(actual.label, /86%/);
  assert.match(actual.label, /tham khảo/);
});
test("invalid confidence is always treated as unknown", () => {
  for (const value of [-0.5, Number.NaN, Infinity]) {
    assert.equal(getOcrConfidenceDisplay(value).known, false);
  }
});
