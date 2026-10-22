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

    // If whole content looks like raw LaTeX without $ wrappers (e.g. \frac{1}{2} or y' = 3x^2)
    const trimmed = content.trim();
    if (
      (trimmed.startsWith("\\") || trimmed.includes("=") || trimmed.includes("^") || trimmed.includes("_")) &&
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
          return segment.value
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\n/g, "<br/>");
        }

        const isDisplay = segment.type === "display_math";
        try {
          return katex.renderToString(segment.value, {
            displayMode: isDisplay,
            throwOnError: false,
            strict: false,
          });
        } catch {
          return `<span>${segment.value}</span>`;
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
