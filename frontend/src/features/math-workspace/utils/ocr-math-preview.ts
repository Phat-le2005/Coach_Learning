import katex from "katex";

/** Render untrusted OCR text only as local, non-trusted math markup. */
export function renderOcrLatexHtml(latex: string): string | null {
  if (!latex.trim() || latex.length > 1000) return null;
  try {
    return katex.renderToString(latex, {
      displayMode: false,
      output: "htmlAndMathml",
      throwOnError: true,
      trust: false,
      maxExpand: 100,
    });
  } catch {
    return null;
  }
}
