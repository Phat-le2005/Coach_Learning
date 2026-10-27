"use client";

import React from "react";
import type { AIStepSuggestionRead } from "@/lib/api/contracts";
import styles from "./AIReview.module.css";

interface AIReviewStepIndicatorProps {
  stepGrades: ReadonlyArray<AIStepSuggestionRead>;
  revealedCount: number;
  activeStepIndex: number | null;
  onSelectStep: (stepIndex: number) => void;
}

export function AIReviewStepIndicator({
  stepGrades,
  revealedCount,
  activeStepIndex,
  onSelectStep,
}: AIReviewStepIndicatorProps) {
  if (stepGrades.length === 0) return null;

  return (
    <div
      className={styles.stepIndicatorRail}
      role="tablist"
      aria-label="Điều hướng nhanh các bước giải"
    >
      {stepGrades.map((grade, orderIdx) => {
        const isRevealed = orderIdx < revealedCount;
        const isActive = activeStepIndex === grade.step_index;

        const dotClass =
          grade.verdict === "VALID"
            ? styles.stepPillDotValid
            : grade.verdict === "INVALID"
              ? styles.stepPillDotInvalid
              : styles.stepPillDotNeedsReview;

        return (
          <button
            key={grade.step_index}
            type="button"
            role="tab"
            aria-selected={isActive}
            disabled={!isRevealed}
            onClick={() => onSelectStep(grade.step_index)}
            className={`${styles.stepPillBtn} ${
              !isRevealed ? styles.stepPillBtnPending : ""
            } ${isActive ? styles.stepPillBtnActive : ""}`}
          >
            {isRevealed && (
              <span
                className={`${styles.stepPillDot} ${dotClass}`}
                aria-hidden="true"
              />
            )}
            <span>Bước {grade.step_index}</span>
          </button>
        );
      })}
    </div>
  );
}
