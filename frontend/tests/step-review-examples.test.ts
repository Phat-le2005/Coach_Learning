import assert from "node:assert/strict";
import test from "node:test";
import katex from "katex";
import { readFileSync } from "node:fs";
import { DERIVATIVE_TEST_EXAMPLES, resolveStepReviewExample, STEP_REVIEW_EXAMPLES, stepReviewSeedCommand } from "../src/features/math-workspace/utils/step-review-examples.js";

test("the original demo and source-backed Example 7 can both be selected", () => {
  assert.equal(resolveStepReviewExample(null)?.id, STEP_REVIEW_EXAMPLES[0].id);
  assert.equal(resolveStepReviewExample(STEP_REVIEW_EXAMPLES[1].id)?.label, "Ví dụ 7 · Chứng minh g(x)=x/(x−1) nghịch biến");
});

test("a submitted demo question must belong to the server allowlist", () => {
  for (const value of ["", "arbitrary-id", "c0000000-0000-0000-0000-000000000003", undefined, {}]) {
    assert.equal(resolveStepReviewExample(value), null);
  }
});

test("all ten derivative exercises match the source-backed backend pack", () => {
  const pack = JSON.parse(readFileSync("../backend/data/dev_only/derivative_step_review_10.json", "utf8"));
  assert.equal(DERIVATIVE_TEST_EXAMPLES.length, 10);
  assert.equal(new Set(STEP_REVIEW_EXAMPLES.map((x) => x.id)).size, 12);
  assert.deepEqual(DERIVATIVE_TEST_EXAMPLES.map((x) => x.id), pack.questions.map((x: { id: string }) => x.id));
  for (const example of DERIVATIVE_TEST_EXAMPLES) {
    assert.equal(resolveStepReviewExample(example.id), example);
    assert.equal(stepReviewSeedCommand(example.id), "python -m app.seed_derivative_test_pack --apply");
  }
});

test("all local problem and solution formulas render without LaTeX errors", () => {
  const pack = JSON.parse(readFileSync("../backend/data/dev_only/derivative_step_review_10.json", "utf8"));
  for (const item of pack.questions) {
    for (const field of ["content", "reference_solution"]) {
      for (const match of item[field].matchAll(/\$([^$]+)\$/g)) {
        assert.doesNotThrow(() => katex.renderToString(match[1], { throwOnError: true, trust: false }), item.id);
      }
    }
  }
});
