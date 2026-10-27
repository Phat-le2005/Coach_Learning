"use client";

import React, { useState } from "react";
import { Sparkles, BookOpen, X, ChevronUp } from "lucide-react";
import { MathRenderer } from "@/components/ui/MathRenderer";
import type { ProblemRead } from "../../types";
import type { AIReviewUIState } from "../../utils/ai-review-controller";
import styles from "./AIReview.module.css";

interface AIReviewHeaderProps {
  uiState: AIReviewUIState;
  confirmedStepCount: number;
  problem: ProblemRead | null;
  onClose: () => void;
}

function getStatusBadgeMeta(uiState: AIReviewUIState): {
  label: string;
  className: string;
} {
  switch (uiState) {
    case "REQUESTING":
    case "READY":
      return {
        label: "Đang đối chiếu với đáp án...",
        className: styles.statusPillRequesting,
      };
    case "REVEALING":
      return {
        label: "Đang trình bày từng bước",
        className: styles.statusPillRevealing,
      };
    case "PAUSED":
      return {
        label: "Đã tạm dừng trình chiếu",
        className: styles.statusPillPaused,
      };
    case "COMPLETED":
      return {
        label: "Đã có nhận xét AI",
        className: styles.statusPillCompleted,
      };
    case "ERROR":
      return {
        label: "Chưa thể hoàn tất đối chiếu",
        className: styles.statusPillError,
      };
    default:
      return {
        label: "Chế độ nhận xét AI",
        className: styles.statusPillRequesting,
      };
  }
}

export function AIReviewHeader({
  uiState,
  confirmedStepCount,
  problem,
  onClose,
}: AIReviewHeaderProps) {
  const [showProblem, setShowProblem] = useState(false);
  const statusMeta = getStatusBadgeMeta(uiState);

  return (
    <>
      <header className={styles.headerBar}>
        <div className={styles.headerBrand}>
          <div className={styles.headerIconBadge} aria-hidden="true">
            <Sparkles size={18} />
          </div>
          <div className={styles.headerTitleGroup}>
            <div className={styles.headerTitleRow}>
              <h2 className={styles.headerTitle}>
                Đối chiếu lời giải từng bước cùng AI
              </h2>
              <span className={`${styles.statusPill} ${statusMeta.className}`}>
                <span className={styles.statusDot} aria-hidden="true" />
                {statusMeta.label}
              </span>
            </div>
            <p className={styles.headerSubtitle}>
              {confirmedStepCount} bước giải đã xác nhận · Nhận xét tham khảo dựa trên đáp án chuẩn
            </p>
          </div>
        </div>

        <div className={styles.headerActions}>
          {problem && (
            <button
              type="button"
              onClick={() => setShowProblem((prev) => !prev)}
              className={`${styles.problemToggleBtn} ${showProblem ? styles.problemToggleBtnActive : ""}`}
              aria-expanded={showProblem}
            >
              <BookOpen size={15} />
              <span>{showProblem ? "Ẩn đề bài" : "Xem đề bài"}</span>
              {showProblem && <ChevronUp size={14} />}
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className={styles.closeReviewBtn}
            aria-label="Đóng chế độ nhận xét AI"
          >
            <X size={16} />
            <span>Quay lại bài làm</span>
          </button>
        </div>
      </header>

      {showProblem && problem && (
        <section className={styles.problemDrawer} aria-label="Đề bài toán">
          <div className={styles.problemDrawerHeader}>
            <span>Đề bài tham chiếu</span>
          </div>
          <div className={styles.problemDrawerBody}>
            <MathRenderer content={problem.content} />
          </div>
        </section>
      )}
    </>
  );
}
