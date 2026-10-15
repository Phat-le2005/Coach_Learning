"use client";

import React from "react";
import { BookOpen, PanelLeftClose, PanelLeft, CheckCircle2 } from "lucide-react";
import type { ProblemRead, SolutionAttemptRead } from "../types";
import styles from "../MathWorkspace.module.css";

interface ProblemPaneProps {
  problem: ProblemRead | null;
  attempt: SolutionAttemptRead | null;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export function ProblemPane({
  problem,
  attempt,
  isCollapsed,
  onToggleCollapse,
}: ProblemPaneProps) {
  if (isCollapsed) {
    return (
      <aside className={styles.problemPaneCollapsed}>
        <button
          type="button"
          className={styles.expandButton}
          onClick={onToggleCollapse}
          title="Mở rộng đề bài (35%)"
          aria-label="Mở rộng bảng đề bài"
        >
          <PanelLeft size={18} />
          <span className={styles.verticalText}>ĐỀ BÀI</span>
        </button>
      </aside>
    );
  }

  return (
    <aside className={styles.problemPane} aria-label="Nội dung đề bài">
      <div className={styles.problemHeader}>
        <div className={styles.problemHeaderLeft}>
          <BookOpen className={styles.problemIcon} size={18} />
          <h2 className={styles.problemTitle}>Đề bài</h2>
          {problem?.question_type && (
            <span className={styles.questionTypeBadge}>
              {formatQuestionType(problem.question_type)}
            </span>
          )}
        </div>

        <button
          type="button"
          className={styles.collapseButton}
          onClick={onToggleCollapse}
          title="Thu gọn đề bài để tập trung không gian viết"
          aria-label="Thu gọn đề bài"
        >
          <PanelLeftClose size={18} />
        </button>
      </div>

      <div className={styles.problemContentScroll}>
        {problem ? (
          <>
            {/* Question Text */}
            <div className={styles.problemBody}>
              <div className={styles.problemContentText}>{problem.content}</div>
            </div>

            {/* Options (if multiple choice) */}
            {problem.options && problem.options.length > 0 && (
              <div className={styles.optionsSection}>
                <h3 className={styles.optionsTitle}>Các phương án lựa chọn:</h3>
                <div className={styles.optionsList}>
                  {problem.options.map((opt) => (
                    <div key={opt.id} className={styles.optionCard}>
                      <span className={styles.optionLabel}>{opt.label}</span>
                      <div className={styles.optionContent}>{opt.content}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Attempt info footer */}
            {attempt && (
              <div className={styles.attemptMeta}>
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>Trạng thái lượt giải:</span>
                  <span className={styles.metaValue}>
                    {formatAttemptStatus(attempt.status)}
                  </span>
                </div>
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>Phiên bản bài làm:</span>
                  <span className={styles.metaValue}>v{attempt.current_revision}</span>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className={styles.problemPlaceholder}>
            <p>Đang tải thông tin đề bài...</p>
          </div>
        )}
      </div>
    </aside>
  );
}

function formatQuestionType(type: string): string {
  switch (type.toUpperCase()) {
    case "MULTIPLE_CHOICE":
      return "Trắc nghiệm 4 lựa chọn";
    case "TRUE_FALSE":
      return "Đúng / Sai";
    case "SHORT_ANSWER":
      return "Trả lời ngắn";
    case "ESSAY":
      return "Tự luận";
    default:
      return type;
  }
}

function formatAttemptStatus(status: string): string {
  switch (status.toUpperCase()) {
    case "IN_PROGRESS":
      return "Đang thực hiện";
    case "SUBMITTED":
      return "Đã nộp bài";
    case "EVALUATED":
      return "Đã đánh giá";
    default:
      return status;
  }
}
