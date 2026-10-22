import test from "node:test";
import assert from "node:assert/strict";
import { CORRECTION_KEYS, insertCorrectionKey, toConfirmedLatex } from "../src/features/math-workspace/utils/ocr-correction.js";
import { renderOcrLatexHtml } from "../src/features/math-workspace/utils/ocr-math-preview.js";

test("student can replace one wrong OCR symbol at the cursor", () => {
  const edited = insertCorrectionKey("y=x+7", 4, 5, "2");
  assert.deepEqual(edited, { value: "y=x+2", selectionStart: 5, selectionEnd: 5 });
  assert.ok(renderOcrLatexHtml(toConfirmedLatex(edited.value) ?? ""));
});

test("math keypad offers familiar numbers, variables, operations and structures", () => {
  for (const label of ["0", "2", "9", "x", "y", "+", "−", "=", "√", "a/b", "x²", "xⁿ"]) {
    assert.ok(CORRECTION_KEYS.some((key) => key.label === label));
  }
});

test("a selected expression fills the first template slot and selects the next", () => {
  const result = insertCorrectionKey("x+1", 0, 1, "(□)/(□)");
  assert.deepEqual(result, { value: "(x)/(□)+1", selectionStart: 5, selectionEnd: 6 });
});

test("student notation becomes renderable LaTeX without changing arithmetic", () => {
  assert.equal(toConfirmedLatex("y=x+2"), "y=x+2");
  assert.equal(toConfirmedLatex("√(x^(2)+1)"), String.raw`\sqrt{x^{2}+1}`);
  assert.equal(toConfirmedLatex("(x+1)/(2x)"), String.raw`\frac{x+1}{2x}`);
  assert.equal(toConfirmedLatex("π×2"), String.raw`\pi \times 2`);
  assert.equal(toConfirmedLatex(String.raw`\frac{x+1}{2}`), String.raw`\frac{x+1}{2}`);
});

test("incomplete template, malformed root and empty entry cannot be saved", () => {
  assert.equal(toConfirmedLatex("x+□"), null);
  assert.equal(toConfirmedLatex("√(x+1"), null);
  assert.equal(toConfirmedLatex(""), null);
});

test("power key keeps a selected base instead of deleting it", () => {
  assert.deepEqual(insertCorrectionKey("x+1", 0, 1, "^2"), {
    value: "x^2+1", selectionStart: 3, selectionEnd: 3,
  });
});
