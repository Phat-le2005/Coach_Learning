"use client";

import React from "react";
import {
  Pause,
  Play,
  SkipForward,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import type { AIReviewUIState } from "../../utils/ai-review-controller";
import styles from "./AIReview.module.css";

interface AIReviewControlsProps {
  uiState: AIReviewUIState;
  revealedCount: number;
  totalSteps: number;
  canGoPrev: boolean;
  canGoNext: boolean;
  onPause: () => void;
  onResume: () => void;
  onSkipToEnd: () => void;
  onReplay: () => void;
  onPrevStep: () => void;
  onNextStep: () => void;
}

export function AIReviewControls({
  uiState,
  revealedCount,
  totalSteps,
  canGoPrev,
  canGoNext,
  onPause,
  onResume,
  onSkipToEnd,
  onReplay,
  onPrevStep,
  onNextStep,
}: AIReviewControlsProps) {
  const progressPercent =
    totalSteps > 0 ? Math.min(100, Math.round((revealedCount / totalSteps) * 100)) : 0;

  return (
    <div className={styles.controlsBar} aria-label="Điều khiển trình chiếu nhận xét">
      <div className={styles.progressCluster}>
        <span className={styles.progressCountBadge}>
          Bước {revealedCount} / {totalSteps}
        </span>
        <div className={styles.progressTrack} aria-hidden="true">
          <div
            className={styles.progressFill}
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      <div className={styles.controlBtnGroup}>
        {uiState === "REVEALING" && (
          <>
            <button
              type="button"
              onClick={onPause}
              className={styles.controlIconBtn}
              title="Tạm dừng hiệu ứng trình chiếu"
            >
              <Pause size={13} />
              <span>Tạm dừng</span>
            </button>
            <button
              type="button"
              onClick={onSkipToEnd}
              className={styles.controlIconBtn}
              title="Mở ngay toàn bộ kết quả"
            >
              <SkipForward size={13} />
              <span>Mở tất cả</span>
            </button>
          </>
        )}

        {uiState === "PAUSED" && (
          <>
            <button
              type="button"
              onClick={onResume}
              className={styles.controlIconBtn}
              title="Tiếp tục hiệu ứng trình chiếu"
            >
              <Play size={13} />
              <span>Tiếp tục</span>
            </button>
            <button
              type="button"
              onClick={onSkipToEnd}
              className={styles.controlIconBtn}
              title="Mở ngay toàn bộ kết quả"
            >
              <SkipForward size={13} />
              <span>Mở tất cả</span>
            </button>
          </>
        )}

        {uiState === "COMPLETED" && totalSteps > 0 && (
          <button
            type="button"
            onClick={onReplay}
            className={styles.controlIconBtn}
            title="Xem lại hiệu ứng đánh giá từng bước"
          >
            <RotateCcw size={13} />
            <span>Trình chiếu lại</span>
          </button>
        )}

        <button
          type="button"
          onClick={onPrevStep}
          disabled={!canGoPrev}
          className={styles.controlIconBtn}
          aria-label="Bước trước"
          title="Chuyển sang bước trước"
        >
          <ChevronLeft size={14} />
        </button>
        <button
          type="button"
          onClick={onNextStep}
          disabled={!canGoNext}
          className={styles.controlIconBtn}
          aria-label="Bước tiếp theo"
          title="Chuyển sang bước tiếp theo"
        >
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}
