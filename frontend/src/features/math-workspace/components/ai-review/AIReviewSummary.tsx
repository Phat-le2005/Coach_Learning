"use client";

import React, { useEffect, useRef } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  Filter,
  RotateCcw,
  X,
  ArrowRight,
  LoaderCircle,
} from "lucide-react";
import type {
  AIReviewFilterMode,
  AIReviewSummaryStats,
} from "../../utils/ai-review-controller";
import type { AIReviewRead } from "@/lib/api/contracts";
import styles from "./AIReview.module.css";

interface AIReviewSummaryProps {
  review: AIReviewRead;
  stats: AIReviewSummaryStats;
  filterMode: AIReviewFilterMode;
  onSetFilter: (mode: AIReviewFilterMode) => void;
  onJumpToStep: (stepIndex: number) => void;
  onReplay: () => void;
  onClose: () => void;
  onNextProblem?: () => void;
  nextProblemLabel?: string;
  isNextLoading?: boolean;
}

export function AIReviewSummary({
  review,
  stats,
  filterMode,
  onSetFilter,
  onJumpToStep,
  onReplay,
  onClose,
  onNextProblem,
  nextProblemLabel,
  isNextLoading = false,
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
        <span className={styles.referenceBadge}>
          {review.is_final
            ? "Điểm đã ghi nhận"
            : review.review_source === "ANSWER_GROUNDED_AI"
            ? "Đã đối chiếu đáp án chuẩn"
            : "Góp ý tham khảo"}
        </span>
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
            {review.review_source === "UNANSWERED_AI" ? "—" : `${stats.validCount}/${stats.totalSteps}`}
          </span>
        </div>

        <div>
          <strong style={{ fontSize: "0.92rem", color: "#113928" }}>
            {review.is_final
              ? `${review.review_source === "TEACHER" ? "Điểm giáo viên ghi nhận" : review.review_source === "ANSWER_GROUNDED_AI" ? "Điểm Gemini theo rubric được duyệt" : "Điểm theo rubric được duyệt"}: ${Math.round((review.final_score ?? 0) * 100)}%.`
              : review.review_source === "UNANSWERED_AI"
                ? "Chưa có đáp án được duyệt. Các góp ý dưới đây không xác định đúng sai và không cho điểm."
                : review.review_source === "ANSWER_GROUNDED_AI"
                ? stats.invalidCount === 0 && stats.needsReviewCount === 0
                  ? "AI đã đối chiếu các bước với đáp án mẫu. Kết quả đang ở mức góp ý tham khảo."
                  : `AI nhận xét ${stats.validCount}/${stats.totalSteps} bước hợp lý; kết quả chưa phải điểm chính thức.`
                : stats.invalidCount === 0 && stats.needsReviewCount === 0
              ? "AI chưa đánh dấu bước nào cần xem lại."
              : `AI gợi ý kiểm tra lại ${stats.issueStepIndices.length} bước.`}
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
          <span className={styles.metricLabel}>{review.is_final ? "Bước hợp lý" : "AI nhận xét hợp lý"}</span>
        </div>
        <div className={styles.metricCard}>
          <span
            className={`${styles.metricValue} ${styles.metricValueInvalid}`}
          >
            {stats.invalidCount}
          </span>
          <span className={styles.metricLabel}>{review.is_final ? "Bước cần sửa" : "AI gợi ý xem lại"}</span>
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

      <p className={styles.disclaimerNote}>{review.is_final
        ? review.review_source === "TEACHER"
          ? "Điểm này do giáo viên ghi nhận. Nhận xét theo từng bước chỉ hiện nếu đã được lưu."
          : review.review_source === "ANSWER_GROUNDED_AI"
          ? "Điểm và năng lực được cập nhật từ kết quả Gemini theo rubric đã duyệt."
          : "Điểm này được tính từ rubric đã duyệt và các bước được quy tắc toán học kiểm chứng."
        : review.review_source === "UNANSWERED_AI"
          ? "AI chỉ gợi ý điều cần kiểm tra. Giáo viên cần bổ sung hoặc duyệt đáp án trước khi có điểm chính thức."
          : stats.disclaimer}</p>

      {/* LOOP CLOSURE: Khép vòng học tập sang Cây Tri Thức & Lộ Trình */}
      <div
        style={{
          margin: "14px 0",
          padding: "14px 16px",
          borderRadius: "14px",
          background: hasIssues
            ? "linear-gradient(135deg, rgba(234, 179, 8, 0.12), rgba(245, 158, 11, 0.06))"
            : "linear-gradient(135deg, rgba(35, 166, 122, 0.15), rgba(16, 185, 129, 0.08))",
          border: hasIssues
            ? "1px solid rgba(245, 158, 11, 0.35)"
            : "1px solid rgba(35, 166, 122, 0.35)",
          display: "flex",
          flexDirection: "column",
          gap: "8px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: "0.86rem", fontWeight: 700, color: hasIssues ? "#b45309" : "#14533f" }}>
            {!review.is_final ? "Đã nhận góp ý cho bài làm" : hasIssues
              ? "⚡ Cần củng cố thêm công thức trước khi sang câu mới?"
              : "🌱 Đã hoàn thành chặng luyện tập có kiểm chứng AI!"}
          </span>
          <span
            style={{
              fontSize: "0.75rem",
              fontWeight: 650,
              padding: "2px 8px",
              borderRadius: "999px",
              background: hasIssues ? "rgba(245, 158, 11, 0.2)" : "rgba(35, 166, 122, 0.2)",
              color: hasIssues ? "#b45309" : "#14533f",
            }}
          >
            {!review.is_final ? "Góp ý tham khảo" : hasIssues ? "Cần gỡ lỗi" : "Đã ghi nhận độ vững"}
          </span>
        </div>

        <p style={{ margin: 0, fontSize: "0.78rem", color: "#374151", lineHeight: 1.45 }}>
          {hasIssues
            ? "Bạn có thể xem lại sơ đồ tư duy & khung cắt công thức PDF để hiểu rõ lý do biến đổi, hoặc bấm nút xem lại các bước sai bên dưới."
            : "Kết quả bài làm đã được đồng bộ vào bảng đo lường năng lực của bạn. Hãy quay lại xem nhánh cây vừa sáng hoặc tiếp tục chặng hôm nay."}
        </p>

        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "6px", alignItems: "center" }}>
          {onNextProblem && (
            <button
              type="button"
              onClick={onNextProblem}
              disabled={isNextLoading}
              className={styles.summaryNextBtn}
            >
              {isNextLoading ? (
                <>
                  <LoaderCircle className={styles.spin} size={15} />
                  <span>Đang mở bài tiếp theo...</span>
                </>
              ) : (
                <>
                  <ArrowRight size={15} />
                  <span>{nextProblemLabel || "Luyện tập bài tiếp theo →"}</span>
                </>
              )}
            </button>
          )}

          <a
            href="/student/knowledge"
            style={{
              padding: "7px 12px",
              borderRadius: "8px",
              background: "#23a67a",
              color: "#ffffff",
              fontSize: "0.8rem",
              fontWeight: 650,
              textDecoration: "none",
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
              boxShadow: "0 2px 6px rgba(35, 166, 122, 0.3)",
            }}
          >
            ✦ Xem trên Cây Tri Thức 3D
          </a>

          <a
            href="/student/theory"
            style={{
              padding: "7px 12px",
              borderRadius: "8px",
              background: "rgba(255, 255, 255, 0.85)",
              border: "1px solid rgba(16, 46, 38, 0.15)",
              color: "#14533f",
              fontSize: "0.8rem",
              fontWeight: 650,
              textDecoration: "none",
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
            }}
          >
            📖 Mở Sơ đồ tư duy PDF
          </a>

          <a
            href="/student"
            style={{
              padding: "7px 12px",
              borderRadius: "8px",
              background: "transparent",
              color: "#4b5563",
              fontSize: "0.8rem",
              fontWeight: 600,
              textDecoration: "none",
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
            }}
          >
            Về trang chủ →
          </a>
        </div>
      </div>

      <div className={styles.summaryActions}>
        {onNextProblem && (
          <button
            type="button"
            onClick={onNextProblem}
            disabled={isNextLoading}
            className={styles.summaryNextBtn}
          >
            {isNextLoading ? (
              <>
                <LoaderCircle className={styles.spin} size={14} />
                <span>Đang tải...</span>
              </>
            ) : (
              <>
                <ArrowRight size={15} />
                <span>{nextProblemLabel || "Luyện tập bài tiếp theo →"}</span>
              </>
            )}
          </button>
        )}
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
