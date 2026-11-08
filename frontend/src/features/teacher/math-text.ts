export type MathTextPart = { kind: "text"; raw: string } | { kind: "math"; raw: string; latex: string; open: string; close: string; display: boolean };

function escaped(text: string, position: number): boolean {
  let count = 0;
  for (let i = position - 1; i >= 0 && text[i] === "\\"; i--) count++;
  return count % 2 === 1;
}

/** Keep original delimiters, whitespace, text and unsupported input byte-for-byte. */
export function splitMathText(value: string): MathTextPart[] {
  const result: MathTextPart[] = [];
  let plainStart = 0;
  for (let i = 0; i < value.length; i++) {
    if (escaped(value, i)) continue;
    const open = value.startsWith("$$", i) ? "$$" : value[i] === "$" ? "$" : value.startsWith("\\(", i) ? "\\(" : value.startsWith("\\[", i) ? "\\[" : null;
    if (!open) continue;
    const close = open === "\\(" ? "\\)" : open === "\\[" ? "\\]" : open;
    let end = i + open.length;
    for (; end < value.length; end++) {
      if (value.startsWith(close, end) && !escaped(value, end)) break;
    }
    if (end >= value.length) { i += open.length - 1; continue; }
    if (i > plainStart) result.push({ kind: "text", raw: value.slice(plainStart, i) });
    const raw = value.slice(i, end + close.length);
    result.push({ kind: "math", raw, latex: value.slice(i + open.length, end), open, close, display: open === "$$" || open === "\\[" });
    i = end + close.length - 1;
    plainStart = i + 1;
  }
  if (plainStart < value.length) result.push({ kind: "text", raw: value.slice(plainStart) });
  return result;
}
