import type { PaperOcrSuggestion } from "@/lib/api/client";

import { toConfirmedLatex } from "./ocr-correction";
import { renderOcrLatexHtml } from "./ocr-math-preview";

export interface ConfirmedPaperStepContent {
  latex: string | null;
  explanation: string;
}

/** Only valid student-edited formulas become LaTeX; tables stay multiline text. */
export function buildPaperOcrStepContent(
  kind: PaperOcrSuggestion["kind"], text: string,
): ConfirmedPaperStepContent | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  if (kind === "FORMULA") {
    const unwrapped = trimmed.startsWith("\\(") && trimmed.endsWith("\\)")
      ? trimmed.slice(2, -2).trim()
      : trimmed.startsWith("\\[") && trimmed.endsWith("\\]")
        ? trimmed.slice(2, -2).trim()
        : trimmed.startsWith("$") && trimmed.endsWith("$")
          ? trimmed.slice(1, -1).trim() : trimmed;
    const latex = toConfirmedLatex(unwrapped);
    return latex && renderOcrLatexHtml(latex) !== null ? { latex, explanation: "" } : null;
  }
  return { latex: null, explanation: trimmed };
}
