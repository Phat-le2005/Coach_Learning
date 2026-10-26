"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const strict_1 = __importDefault(require("node:assert/strict"));
const ocr_correction_js_1 = require("../src/features/math-workspace/utils/ocr-correction.js");
const ocr_math_preview_js_1 = require("../src/features/math-workspace/utils/ocr-math-preview.js");
(0, node_test_1.default)("student can replace one wrong OCR symbol at the cursor", () => {
    var _a;
    const edited = (0, ocr_correction_js_1.insertCorrectionKey)("y=x+7", 4, 5, "2");
    strict_1.default.deepEqual(edited, { value: "y=x+2", selectionStart: 5, selectionEnd: 5 });
    strict_1.default.ok((0, ocr_math_preview_js_1.renderOcrLatexHtml)((_a = (0, ocr_correction_js_1.toConfirmedLatex)(edited.value)) !== null && _a !== void 0 ? _a : ""));
});
(0, node_test_1.default)("math keypad offers familiar numbers, variables, operations and structures", () => {
    for (const label of ["0", "2", "9", "x", "y", "+", "−", "=", "√", "a/b", "x²", "xⁿ"]) {
        strict_1.default.ok(ocr_correction_js_1.CORRECTION_KEYS.some((key) => key.label === label));
    }
});
(0, node_test_1.default)("a selected expression fills the first template slot and selects the next", () => {
    const result = (0, ocr_correction_js_1.insertCorrectionKey)("x+1", 0, 1, "(□)/(□)");
    strict_1.default.deepEqual(result, { value: "(x)/(□)+1", selectionStart: 5, selectionEnd: 6 });
});
(0, node_test_1.default)("student notation becomes renderable LaTeX without changing arithmetic", () => {
    strict_1.default.equal((0, ocr_correction_js_1.toConfirmedLatex)("y=x+2"), "y=x+2");
    strict_1.default.equal((0, ocr_correction_js_1.toConfirmedLatex)("√(x^(2)+1)"), String.raw `\sqrt{x^{2}+1}`);
    strict_1.default.equal((0, ocr_correction_js_1.toConfirmedLatex)("(x+1)/(2x)"), String.raw `\frac{x+1}{2x}`);
    strict_1.default.equal((0, ocr_correction_js_1.toConfirmedLatex)("π×2"), String.raw `\pi \times 2`);
    strict_1.default.equal((0, ocr_correction_js_1.toConfirmedLatex)(String.raw `\frac{x+1}{2}`), String.raw `\frac{x+1}{2}`);
});
(0, node_test_1.default)("incomplete template, malformed root and empty entry cannot be saved", () => {
    strict_1.default.equal((0, ocr_correction_js_1.toConfirmedLatex)("x+□"), null);
    strict_1.default.equal((0, ocr_correction_js_1.toConfirmedLatex)("√(x+1"), null);
    strict_1.default.equal((0, ocr_correction_js_1.toConfirmedLatex)(""), null);
});
(0, node_test_1.default)("power key keeps a selected base instead of deleting it", () => {
    strict_1.default.deepEqual((0, ocr_correction_js_1.insertCorrectionKey)("x+1", 0, 1, "^2"), {
        value: "x^2+1", selectionStart: 3, selectionEnd: 3,
    });
});
