"use client";

import { useMemo } from "react";
import { MathRenderer } from "@/components/ui/MathRenderer";
import styles from "../MathWorkspace.module.css";
import { renderOcrLatexHtml } from "../utils/ocr-math-preview";

interface OcrMathPreviewProps {
  latex: string;
}

export function OcrMathPreview({ latex }: OcrMathPreviewProps) {
  const html = useMemo(() => renderOcrLatexHtml(latex), [latex]);

  if (!latex.trim()) return <span className={styles.emptyPreviewText}>Chưa có công thức</span>;
  if (html === null) {
    // Graceful fallback to rich math renderer when input contains mixed prose or $ delimiters
    return (
      <span className={styles.renderedFormula}>
        <MathRenderer content={latex} inline />
      </span>
    );
  }
  return <span className={styles.renderedFormula} dangerouslySetInnerHTML={{ __html: html }} />;
}
