"use client";

import React, { useEffect, useRef } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  Filter,
  RotateCcw,
  X,
} from "lucide-react";
import type {
  AIReviewFilterMode,
  AIReviewSummaryStats,
} from "../../utils/ai-review-controller";
import styles from "./AIReview.module.css";

interface AIReviewSummaryProps {
  stats: AIReviewSummaryStats;
  filterMode: AIReviewFilterMode;
  onSetFilter: (mode: AIReviewFilterMode) => void;
  onJumpToStep: (stepIndex: number) => void;
  onReplay: () => void;
  onClose: () => void;
}

export function AIReviewSummary({
  stats,
  filterMode,
  onSetFilter,
  onJumpToStep,
  onReplay,
  onClose,
}: AIReviewSummaryProps) {
  const summaryRef = useRef<HTMLElement | null>(null);
  const hasIssues = stats.issueStepIndices.length > 0;
  const ratio =
    stats.totalSteps > 0 ? stats.validCount / stats.totalSteps : 0;
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - ratio);

  useEffect(() => {
    summaryRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
    });
  }, []);

  return (
    <section
      ref={summaryRef}
      className={styles.summaryPanel}
      aria-label="Tổng kết nhận xét AI"
    >
      <div className={styles.summaryHeader}>
        <h3 className={styles.summaryTitle}>
          <CheckCircle2 size={18} color="#148056" />
          <span>Tổng kết đánh giá từng bước</span>
        </h3>
        <span className={styles.referenceBadge}>Kết quả tham khảo</span>
      </div>

      <div className={styles.summaryHeroRow}>
        <div className={styles.accuracyRingWrap} aria-hidden="true">
          <svg width="68" height="68" viewBox="0 0 68 68">
            <circle
              cx="34"
              cy="34"
              r={radius}
              fill="none"
              stroke="#e1f2e9"
              strokeWidth="6.5"
            />
            <circle
              cx="34"
              cy="34"
              r={radius}
              fill="none"
              stroke={hasIssues ? "#d97706" : "#159966"}
              strokeWidth="6.5"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={dashOffset}
              transform="rotate(-90 34 34)"
              style={{
                transition: "stroke-dashoffset 750ms cubic-bezier(0.22, 1, 0.36, 1)",
              }}
            />
          </svg>
          <span className={styles.accuracyRingLabel}>
            {stats.validCount}/{stats.totalSteps}
          </span>
        </div>

        <div>
          <strong style={{ fontSize: "0.92rem", color: "#113928" }}>
            {stats.invalidCount === 0 && stats.needsReviewCount === 0
              ? "Tuyệt vời! Toàn bộ các bước giải đều hợp lý."
              : `Đã phát hiện ${stats.issueStepIndices.length} bước giải cần kiểm tra hoặc chỉnh sửa.`}
          </strong>
          <p
            style={{
              margin: "0.22rem 0 0",
              fontSize: "0.79rem",
              color: "#4a6b5b",
            }}
          >
            Bấm vào từng bước bên trên để xem chi tiết nhận xét và đối chiếu với bài viết.
          </p>
        </div>
      </div>

      <div className={styles.metricsGrid}>
        <div className={styles.metricCard}>
          <span className={styles.metricValue}>{stats.totalSteps}</span>
          <span className={styles.metricLabel}>Tổng số bước</span>
        </div>
        <div className={styles.metricCard}>
          <span className={`${styles.metricValue} ${styles.metricValueValid}`}>
            {stats.validCount}
          </span>
          <span className={styles.metricLabel}>Bước hợp lý</span>
        </div>
        <div className={styles.metricCard}>
          <span
            className={`${styles.metricValue} ${styles.metricValueInvalid}`}
          >
            {stats.invalidCount}
          </span>
          <span className={styles.metricLabel}>Bước cần sửa</span>
        </div>
        <div className={styles.metricCard}>
          <span className={`${styles.metricValue} ${styles.metricValueReview}`}>
            {stats.needsReviewCount}
          </span>
          <span className={styles.metricLabel}>Cần xem lại</span>
        </div>
      </div>

      {hasIssues && (
        <div className={styles.issueCallout}>
          <p className={styles.issueCalloutTitle}>
            Các bước bạn nên kiểm tra và chỉnh sửa ưu tiên:
          </p>
          <div className={styles.issueJumpRow}>
            {stats.issueStepIndices.map((stepIdx) => (
              <button
                key={stepIdx}
                type="button"
                onClick={() => onJumpToStep(stepIdx)}
                className={styles.issueJumpBtn}
              >
                Xem Bước {stepIdx}
              </button>
            ))}
          </div>
        </div>
      )}

      {stats.teacherReviewNotice && (
        <div className={styles.teacherReviewBanner} role="note">
          <AlertTriangle size={16} />
          <span>{stats.teacherReviewNotice}</span>
        </div>
      )}

      <p className={styles.disclaimerNote}>{stats.disclaimer}</p>

      <div className={styles.summaryActions}>
        {hasIssues && (
          <button
            type="button"
            onClick={() => {
              if (filterMode === "NEEDS_FIX") {
                onSetFilter("ALL");
              } else {
                onSetFilter("NEEDS_FIX");
                if (stats.issueStepIndices[0] !== undefined) {
                  onJumpToStep(stats.issueStepIndices[0]);
                }
              }
            }}
            className={
              filterMode === "NEEDS_FIX"
                ? styles.summarySecondaryBtn
                : styles.summaryPrimaryBtn
            }
          >
            <Filter size={14} />
            <span>
              {filterMode === "NEEDS_FIX"
                ? "Xem tất cả các bước"
                : "Xem bước cần sửa"}
            </span>
          </button>
        )}

        {filterMode === "NEEDS_FIX" && !hasIssues && (
          <button
            type="button"
            onClick={() => onSetFilter("ALL")}
            className={styles.summarySecondaryBtn}
          >
            <span>Xem tất cả các bước</span>
          </button>
        )}

        <button
          type="button"
          onClick={onReplay}
          className={styles.summarySecondaryBtn}
        >
          <RotateCcw size={14} />
          <span>Trình chiếu chấm lại từ đầu</span>
        </button>

        <button
          type="button"
          onClick={onClose}
          className={styles.summarySecondaryBtn}
        >
          <X size={14} />
          <span>Đóng chế độ nhận xét</span>
        </button>
      </div>
    </section>
  );
}
