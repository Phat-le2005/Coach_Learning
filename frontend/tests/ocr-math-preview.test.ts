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

test("multiline Gemini transcription preserves separate equations and nested tables", () => {
  const html = renderOcrLatexHtml(String.raw`y' = 3x^2 - 3
y' = 0 \Leftrightarrow 3x^2 - 3 = 0
\begin{cases}
x = 1 \\
x = -1
\end{cases}
\begin{array}{c|ccccc}
x & -\infty & -1 & 0 & 1 & +\infty \\
y' & + & 0 & - & 0 & +
\end{array}`);
  assert.ok(html);
  assert.match(html, /katex-display/);
  assert.match(html, /mtable/);
  assert.doesNotMatch(html, /katex-error/);
  assert.ok((html.match(/<mtr>/g) ?? []).length >= 8);
});

test("line breaks within a fraction stay within the same expression", () => {
  const html = renderOcrLatexHtml("y = \\frac{1\n+ x}{2}\ny = 3");
  assert.ok(html);
  assert.match(html, /mfrac/);
  assert.match(html, /mtable/);
});
