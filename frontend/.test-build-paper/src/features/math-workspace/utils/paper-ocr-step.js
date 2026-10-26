"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.buildPaperOcrStepContent = buildPaperOcrStepContent;
const ocr_correction_1 = require("./ocr-correction");
const ocr_math_preview_1 = require("./ocr-math-preview");
/** Only valid student-edited formulas become LaTeX; tables stay multiline text. */
function buildPaperOcrStepContent(kind, text) {
    const trimmed = text.trim();
    if (!trimmed)
        return null;
    if (kind === "FORMULA") {
        const unwrapped = trimmed.startsWith("\\(") && trimmed.endsWith("\\)")
            ? trimmed.slice(2, -2).trim()
            : trimmed.startsWith("\\[") && trimmed.endsWith("\\]")
                ? trimmed.slice(2, -2).trim()
                : trimmed.startsWith("$") && trimmed.endsWith("$")
                    ? trimmed.slice(1, -1).trim() : trimmed;
        const latex = (0, ocr_correction_1.toConfirmedLatex)(unwrapped);
        return latex && (0, ocr_math_preview_1.renderOcrLatexHtml)(latex) !== null ? { latex, explanation: "" } : null;
    }
    return { latex: null, explanation: trimmed };
}
