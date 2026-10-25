import assert from "node:assert/strict";
import test from "node:test";

import { hasBrokenMathExtraction, problemNeedsSourceReview } from "../src/features/math-workspace/utils/question-presentation.js";

test("fragmented Oxyz PDF extraction is not presented as a trustworthy formula", () => {
  const raw = "Câu 10. Trong không gian Oxyz, cho đường thẳng\n2\n1\n1\n:\n1\n2\n3\nx\ny\nz\nd\n\uF02D\n\uF03D";
  assert.equal(hasBrokenMathExtraction(raw), true);
  assert.equal(problemNeedsSourceReview(raw, [{ content: "M(1;2;3)" }]), true);
});

test("a malformed option is enough to require source review", () => {
  assert.equal(problemNeedsSourceReview("Cho điểm A thuộc d?", [{ content: "\uF028\n1;2;3\nM" }]), true);
});

test("ordinary LaTeX and prose remain displayable", () => {
  const latex = "Trong không gian Oxyz, cho $d: \\frac{x-2}{1}=\\frac{y-1}{2}$.";
  assert.equal(hasBrokenMathExtraction(latex), false);
  assert.equal(hasBrokenMathExtraction("Dòng đầu của câu hỏi.\nDòng sau tiếp tục câu hỏi."), false);
  assert.equal(problemNeedsSourceReview(latex, [{ content: "$M(1;2;3)$" }]), false);
});
