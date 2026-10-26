"use strict";
var __makeTemplateObject = (this && this.__makeTemplateObject) || function (cooked, raw) {
    if (Object.defineProperty) { Object.defineProperty(cooked, "raw", { value: raw }); } else { cooked.raw = raw; }
    return cooked;
};
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const strict_1 = __importDefault(require("node:assert/strict"));
const ocr_math_preview_js_1 = require("../src/features/math-workspace/utils/ocr-math-preview.js");
(0, node_test_1.default)("OCR suggestion renders visible math for student review", () => {
    const html = (0, ocr_math_preview_js_1.renderOcrLatexHtml)(String.raw `\frac{x^2+1}{2}`);
    strict_1.default.ok(html);
    strict_1.default.match(html, /katex/);
    strict_1.default.match(html, /math/);
});
(0, node_test_1.default)("unsupported or excessive OCR markup cannot create trusted links", () => {
    const blockedLink = (0, ocr_math_preview_js_1.renderOcrLatexHtml)(String.raw `\href{javascript:alert(1)}{x}`);
    strict_1.default.ok(blockedLink);
    strict_1.default.doesNotMatch(blockedLink, /href="javascript:/);
    strict_1.default.equal((0, ocr_math_preview_js_1.renderOcrLatexHtml)("x".repeat(1001)), null);
    strict_1.default.equal((0, ocr_math_preview_js_1.renderOcrLatexHtml)(String.raw(templateObject_1 || (templateObject_1 = __makeTemplateObject([void 0], ["\\unknowncommand{x}"])))), null);
});
(0, node_test_1.default)("unrenderable OCR output is rejected before student confirmation", () => {
    strict_1.default.equal((0, ocr_math_preview_js_1.renderOcrLatexHtml)(String.raw `\widehat{\mathbf{v}}} = \mathcal{v}`), null);
    strict_1.default.ok((0, ocr_math_preview_js_1.renderOcrLatexHtml)("y=x+2"));
});
var templateObject_1;
