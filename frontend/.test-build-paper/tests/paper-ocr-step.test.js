"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const paper_ocr_step_js_1 = require("../src/features/math-workspace/utils/paper-ocr-step.js");
const ocr_math_preview_js_1 = require("../src/features/math-workspace/utils/ocr-math-preview.js");
(0, node_test_1.default)("corrected photo formula renders and is stored as LaTeX", () => {
    var _a, _b;
    const content = (0, paper_ocr_step_js_1.buildPaperOcrStepContent)("FORMULA", String.raw `y = \frac{1}{3}x^3 - x^2 - 3x + 1`);
    strict_1.default.equal(content === null || content === void 0 ? void 0 : content.latex, String.raw `y = \frac{1}{3}x^3 - x^2 - 3x + 1`);
    strict_1.default.equal(content === null || content === void 0 ? void 0 : content.explanation, "");
    strict_1.default.ok((_b = (0, ocr_math_preview_js_1.renderOcrLatexHtml)((_a = content === null || content === void 0 ? void 0 : content.latex) !== null && _a !== void 0 ? _a : "")) === null || _b === void 0 ? void 0 : _b.includes("katex"));
});
(0, node_test_1.default)("plain math correction is converted before saving", () => {
    strict_1.default.deepEqual((0, paper_ocr_step_js_1.buildPaperOcrStepContent)("FORMULA", "y=(x+1)/(3)"), {
        latex: String.raw `y=\frac{x+1}{3}`, explanation: "",
    });
});
(0, node_test_1.default)("common OCR math delimiters are removed before rendering", () => {
    var _a, _b;
    strict_1.default.equal((_a = (0, paper_ocr_step_js_1.buildPaperOcrStepContent)("FORMULA", String.raw `\(y=x^2+2\)`)) === null || _a === void 0 ? void 0 : _a.latex, "y=x^2+2");
    strict_1.default.equal((_b = (0, paper_ocr_step_js_1.buildPaperOcrStepContent)("FORMULA", "$y=x^2+2$")) === null || _b === void 0 ? void 0 : _b.latex, "y=x^2+2");
});
(0, node_test_1.default)("broken LaTeX and unfilled keypad placeholders cannot be confirmed", () => {
    strict_1.default.equal((0, paper_ocr_step_js_1.buildPaperOcrStepContent)("FORMULA", String.raw `y=\frac{1}{`), null);
    strict_1.default.equal((0, paper_ocr_step_js_1.buildPaperOcrStepContent)("FORMULA", "y=□+1"), null);
});
(0, node_test_1.default)("variation tables remain editable multiline evidence", () => {
    strict_1.default.deepEqual((0, paper_ocr_step_js_1.buildPaperOcrStepContent)("TABLE", "x | -1 | 3\ny' | + | -"), {
        latex: null, explanation: "x | -1 | 3\ny' | + | -",
    });
});
