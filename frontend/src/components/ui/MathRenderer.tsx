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
 * Handles common issues like unclosed '$', equations starting with '= \frac...', etc.
 */
function normalizeMathText(text: string): string {
  if (!text) return "";

  let cleaned = text;

  // Handle common typo where an equation starts with '= \frac' or similar and ends with '$'
  // e.g. "hàm số = \frac{1}{3}x^3 - x^2 - 3x + 1$." -> "hàm số $y = \frac{1}{3}x^3 - x^2 - 3x + 1$."
  if (/=\s*\\frac/.test(cleaned) && !cleaned.includes("$=") && !cleaned.includes("$y =")) {
    cleaned = cleaned.replace(/=\s*\\frac([^$]+)\$/, "$$y = \\frac$1$$");
  }

  return cleaned;
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

    // A sentence containing '=' is not a standalone formula. Render whole-input
    // KaTeX only for compact formula-like values without prose or PDF line breaks.
    const trimmed = content.trim();
    if (
      (trimmed.startsWith("\\") || trimmed.includes("=") || trimmed.includes("^") || trimmed.includes("_")) &&
      trimmed.length <= 200 &&
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
          // PDF text extraction often inserts soft wraps inside one sentence.
          // Preserve paragraph breaks while joining single source line wraps.
          return segment.value.replace(/\r\n?/g, "\n").split(/\n{2,}/).map((paragraph) =>
            paragraph.replace(/[ \t]*\n[ \t]*/g, " ")
              .replace(/&/g, "&amp;")
              .replace(/</g, "&lt;")
              .replace(/>/g, "&gt;"),
          ).join("<br/><br/>");
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
