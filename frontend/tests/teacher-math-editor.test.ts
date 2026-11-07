import test from "node:test";
import assert from "node:assert/strict";
import katex from "katex";
import { splitMathText } from "../src/features/teacher/math-text.js";
import { MATH_SYMBOL_GROUPS, QUICK_MATH_KEYS, searchMathSymbols } from "../src/features/teacher/math-symbols.js";

test("editing prose preserves OCR formula delimiters, whitespace and unsupported input", () => {
  const content = String.raw`Gọi $A$ là biến cố.  
Đáp án: \(P(A)=0{,}18\), $$\frac{3}{10}$$ và \[\sqrt{x}\].
Giá \$5; mã lỗi $\unknown{x}$; công thức chưa khép $x`;
  const parts = splitMathText(content);
  assert.equal(parts.map((p) => p.raw).join(""), content);
  assert.deepEqual(parts.filter((p) => p.kind === "math").map((p) => [p.latex, p.open, p.close, p.display]), [
    ["A", "$", "$", false], [String.raw`P(A)=0{,}18`, String.raw`\(`, String.raw`\)`, false],
    [String.raw`\frac{3}{10}`, "$$", "$$", true], [String.raw`\sqrt{x}`, String.raw`\[`, String.raw`\]`, true],
    [String.raw`\unknown{x}`, "$", "$", false],
  ]);
});

test("escaped delimiters stay literal and an escaped dollar does not close a formula", () => {
  for (const value of ["", "Văn bản tiếng Việt\n\n", String.raw`\$5 và \\(x\\)`, "$x chưa hoàn tất"]) {
    assert.equal(splitMathText(value).map((p) => p.raw).join(""), value);
    assert.ok(splitMathText(value).every((p) => p.kind === "text"));
  }
  const parts = splitMathText(String.raw`$x+\$5$ và $y$`);
  assert.deepEqual(parts.filter((p) => p.kind === "math").map((p) => p.latex), [String.raw`x+\$5`, "y"]);
});

test("every palette symbol has a unique id and valid renderable display and insertion template", () => {
  const symbols = [...MATH_SYMBOL_GROUPS.flatMap((g) => g.symbols), ...QUICK_MATH_KEYS];
  assert.ok(symbols.length > 200);
  assert.equal(new Set(symbols.map((s) => s.id)).size, symbols.length);
  for (const symbol of symbols) {
    for (const value of [symbol.latex, symbol.insert.replace(/#(?:0|\?)/g, "x")]) {
      assert.doesNotThrow(() => katex.renderToString(value, { throwOnError: true, trust: false, strict: "ignore" }), symbol.id);
    }
  }
});

test("teachers can search names with accents, unaccented names, LaTeX names and lambda misspellings", () => {
  for (const query of ["lambda", "/landa", "\\lambda", "lam đa"]) {
    assert.ok(searchMathSymbols(query, "common").some((s) => s.id === "greek-lambda"), query);
  }
  for (const [query, id] of [["tich phan", "definite-integral"], ["đạo hàm", "derivative"], ["can bac", "sqrt"], ["sigma", "greek-sigma"], ["Sigma hoa", "greek-upper-Sigma"]]) {
    assert.ok(searchMathSymbols(query, "common").some((s) => s.id === id), query);
  }
  assert.equal(searchMathSymbols("  ", "greek").length, MATH_SYMBOL_GROUPS.find((g) => g.id === "greek")!.symbols.length);
  assert.deepEqual(searchMathSymbols("khong-co-ky-hieu-nay", "common"), []);
});
