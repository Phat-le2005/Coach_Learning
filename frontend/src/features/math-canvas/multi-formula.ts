import type { InkStroke } from "@/lib/api/contracts";
import { segmentPageInk, type PageOcrRegion } from "../math-workspace/utils/page-ocr";

/** Split only explicit row separators outside mathematical groups. Never split a fraction. */
export function splitFormulaRows(source: string): string[] {
  const aligned = /\\begin\{(?:cases|aligned|align\*?)\}/.test(source);
  const text = source.trim().replace(/\\begin\{(?:cases|aligned|align\*?)\}/g, "").replace(/\\end\{(?:cases|aligned|align\*?)\}/g, "")
    .replace(/\\left\s*\\\{/g, "").replace(/\\right\s*\./g, "").replace(/&/g, aligned ? "" : "&");
  const rows: string[] = [];
  let depth = 0, start = 0;
  for (let i = 0; i < text.length; i++) {
    if ("({[".includes(text[i])) depth++;
    else if (")}]".includes(text[i])) depth--;
    const latexBreak = text[i] === "\\" && text[i + 1] === "\\";
    if (depth === 0 && (text[i] === "\n" || text[i] === ";" || latexBreak)) {
      if (text.slice(start, i).trim()) rows.push(text.slice(start, i).trim());
      if (latexBreak) i++;
      start = i + 1;
    }
  }
  if (text.slice(start).trim()) rows.push(text.slice(start).trim());
  // A wrapped single equation is not two formulas merely because it has a newline.
  return rows.length > 1 && rows.every((row) => /[=<>≤≥]|\\(?:le|ge)/.test(row)) ? rows : [source.trim()].filter(Boolean);
}

/** Rejoin fragments of a mathematical line by vertical extent instead of center.
 * A handwritten y/parenthesis can be much taller than its baseline characters.
 * The page detector still supplies fraction protection; separate columns stay apart.
 */
function joinEquationFragments(regions: PageOcrRegion[], pen: InkStroke[], median: number): PageOcrRegion[] {
  const groups = regions.map((row) => ({ ...row, strokes: [...row.strokes], bounds: { ...row.bounds } }));
  let changed = true;
  while (changed) {
    changed = false;
    outer: for (let i = 0; i < groups.length; i++) for (let j = i + 1; j < groups.length; j++) {
      const a = groups[i].bounds, b = groups[j].bounds;
      const verticalGap = Math.max(a.top, b.top) - Math.min(a.bottom, b.bottom);
      const horizontalGap = Math.max(a.left, b.left) - Math.min(a.right, b.right);
      if (verticalGap > median * .2 || horizontalGap > Math.max(.02, median * 1.5)) continue;
      const ids = new Set([...groups[i].strokes, ...groups[j].strokes].map((stroke) => stroke.id));
      const strokes = pen.filter((stroke) => ids.has(stroke.id));
      groups[i] = { id: strokes[0].id, strokes, bounds: { left: Math.min(a.left, b.left), top: Math.min(a.top, b.top), right: Math.max(a.right, b.right), bottom: Math.max(a.bottom, b.bottom) } };
      groups.splice(j, 1); changed = true; break outer;
    }
  }
  return groups.sort((a, b) => a.bounds.top - b.bounds.top || a.bounds.left - b.bounds.left);
}

/** Reuse the fraction-aware line detector, excluding a separate left system brace
 * only when the remaining ink really forms multiple disjoint, substantial rows.
 * Nothing is removed from the original document or saved stroke provenance.
 */
export function equationInkRows(strokes: InkStroke[]): { regions: PageOcrRegion[]; omittedIds: string[] } {
  const pen = strokes.filter((stroke) => stroke.tool === "PEN" && stroke.points.length);
  const boxes = pen.map((stroke) => ({ stroke, left: Math.min(...stroke.points.map((p) => p.x)), right: Math.max(...stroke.points.map((p) => p.x)),
    top: Math.min(...stroke.points.map((p) => p.y)), bottom: Math.max(...stroke.points.map((p) => p.y)) }));
  const heights = boxes.map((box) => box.bottom - box.top).filter((height) => height > .006).sort((a, b) => a - b);
  const median = heights[Math.floor(heights.length / 2)] ?? .018;
  const left = Math.min(...boxes.map((box) => box.left));
  const candidates = boxes.filter((box) => box.left <= left + median * .3 && box.bottom - box.top > median * 3
    && (box.right - box.left) < (box.bottom - box.top) * .4
    && boxes.filter((other) => other !== box && other.left >= box.right).length >= 4);
  if (candidates.length) {
    const omitted = new Set(candidates.map((box) => box.stroke.id));
    const content = pen.filter((stroke) => !omitted.has(stroke.id));
    const regions = joinEquationFragments(segmentPageInk(content), content, median);
    const substantial = regions.length >= 2 && regions.every((row, index) => row.strokes.length >= 3
      && row.bounds.right - row.bounds.left > median * 2
      && (index === 0 || row.bounds.top - regions[index - 1].bounds.bottom > median * .35));
    const spansRows = candidates.every((box) => regions.filter((row) => box.top <= row.bounds.bottom && box.bottom >= row.bounds.top).length >= 2);
    if (substantial && spansRows) return { regions, omittedIds: [...omitted] };
  }
  return { regions: joinEquationFragments(segmentPageInk(pen), pen, median), omittedIds: [] };
}

/** Keep local model inference sequential and stop queued rows after a manual edit. */
export async function recognizeFormulaRows(regions: PageOcrRegion[], recognize: (strokes: InkStroke[]) => Promise<{ latex: string }>,
  shouldContinue: () => boolean, progress: (done: number) => void) {
  const formulas: string[] = [], failed: number[] = [];
  for (let i = 0; i < regions.length; i++) {
    if (!shouldContinue()) return null;
    try { formulas.push((await recognize(regions[i].strokes)).latex); }
    catch { formulas.push(""); failed.push(i + 1); }
    if (!shouldContinue()) return null;
    progress(i + 1);
  }
  return { formulas, failed };
}
