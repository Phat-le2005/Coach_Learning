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
      try {
        return katex.renderToString(trimmed, {
          displayMode: !inline,
          throwOnError: false,
          strict: false,
        });
      } catch {
        // Fallback to segment parsing if single-shot render fails
      }
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
        try {
          return katex.renderToString(segment.value, {
            displayMode: isDisplay,
            throwOnError: false,
            strict: false,
          });
        } catch {
          const safe = segment.value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
          return `<span>${safe}</span>`;
        }
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
