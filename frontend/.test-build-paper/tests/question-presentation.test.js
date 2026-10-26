"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const question_presentation_js_1 = require("../src/features/math-workspace/utils/question-presentation.js");
(0, node_test_1.default)("fragmented Oxyz PDF extraction is not presented as a trustworthy formula", () => {
    const raw = "Câu 10. Trong không gian Oxyz, cho đường thẳng\n2\n1\n1\n:\n1\n2\n3\nx\ny\nz\nd\n\uF02D\n\uF03D";
    strict_1.default.equal((0, question_presentation_js_1.hasBrokenMathExtraction)(raw), true);
    strict_1.default.equal((0, question_presentation_js_1.problemNeedsSourceReview)(raw, [{ content: "M(1;2;3)" }]), true);
});
(0, node_test_1.default)("a malformed option is enough to require source review", () => {
    strict_1.default.equal((0, question_presentation_js_1.problemNeedsSourceReview)("Cho điểm A thuộc d?", [{ content: "\uF028\n1;2;3\nM" }]), true);
});
(0, node_test_1.default)("ordinary LaTeX and prose remain displayable", () => {
    const latex = "Trong không gian Oxyz, cho $d: \\frac{x-2}{1}=\\frac{y-1}{2}$.";
    strict_1.default.equal((0, question_presentation_js_1.hasBrokenMathExtraction)(latex), false);
    strict_1.default.equal((0, question_presentation_js_1.hasBrokenMathExtraction)("Dòng đầu của câu hỏi.\nDòng sau tiếp tục câu hỏi."), false);
    strict_1.default.equal((0, question_presentation_js_1.problemNeedsSourceReview)(latex, [{ content: "$M(1;2;3)$" }]), false);
});
