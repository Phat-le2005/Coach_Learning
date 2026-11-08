"use client";

import React, { useState } from "react";
import { Sparkles, BookOpen, X, ChevronUp, ArrowRight, LoaderCircle } from "lucide-react";
import { MathRenderer } from "@/components/ui/MathRenderer";
import type { ProblemRead } from "../../types";
import type { AIReviewUIState } from "../../utils/ai-review-controller";
import type { AIReviewRead } from "@/lib/api/contracts";
import styles from "./AIReview.module.css";

interface AIReviewHeaderProps {
  uiState: AIReviewUIState;
  confirmedStepCount: number;
  problem: ProblemRead | null;
  review: AIReviewRead | null;
  onClose: () => void;
  onNextProblem?: () => void;
  nextProblemLabel?: string;
  isNextLoading?: boolean;
}

function getStatusBadgeMeta(uiState: AIReviewUIState, review: AIReviewRead | null): {
  label: string;
  className: string;
} {
  switch (uiState) {
    case "REQUESTING":
    case "READY":
      return {
        label: "Đang kiểm tra các bước...",
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
        label: review?.is_final ? "Đã có điểm chính thức" : "Đã có góp ý tạm thời",
        className: styles.statusPillCompleted,
      };
    case "ERROR":
      return {
        label: "Chưa thể hoàn tất đối chiếu",
        className: styles.statusPillError,
      };
    default:
      return {
        label: "Kiểm tra bài làm",
        className: styles.statusPillRequesting,
      };
  }
}

export function AIReviewHeader({
  uiState,
  confirmedStepCount,
  problem,
  review,
  onClose,
  onNextProblem,
  nextProblemLabel,
  isNextLoading = false,
}: AIReviewHeaderProps) {
  const [showProblem, setShowProblem] = useState(false);
  const statusMeta = getStatusBadgeMeta(uiState, review);

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
                Kiểm tra lời giải từng bước
              </h2>
              <span className={`${styles.statusPill} ${statusMeta.className}`}>
                <span className={styles.statusDot} aria-hidden="true" />
                {statusMeta.label}
              </span>
            </div>
            <p className={styles.headerSubtitle}>
              {confirmedStepCount} bước giải đã xác nhận · {review?.review_source === "TEACHER"
                ? "Điểm do giáo viên ghi nhận"
                : review?.is_final
                ? "Điểm từ quy tắc toán học và rubric được duyệt"
                : review?.review_source === "UNANSWERED_AI"
                  ? "Chưa có đáp án: góp ý sơ bộ, chờ giáo viên duyệt"
                  : "Nhận xét tham khảo, chưa phải điểm chính thức"}
            </p>
          </div>
        </div>

        <div className={styles.headerActions}>
          {onNextProblem && (
            <button
              type="button"
              onClick={onNextProblem}
              disabled={isNextLoading}
              className={styles.nextProblemHeaderBtn}
            >
              {isNextLoading ? (
                <>
                  <LoaderCircle className={styles.spin} size={14} />
                  <span>Đang mở...</span>
                </>
              ) : (
                <>
                  <ArrowRight size={14} />
                  <span>{nextProblemLabel || "Bài tiếp theo →"}</span>
                </>
              )}
            </button>
          )}
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
            aria-label="Đóng chế độ kiểm tra bài làm"
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
