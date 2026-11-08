"use client";

import React, { useMemo } from "react";
import katex from "katex";

interface MathRendererProps {
  content: string;
  className?: string;
  inline?: boolean;
}

/**
 * Pre-processes and normalizes math formula strings before KaTeX parsing.
 */
function normalizeMathText(text: string): string {
  if (!text) return "";
  return text;
}

function enhanceTextWithInlineMath(text: string): string {
  if (!text) return "";
  let s = text;
  // Replace x_ngang, y_ngang
  s = s.replace(/\b([xyz])_ngang\b/gi, (_m, p1) => `$\\bar{${p1}}$`);
  // Replace B_ngang, A_ngang
  s = s.replace(/\b([A-Z])_ngang\b/g, (_m, p1) => `$\\overline{${p1}}$`);
  // Replace x_i, y_i, n_i, x_0, y_0
  s = s.replace(/\b([xyn])_([ijk0-9])\b/g, (_m, p1, p2) => `$${p1}_{${p2}}$`);
  // Replace s^2, R^2
  s = s.replace(/\b([sR])\^2\b/g, (_m, p1) => `$${p1}^2$`);
  // Replace !=
  s = s.replace(/\s+!=\s+/g, " $\\neq$ ");
  return s;
}

function formatParagraphs(text: string): string {
  return text
    .split(/\n{2,}/)
    .map((paragraph) =>
      escapeHtml(paragraph.replace(/[ \t]*\n[ \t]*/g, " "))
    )
    .join("<br/><br/>");
}

function pipeCells(line: string): string[] | null {
  let row = line.trim();
  if (!/(?<!\\)\|/.test(row)) return null;
  if (row.startsWith("|")) row = row.slice(1);
  if (/(?<!\\)\|$/.test(row)) row = row.slice(0, -1);
  return row.split(/(?<!\\)\|/).map((cell) => cell.trim().replace(/\\\|/g, "|"));
}

/** Render only pipe tables with a valid header separator; source HTML stays text. */
export function formatPlainText(text: string): string {
  const normalized = text.replace(/\r\n?/g, "\n");
  const lines = normalized.split("\n");
  const blocks: string[] = [];
  let plain: string[] = [];
  let foundTable = false;
  const flushPlain = () => {
    const value = plain.join("\n").replace(/^\n+|\n+$/g, "");
    if (value) blocks.push(formatParagraphs(value));
    plain = [];
  };

  for (let index = 0; index < lines.length; index++) {
    const header = pipeCells(lines[index]);
    const separator = index + 1 < lines.length ? pipeCells(lines[index + 1]) : null;
    if (!header || header.length < 2 || separator?.length !== header.length
        || !separator.every((cell) => /^:?-{3,}:?$/.test(cell))) {
      plain.push(lines[index]);
      continue;
    }
    const rows: string[][] = [];
    let end = index + 2;
    while (end < lines.length) {
      const cells = pipeCells(lines[end]);
      if (!cells || cells.length !== header.length) break;
      rows.push(cells);
      end++;
    }
    if (rows.length === 0) {
      plain.push(lines[index]);
      continue;
    }
    foundTable = true;
    flushPlain();
    const cellStyle = "border:1px solid currentColor;padding:0.45rem 0.65rem;text-align:left;vertical-align:top";
    blocks.push(
      '<div style="max-width:100%;overflow-x:auto"><table style="border-collapse:collapse;margin:0.25rem 0">'
      + `<thead><tr>${header.map((cell) => `<th scope="col" style="${cellStyle}">${escapeHtml(cell)}</th>`).join("")}</tr></thead>`
      + `<tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td style="${cellStyle}">${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}</tbody>`
      + "</table></div>"
    );
    index = end - 1;
  }
  if (!foundTable) return formatParagraphs(normalized);
  flushPlain();
  return blocks.join("<br/><br/>");
}

interface Segment {
  type: "text" | "inline_math" | "display_math";
  value: string;
}

function parseMathSegments(text: string): Segment[] {
  const segments: Segment[] = [];
  // Regex to match $$...$$, \[...\], $...$, \(...\)
  const mathRegex = /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\$(?!\$)[\s\S]+?\$|\\\([\s\S]+?\\\))/g;

  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = mathRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({
        type: "text",
        value: text.slice(lastIndex, match.index),
      });
    }

    const raw = match[0];
    if (raw.startsWith("$$") && raw.endsWith("$$")) {
      segments.push({
        type: "display_math",
        value: raw.slice(2, -2).trim(),
      });
    } else if (raw.startsWith("\\[") && raw.endsWith("\\]")) {
      segments.push({
        type: "display_math",
        value: raw.slice(2, -2).trim(),
      });
    } else if (raw.startsWith("\\(") && raw.endsWith("\\)")) {
      segments.push({
        type: "inline_math",
        value: raw.slice(2, -2).trim(),
      });
    } else if (raw.startsWith("$") && raw.endsWith("$")) {
      segments.push({
        type: "inline_math",
        value: raw.slice(1, -1).trim(),
      });
    }

    lastIndex = mathRegex.lastIndex;
  }

  if (lastIndex < text.length) {
    segments.push({
      type: "text",
      value: text.slice(lastIndex),
    });
  }

  return segments;
}

function preprocessVietnameseInMath(mathStr: string): {
  processed: string;
  restores: Array<{ token: string; text: string }>;
} {
  const restores: Array<{ token: string; text: string }> = [];
  let tokenCounter = 0;

  // Protect \text{...}, \textrm{...}, \textnormal{...}, \mathrm{...}, \textbf{...}, \textit{...} containing Vietnamese letters
  const processed = mathStr.replace(
    /\\(text|textnormal|textrm|mathrm|textbf|textit)\{([^}]+)\}/g,
    (match, cmd, inner) => {
      if (/[\u00c0-\u1ef9]/.test(inner)) {
        const token = `VNTEXT${tokenCounter++}END`;
        restores.push({ token, text: inner });
        return `\\${cmd}{${token}}`;
      }
      return match;
    }
  );

  return { processed, restores };
}

export function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function restoreVietnameseInHtml(
  html: string,
  restores: Array<{ token: string; text: string }>
): string {
  let result = html;
  for (const item of restores) {
    result = result.replace(
      item.token,
      `<span class="katex-vn-text">${escapeHtml(item.text)}</span>`
    );
  }
  return result;
}

function renderKatexSafe(expression: string, isDisplay: boolean): string {
  const originalWarn = console.warn;
  try {
    console.warn = (...args: unknown[]) => {
      const msg = typeof args[0] === "string" ? args[0] : "";
      if (
        msg.includes("No character metrics") ||
        msg.includes("LaTeX-incompatible input") ||
        msg.includes("Unrecognized Unicode character")
      ) {
        return; // Suppress character metrics warnings for non-ASCII/Vietnamese text in math
      }
      originalWarn.apply(console, args);
    };

    const { processed, restores } = preprocessVietnameseInMath(expression);

    let html = katex.renderToString(processed, {
      displayMode: isDisplay,
      throwOnError: false,
      strict: "ignore",
    });

    if (restores.length > 0) {
      html = restoreVietnameseInHtml(html, restores);
    }

    return html;
  } catch {
    const safe = expression.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return `<span>${safe}</span>`;
  } finally {
    console.warn = originalWarn;
  }
}

export function MathRenderer({ content, className = "", inline = false }: MathRendererProps) {
  const renderedHtml = useMemo(() => {
    if (!content) return "";
    const trimmed = content.trim();

    // 1. Check if content is a single wrapped display math expression: $$...$$ or \[...\]
    if (
      (trimmed.startsWith("$$") && trimmed.endsWith("$$") && trimmed.length >= 4) ||
      (trimmed.startsWith("\\[") && trimmed.endsWith("\\]") && trimmed.length >= 4)
    ) {
      const inner = trimmed.startsWith("$$") ? trimmed.slice(2, -2).trim() : trimmed.slice(2, -2).trim();
      return renderKatexSafe(inner, true);
    }

    // 2. Check if content is a single wrapped inline math expression: \(...\) or $...$
    if (
      (trimmed.startsWith("\\(") && trimmed.endsWith("\\)") && trimmed.length >= 4) ||
      (trimmed.startsWith("$") && trimmed.endsWith("$") && trimmed.length >= 2 && !trimmed.slice(1, -1).includes("$"))
    ) {
      const inner = trimmed.startsWith("\\(") ? trimmed.slice(2, -2).trim() : trimmed.slice(1, -1).trim();
      return renderKatexSafe(inner, false);
    }

    // 3. Pure standalone formula without delimiters (e.g. from node.latex)
    if (
      (trimmed.startsWith("\\") || trimmed.includes("=") || trimmed.includes("^") || trimmed.includes("_") || trimmed.includes("\\frac") || trimmed.includes("\\sum")) &&
      !/[\r\n]/.test(trimmed) &&
      !/[\u00c0-\u1ef9]/iu.test(trimmed) &&
      !/\b[A-Za-z]{4,}\s+[A-Za-z]{4,}\b/.test(trimmed) &&
      !trimmed.includes("$") &&
      !trimmed.includes("\\[")
    ) {
      return renderKatexSafe(trimmed, !inline);
    }

    const normalized = normalizeMathText(content);
    const segments = parseMathSegments(normalized);

    return segments
      .map((segment) => {
        if (segment.type === "text") {
          const enhanced = enhanceTextWithInlineMath(segment.value);
          if (enhanced.includes("$")) {
            const subSegments = parseMathSegments(enhanced);
            return subSegments
              .map((sub) =>
                sub.type === "text"
                  ? formatPlainText(sub.value)
                  : renderKatexSafe(sub.value, sub.type === "display_math")
              )
              .join("");
          }
          return formatPlainText(segment.value);
        }

        const isDisplay = segment.type === "display_math";
        return renderKatexSafe(segment.value, isDisplay);
      })
      .join("");
  }, [content, inline]);

  return (
    <div
      className={`math-rendered-content ${className}`}
      dangerouslySetInnerHTML={{ __html: renderedHtml }}
    />
  );
}
