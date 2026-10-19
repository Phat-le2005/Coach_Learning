"use client";

import { useMemo } from "react";

import styles from "../MathWorkspace.module.css";
import { renderOcrLatexHtml } from "../utils/ocr-math-preview";

interface OcrMathPreviewProps {
  latex: string;
}

export function OcrMathPreview({ latex }: OcrMathPreviewProps) {
  const html = useMemo(() => renderOcrLatexHtml(latex), [latex]);

  if (!latex.trim()) return <span className={styles.emptyPreviewText}>Chưa có công thức</span>;
  if (html === null) {
    return <span className={styles.previewError}>Chưa thể hiển thị công thức này. Hãy kiểm tra LaTeX trước khi xác nhận.</span>;
  }
  return <span className={styles.renderedFormula} dangerouslySetInnerHTML={{ __html: html }} />;
}
