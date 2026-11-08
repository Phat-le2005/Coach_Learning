import katex from "katex";

/** Preserve OCR line breaks without splitting rows inside cases, arrays or braces. */
function multilineExpression(latex: string): string {
  const input = latex.trim().replace(/\r\n?/g, "\n");
  const lines: string[] = [];
  let start = 0, braces = 0, environments = 0;
  for (let index = 0; index < input.length; index++) {
    if (input[index] === "\\") {
      const environment = /^\\(begin|end)\{[^}]+\}/.exec(input.slice(index));
      if (environment) {
        environments += environment[1] === "begin" ? 1 : -1;
        index += environment[0].length - 1;
      } else if (["\\", "{", "}"].includes(input[index + 1])) {
        index++;
      }
    } else if (input[index] === "{") {
      braces++;
    } else if (input[index] === "}") {
      braces--;
    } else if (input[index] === "\n" && braces === 0 && environments === 0) {
      const line = input.slice(start, index).trim();
      if (line) lines.push(line);
      start = index + 1;
    }
  }
  const last = input.slice(start).trim();
  if (last) lines.push(last);
  return lines.length > 1 ? `\\begin{gathered}${lines.join(" \\\\ ")}\\end{gathered}` : input;
}

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
    return katex.renderToString(multilineExpression(latex), {
      displayMode: true,
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
