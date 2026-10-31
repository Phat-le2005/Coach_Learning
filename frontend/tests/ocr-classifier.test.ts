import test from "node:test";
import assert from "node:assert/strict";
import {
  classifyMathStep,
  type StepClassificationInput,
} from "../src/features/math-workspace/utils/ocr-classifier.js";

// ---------------------------------------------------------------------------
// 1. Assumption / Domain Tests
// ---------------------------------------------------------------------------
test("classifies explicit domain and assumption statements", () => {
  const cases: StepClassificationInput[] = [
    { contentLatex: "D = \\mathbb{R}", explanationText: "Tập xác định" },
    { contentLatex: "x \\neq 1", explanationText: "Điều kiện xác định: mẫu số khác 0" },
    { contentLatex: "D = (0; +\\infty)", explanationText: "TXĐ của hàm số" },
    { contentLatex: "x > 0", explanationText: "ĐK: biểu thức trong căn dương" },
    { contentLatex: "D = R \\setminus \\{2\\}", explanationText: "" },
  ];

  for (const tc of cases) {
    const res = classifyMathStep(tc);
    assert.equal(res.status, "DETERMINED");
    assert.equal(res.predictedType, "ASSUMPTION");
    assert.equal(res.ruleId, "RULE_ASSUMPTION_DOMAIN");
    assert.ok(res.matchedEvidence.length > 0);
  }
});

// ---------------------------------------------------------------------------
// 2. Derivative Calculation Tests
// ---------------------------------------------------------------------------
test("classifies derivative calculations and preserves student mathematical mistakes", () => {
  const cases: StepClassificationInput[] = [
    { contentLatex: "y' = 3x^2 - 6x", explanationText: "Tính đạo hàm" },
    { contentLatex: "f'(x) = 4x^3 - 4x = 4x(x^2 - 1)", explanationText: "" },
    { contentLatex: "y' = \\frac{x^2 - 2x}{(x - 1)^2}", explanationText: "Đạo hàm hàm phân thức" },
    { contentLatex: "\\frac{dy}{dx} = 2x + 1", explanationText: "" },
    // Crucial: Student math error (wrong sign) must still be classified as DERIVATIVE_CALCULATION!
    { contentLatex: "y' = 3x^2 + 6x", explanationText: "Học sinh tính sai dấu đạo hàm" },
    { contentLatex: "g'(x) = -3x^2 + 6x - 3", explanationText: "" },
  ];

  for (const tc of cases) {
    const res = classifyMathStep(tc);
    assert.equal(res.status, "DETERMINED");
    assert.equal(res.predictedType, "DERIVATIVE_CALCULATION");
    assert.equal(res.ruleId, "RULE_DERIVATIVE_CALCULATION");
    assert.ok(res.matchedEvidence.length > 0);
  }
});

// ---------------------------------------------------------------------------
// 3. Root Finding Tests
// ---------------------------------------------------------------------------
test("classifies root finding equations and critical point solutions", () => {
  const cases: StepClassificationInput[] = [
    { contentLatex: "y' = 0 \\Leftrightarrow 3x^2 - 6x = 0 \\Leftrightarrow x = 0 \\lor x = 2", explanationText: "" },
    { contentLatex: "f'(x) = 0 \\Leftrightarrow x = 1", explanationText: "Tìm nghiệm đạo hàm" },
    { contentLatex: "3x^2 - 6x = 0", explanationText: "Giải phương trình" },
    { contentLatex: "\\Leftrightarrow x = -1 \\lor x = 3", explanationText: "" },
    { contentLatex: "x_1 = 0, x_2 = 2", explanationText: "Các điểm dừng" },
    // Student math mistake in roots
    { contentLatex: "y' = 0 \\Leftrightarrow x = 0 \\lor x = -2", explanationText: "Nghiệm sai" },
    { contentLatex: "x \\in \\{0, 2\\}", explanationText: "Tập nghiệm của y' = 0" },
  ];

  for (const tc of cases) {
    const res = classifyMathStep(tc);
    assert.equal(res.status, "DETERMINED");
    assert.equal(res.predictedType, "ROOT_FINDING");
    assert.ok(res.ruleId.startsWith("RULE_ROOT_FINDING"));
    assert.ok(res.matchedEvidence.length > 0);
  }
});

// ---------------------------------------------------------------------------
// 4. Conclusion Tests
// ---------------------------------------------------------------------------
test("classifies monotonicity, extrema and asymptote conclusions", () => {
  const cases: StepClassificationInput[] = [
    { contentLatex: "", explanationText: "Hàm số đồng biến trên khoảng (0; 2) và nghịch biến trên (-oo; 0)" },
    { contentLatex: "", explanationText: "Vậy hàm số đạt cực đại tại x = 0, giá trị cực đại y_CĐ = 2" },
    { contentLatex: "", explanationText: "Do đó đồ thị hàm số có tiệm cận đứng x = 1" },
    { contentLatex: "y_{cđ} = 5", explanationText: "Kết luận điểm cực đại" },
    { contentLatex: "", explanationText: "Kết luận: hàm số nghịch biến trên R" },
  ];

  for (const tc of cases) {
    const res = classifyMathStep(tc);
    assert.equal(res.status, "DETERMINED");
    assert.equal(res.predictedType, "CONCLUSION");
    assert.equal(res.ruleId, "RULE_CONCLUSION_MONOTONICITY");
    assert.ok(res.matchedEvidence.length > 0);
  }
});

// ---------------------------------------------------------------------------
// 5. Sign Table & Variation Table Keyword Tests
// ---------------------------------------------------------------------------
test("classifies table keyword references without synthesizing fake artifacts", () => {
  const signCases: StepClassificationInput[] = [
    { contentLatex: "", explanationText: "Lập bảng xét dấu của y'" },
    { contentLatex: "", explanationText: "Theo BXĐ ta thấy y' đổi dấu từ dương sang âm" },
  ];
  for (const tc of signCases) {
    const res = classifyMathStep(tc);
    assert.equal(res.status, "DETERMINED");
    assert.equal(res.predictedType, "SIGN_TABLE");
    assert.equal(res.ruleId, "RULE_SIGN_TABLE");
  }

  const varCases: StepClassificationInput[] = [
    { contentLatex: "", explanationText: "Bảng biến thiên của hàm số đã cho" },
    { contentLatex: "", explanationText: "Lập BBT trên tập xác định" },
  ];
  for (const tc of varCases) {
    const res = classifyMathStep(tc);
    assert.equal(res.status, "DETERMINED");
    assert.equal(res.predictedType, "VARIATION_TABLE");
    assert.equal(res.ruleId, "RULE_VARIATION_TABLE");
  }
});

// ---------------------------------------------------------------------------
// 6. Verbal Explanation Tests
// ---------------------------------------------------------------------------
test("classifies verbal explanation statements without specific formulas", () => {
  const cases: StepClassificationInput[] = [
    { contentLatex: "", explanationText: "Vì tam thức bậc hai có hệ số a = 1 > 0 nên bề lõm quay lên" },
    { contentLatex: "", explanationText: "Áp dụng định lý Lagrange trên đoạn [0, 2]" },
    { contentLatex: "", explanationText: "Ta có đạo hàm không đổi dấu trên khoảng này" },
    { contentLatex: "", explanationText: "Theo bài ra ta có đồ thị đi qua gốc tọa độ" },
  ];

  for (const tc of cases) {
    const res = classifyMathStep(tc);
    assert.equal(res.status, "DETERMINED");
    assert.equal(res.predictedType, "EXPLANATION");
    assert.equal(res.ruleId, "RULE_EXPLANATION_VERBAL_PROSE");
  }
});

// ---------------------------------------------------------------------------
// 7. Empty & Incomplete Input (ABSTAIN)
// ---------------------------------------------------------------------------
test("abstains on empty, whitespace-only, or null input", () => {
  const emptyInputs: StepClassificationInput[] = [
    {},
    { contentLatex: "" },
    { explanationText: "" },
    { contentLatex: "   ", explanationText: "   " },
    { contentLatex: null, explanationText: null },
  ];

  for (const inp of emptyInputs) {
    const res = classifyMathStep(inp);
    assert.equal(res.status, "ABSTAIN");
    assert.equal(res.predictedType, null);
    assert.equal(res.ruleId, null);
    assert.ok(res.reason.includes("trống"));
  }
});

// ---------------------------------------------------------------------------
// 8. Incomplete Expressions & Dangling Operators (ABSTAIN)
// ---------------------------------------------------------------------------
test("abstains on expressions ending with dangling operators", () => {
  const dangling: StepClassificationInput[] = [
    { contentLatex: "y' = 3x^2 +" },
    { contentLatex: "f'(x) = 2x -" },
    { contentLatex: "x =" },
    { contentLatex: "3x^2 /" },
  ];

  for (const inp of dangling) {
    const res = classifyMathStep(inp);
    assert.equal(res.status, "ABSTAIN");
    assert.equal(res.predictedType, null);
    assert.ok(res.reason.includes("toán tử"));
  }
});

// ---------------------------------------------------------------------------
// 9. Isolated Ambiguous Equations (ABSTAIN)
// ---------------------------------------------------------------------------
test("adversarial: isolated x = 2 without context must abstain", () => {
  // An isolated "x = 2" could be a root, a vertical asymptote, a domain point, or a constant
  const isolated = classifyMathStep({ contentLatex: "x = 2" });
  assert.equal(isolated.status, "ABSTAIN");
  assert.equal(isolated.predictedType, null);
  assert.ok(isolated.reason.includes("đơn độc"));

  const isolatedY = classifyMathStep({ contentLatex: "y = 5" });
  assert.equal(isolatedY.status, "ABSTAIN");
});

test("adversarial: isolated inequality x > 0 without domain keyword must abstain", () => {
  // An isolated "x > 0" could be an intermediate inequality solution, not a domain assumption
  const isolatedIneq = classifyMathStep({ contentLatex: "x > 0" });
  assert.equal(isolatedIneq.status, "ABSTAIN");
  assert.equal(isolatedIneq.predictedType, null);
});

// ---------------------------------------------------------------------------
// 10. Conflicting Rules & Multi-Step Descriptions (ABSTAIN)
// ---------------------------------------------------------------------------
test("adversarial: multi-step plan descriptions must abstain", () => {
  const multiStepInputs: StepClassificationInput[] = [
    { contentLatex: "", explanationText: "Tính đạo hàm rồi xét dấu trên trục số" },
    { contentLatex: "", explanationText: "Tìm nghiệm và lập bảng biến thiên của hàm số" },
    { contentLatex: "", explanationText: "Xét dấu sau đó kết luận cực trị" },
  ];

  for (const inp of multiStepInputs) {
    const res = classifyMathStep(inp);
    assert.equal(res.status, "ABSTAIN");
    assert.equal(res.predictedType, null);
    assert.ok(res.reason.includes("nhiều bước giải"));
  }
});

// ---------------------------------------------------------------------------
// 11. OCR Noise & Malformed LaTeX (ABSTAIN)
// ---------------------------------------------------------------------------
test("abstains on malformed LaTeX with unbalanced braces", () => {
  const malformed: StepClassificationInput[] = [
    { contentLatex: "\\frac{3x^2 - 6x}{" },
    { contentLatex: "y' = 3x^{2" },
    { contentLatex: "x \\in \\{0, 2" },
  ];

  for (const inp of malformed) {
    const res = classifyMathStep(inp);
    assert.equal(res.status, "ABSTAIN");
    assert.equal(res.predictedType, null);
    assert.ok(res.reason.includes("ngoặc nhọn"));
  }
});

// ---------------------------------------------------------------------------
// 12. Isolated Raw Expressions without Context (ABSTAIN)
// ---------------------------------------------------------------------------
test("adversarial: raw polynomial expression without equals sign must abstain", () => {
  // Just "3x^2 - 6x" with no LHS is not explicitly a calculation or root finding
  const raw = classifyMathStep({ contentLatex: "3x^2 - 6x" });
  assert.equal(raw.status, "ABSTAIN");
  assert.equal(raw.predictedType, null);
});

// ---------------------------------------------------------------------------
// 13. Derivative vs Root Finding Disambiguation
// ---------------------------------------------------------------------------
test("adversarial: f'(x) = 0 is classified as ROOT_FINDING, not DERIVATIVE_CALCULATION", () => {
  const derivZero = classifyMathStep({ contentLatex: "f'(x) = 0" });
  assert.equal(derivZero.status, "DETERMINED");
  assert.equal(derivZero.predictedType, "ROOT_FINDING");
  assert.equal(derivZero.ruleId, "RULE_ROOT_FINDING_DERIVATIVE_ZERO");

  const yPrimeZero = classifyMathStep({ contentLatex: "y' = 0" });
  assert.equal(yPrimeZero.status, "DETERMINED");
  assert.equal(yPrimeZero.predictedType, "ROOT_FINDING");
});

// ---------------------------------------------------------------------------
// 14. Determinism Test
// ---------------------------------------------------------------------------
test("determinism: 100 repeated invocations return strictly identical results", () => {
  const input: StepClassificationInput = {
    contentLatex: "y' = 3x^2 - 6x",
    explanationText: "Tính đạo hàm của hàm số bậc ba",
  };
  const baseline = classifyMathStep(input);

  for (let i = 0; i < 100; i++) {
    const next = classifyMathStep(input);
    assert.deepEqual(next, baseline);
  }
});

// ---------------------------------------------------------------------------
// 15. Input Immutability Test
// ---------------------------------------------------------------------------
test("input immutability: classifyMathStep does not modify input object or fields", () => {
  const input: StepClassificationInput = Object.freeze({
    contentLatex: "y' = 3x^2 - 6x",
    explanationText: "Đạo hàm",
  });
  const copy = { ...input };

  const res = classifyMathStep(input);
  assert.equal(res.status, "DETERMINED");
  assert.deepEqual(input, copy);
});

// ---------------------------------------------------------------------------
// 16. Long Input Safety (ReDoS Protection)
// ---------------------------------------------------------------------------
test("long input safety: large text (>4000 chars) abstains gracefully without hanging", () => {
  const hugeText = "y' = 3x^2 ".repeat(500); // 5000 chars
  const t0 = performance.now();
  const res = classifyMathStep({ contentLatex: hugeText });
  const t1 = performance.now();

  assert.equal(res.status, "ABSTAIN");
  assert.ok(t1 - t0 < 50, "Long input should return in under 50ms without catastrophic backtracking");
  assert.ok(res.reason.includes("giới hạn an toàn"));
});

// ---------------------------------------------------------------------------
// 17. Word Boundary Precision
// ---------------------------------------------------------------------------
test("adversarial: single words like 'tăng' or 'cực trị' alone do not trigger CONCLUSION", () => {
  // A sentence like "x tăng thì y giảm" or "tìm cực trị" is not a definitive conclusion
  const res = classifyMathStep({ explanationText: "x tăng thì hàm số biến thiên" });
  assert.notEqual(res.predictedType, "CONCLUSION");
});
