"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.renderOcrLatexHtml = renderOcrLatexHtml;
const katex_1 = __importDefault(require("katex"));
/** Render untrusted OCR text only as local, non-trusted math markup. */
function renderOcrLatexHtml(latex) {
    if (!latex.trim() || latex.length > 1000)
        return null;
    try {
        return katex_1.default.renderToString(latex, {
            displayMode: false,
            output: "htmlAndMathml",
            throwOnError: true,
            trust: false,
            maxExpand: 100,
        });
    }
    catch (_a) {
        return null;
    }
}
