import test from "node:test";
import assert from "node:assert/strict";
import { renderOcrLatexHtml } from "../src/features/math-workspace/utils/ocr-math-preview.js";

test("OCR suggestion renders visible math for student review", () => {
  const html = renderOcrLatexHtml(String.raw`\frac{x^2+1}{2}`);
  assert.ok(html);
  assert.match(html, /katex/);
  assert.match(html, /math/);
});

test("unsupported or excessive OCR markup cannot create trusted links", () => {
  const blockedLink = renderOcrLatexHtml(String.raw`\href{javascript:alert(1)}{x}`);
  assert.ok(blockedLink);
  assert.doesNotMatch(blockedLink, /href="javascript:/);
  assert.equal(renderOcrLatexHtml("x".repeat(1001)), null);
  assert.equal(renderOcrLatexHtml(String.raw`\unknowncommand{x}`), null);
});

test("unrenderable OCR output is rejected before student confirmation", () => {
  assert.equal(renderOcrLatexHtml(String.raw`\widehat{\mathbf{v}}} = \mathcal{v}`), null);
  assert.ok(renderOcrLatexHtml("y=x+2"));
});
