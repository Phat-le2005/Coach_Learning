import assert from "node:assert/strict";
import test from "node:test";

import { buildPaperOcrStepContent } from "../src/features/math-workspace/utils/paper-ocr-step.js";
import { renderOcrLatexHtml } from "../src/features/math-workspace/utils/ocr-math-preview.js";

test("corrected photo formula renders and is stored as LaTeX", () => {
  const content = buildPaperOcrStepContent("FORMULA", String.raw`y = \frac{1}{3}x^3 - x^2 - 3x + 1`);
  assert.equal(content?.latex, String.raw`y = \frac{1}{3}x^3 - x^2 - 3x + 1`);
  assert.equal(content?.explanation, "");
  assert.ok(renderOcrLatexHtml(content?.latex ?? "")?.includes("katex"));
});

test("plain math correction is converted before saving", () => {
  assert.deepEqual(buildPaperOcrStepContent("FORMULA", "y=(x+1)/(3)"), {
    latex: String.raw`y=\frac{x+1}{3}`, explanation: "",
  });
});

test("common OCR math delimiters are removed before rendering", () => {
  assert.equal(buildPaperOcrStepContent("FORMULA", String.raw`\(y=x^2+2\)`)?.latex, "y=x^2+2");
  assert.equal(buildPaperOcrStepContent("FORMULA", "$y=x^2+2$")?.latex, "y=x^2+2");
});

test("broken LaTeX and unfilled keypad placeholders cannot be confirmed", () => {
  assert.equal(buildPaperOcrStepContent("FORMULA", String.raw`y=\frac{1}{`), null);
  assert.equal(buildPaperOcrStepContent("FORMULA", "y=□+1"), null);
});

test("variation tables remain editable multiline evidence", () => {
  assert.deepEqual(buildPaperOcrStepContent("TABLE", "x | -1 | 3\ny' | + | -"), {
    latex: null, explanation: "x | -1 | 3\ny' | + | -",
  });
});
