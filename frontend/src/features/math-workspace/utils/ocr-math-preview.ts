import katex from "katex";

/** Render untrusted OCR text only as local, non-trusted math markup. */
export function renderOcrLatexHtml(latex: string): string | null {
  if (!latex.trim() || latex.length > 1000) return null;
  const originalWarn = console.warn;
  try {
    console.warn = (...args: unknown[]) => {
      const msg = typeof args[0] === "string" ? args[0] : "";
      if (
        msg.includes("No character metrics") ||
        msg.includes("LaTeX-incompatible input") ||
        msg.includes("Unrecognized Unicode character")
      ) {
        return;
      }
      originalWarn.apply(console, args);
    };
    return katex.renderToString(latex, {
      displayMode: false,
      output: "htmlAndMathml",
      throwOnError: true,
      trust: false,
      maxExpand: 100,
      strict: "ignore",
    });
  } catch {
    return null;
  } finally {
    console.warn = originalWarn;
  }
}
