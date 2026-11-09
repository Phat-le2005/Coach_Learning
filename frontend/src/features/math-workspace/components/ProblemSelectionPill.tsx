"use client";

import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { Box, Copy, Check, Lightbulb } from "lucide-react";
import styles from "./ProblemSelectionPill.module.css";

export interface ProblemSelectionPillProps {
  rect: { top: number; bottom: number; left: number; right: number; width: number };
  formula: string;
  onVisualize?: (formula: string) => void;
  onOpenHint?: () => void;
  onClose: () => void;
}

/**
 * Smart Floating Action Pill (Notion/Medium style)
 * Appears when students highlight a math formula or equation in the problem statement.
 * Allows 1-click 3D/2D visualization, formula copying, and AI hints without manual handwriting.
 */
export function ProblemSelectionPill({
  rect,
  formula,
  onVisualize,
  onOpenHint,
  onClose,
}: ProblemSelectionPillProps) {
  const [copied, setCopied] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted || typeof document === "undefined") return null;

  // Position pill centered above the selection (or below if too close to viewport top)
  const pillHeight = 42;
  const isNearTop = rect.top < pillHeight + 16;
  const top = isNearTop ? rect.bottom + 10 : rect.top - pillHeight - 10;
  const rawCenter = rect.left + rect.width / 2;
  const left = Math.max(160, Math.min(window.innerWidth - 160, rawCenter));

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(formula);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // Fallback
    }
  }

  function handleVisualize() {
    if (onVisualize && formula) {
      onVisualize(formula);
      onClose();
      window.getSelection()?.removeAllRanges();
    }
  }

  function handleHint() {
    if (onOpenHint) {
      onOpenHint();
      onClose();
    }
  }

  const content = (
    <div
      className={`${styles.floatingPill} ${isNearTop ? styles.nearTop : styles.above}`}
      style={{ top: `${top}px`, left: `${left}px` }}
      role="toolbar"
      aria-label="Thao tác nhanh cho công thức đã chọn"
      onMouseDown={e => {
        // Prevent clicking inside the pill from collapsing the text selection prematurely
        e.preventDefault();
        e.stopPropagation();
      }}
    >
      {/* 1. View 3D / Graph Button */}
      {onVisualize && (
        <button
          type="button"
          className={styles.actionBtnPrimary}
          title={`Khảo sát không gian 3D / Đồ thị cho: ${formula}`}
          onClick={handleVisualize}
        >
          <Box size={14} className={styles.icon3d} aria-hidden="true" />
          <span>Khảo sát 3D</span>
        </button>
      )}

      <span className={styles.divider} aria-hidden="true" />

      {/* 2. Copy Formula */}
      <button
        type="button"
        className={styles.actionBtn}
        title="Sao chép công thức"
        onClick={handleCopy}
      >
        {copied ? (
          <>
            <Check size={14} className={styles.iconCopied} aria-hidden="true" />
            <span className={styles.textCopied}>Đã chép!</span>
          </>
        ) : (
          <>
            <Copy size={13} aria-hidden="true" />
            <span>Sao chép</span>
          </>
        )}
      </button>

      {/* 3. Hint / AI Review (if available) */}
      {onOpenHint && (
        <>
          <span className={styles.divider} aria-hidden="true" />
          <button
            type="button"
            className={`${styles.actionBtn} ${styles.btnHint}`}
            title="Xem gợi ý phương pháp giải"
            onClick={handleHint}
          >
            <Lightbulb size={13} className={styles.iconHint} aria-hidden="true" />
            <span>Gợi ý</span>
          </button>
        </>
      )}
    </div>
  );

  return createPortal(content, document.body);
}
