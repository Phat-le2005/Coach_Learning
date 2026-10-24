"use client";

import React, { useState } from "react";
import { BookOpen, PanelLeftClose, PanelLeft, Trash2 } from "lucide-react";
import type { ProblemRead, SolutionAttemptRead } from "../types";
import type { AIReviewRead, AIReviewAvailabilityRead } from "@/lib/api/contracts";
import { MathRenderer } from "@/components/ui/MathRenderer";
import { ApiNetworkError, ApiResponseError } from "@/lib/api/client";
import { OcrMathPreview } from "./OcrMathPreview";
import styles from "../MathWorkspace.module.css";

interface ProblemPaneProps {
  problem: ProblemRead | null;
  attempt: SolutionAttemptRead | null;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  onDeleteStep: (stepId: string) => Promise<void>;
  onSubmitSolution: () => Promise<void>;
  onAIReview: () => Promise<void>;
  aiReview: AIReviewRead | null;
  aiReviewAvailability: AIReviewAvailabilityRead | null;
  gradingError: string | null;
  isSubmitting: boolean;
  isReviewing: boolean;
}

export function ProblemPane({
  problem,
  attempt,
  isCollapsed,
  onToggleCollapse,
  onDeleteStep,
  onSubmitSolution,
  onAIReview,
  aiReview,
  aiReviewAvailability,
  gradingError,
  isSubmitting,
  isReviewing,
}: ProblemPaneProps) {
  const [confirmStepId, setConfirmStepId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const canDelete = attempt?.status === "DRAFT" || attempt?.status === "IN_PROGRESS";

  const confirmDelete = async () => {
    if (!confirmStepId || isDeleting) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await onDeleteStep(confirmStepId);
      setConfirmStepId(null);
    } catch (error: unknown) {
      setDeleteError(error instanceof ApiNetworkError || (error instanceof ApiResponseError && error.status >= 500)
        ? "Chưa nhận được kết quả xóa. Bấm thử lại để kiểm tra, không cần tạo thao tác mới."
        : error instanceof ApiResponseError && error.status === 401
          ? "Phiên đăng nhập đã hết hạn. Đăng nhập lại ở tab khác rồi thử xóa."
          : error instanceof ApiResponseError && error.status === 409
            ? "Bài giải đã thay đổi. Hãy tải lại trang để kiểm tra các bước hiện tại."
            : "Không thể xóa bước này. Vui lòng thử lại.");
    } finally {
      setIsDeleting(false);
    }
  };

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
              <div className={styles.problemContentText}>
                <MathRenderer content={problem.content} />
              </div>
            </div>

            {/* Options (if multiple choice) */}
            {problem.options && problem.options.length > 0 && (
              <div className={styles.optionsSection}>
                <h3 className={styles.optionsTitle}>Các phương án lựa chọn:</h3>
                <div className={styles.optionsList}>
                  {problem.options.map((opt) => (
                    <div key={opt.id} className={styles.optionCard}>
                      <span className={styles.optionLabel}>{opt.label}</span>
                      <div className={styles.optionContent}>
                        <MathRenderer content={opt.content} />
                      </div>
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
            {attempt?.steps && attempt.steps.length > 0 ? (
              <section className={styles.savedSteps} aria-label="Các bước giải đã lưu">
                <h3>Các bước giải đã xác nhận</h3>
                <ol>
                  {[...attempt.steps].sort((a, b) => a.step_index - b.step_index).map((step) => (
                    <li key={step.id}>
                      <div className={styles.savedStepHeader}>
                        <strong>Bước {step.step_index}</strong>
                        {canDelete ? (
                          <button type="button" className={styles.deleteStepButton}
                            onClick={() => { setConfirmStepId(step.id); setDeleteError(null); }}
                            disabled={isDeleting || (confirmStepId !== null && confirmStepId !== step.id)}
                            aria-label={`Xóa bước giải ${step.step_index}`}>
                            <Trash2 size={15} aria-hidden="true" /> Xóa
                          </button>
                        ) : null}
                      </div>
                      {step.content_latex ? <OcrMathPreview latex={step.content_latex} /> : null}
                      {step.explanation_text ? <p className={step.step_type === "VARIATION_TABLE" ? styles.variationTableStep : undefined}>{step.explanation_text}</p> : null}
                      {confirmStepId === step.id ? (
                        <div className={styles.deleteStepConfirm}>
                          <p>Xóa bước {step.step_index} khỏi bài giải? Nét viết trên trang vẫn được giữ.</p>
                          {deleteError ? <p role="alert" className={styles.deleteStepError}>{deleteError}</p> : null}
                          <div>
                            <button type="button" className={styles.buttonSecondary}
                              onClick={() => { setConfirmStepId(null); setDeleteError(null); }}
                              disabled={isDeleting}>Hủy</button>
                            <button type="button" className={styles.deleteStepConfirmButton}
                              onClick={() => void confirmDelete()} disabled={isDeleting}>
                              {isDeleting ? "Đang xóa..." : deleteError ? "Thử xóa lại" : "Xác nhận xóa"}
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ol>
              </section>
            ) : null}
            {attempt && problem.question_type === "OPEN_RESPONSE" ? (
              <section className={styles.aiReviewPanel} aria-label="Nhận xét từng bước giải">
                <h3>Đối chiếu lời giải với đáp án</h3>
                {canDelete ? (
                  <>
                    <p>Kiểm tra lại mọi bước OCR rồi nộp bài để nhận góp ý.</p>
                    <button type="button" className={styles.aiReviewButton}
                      onClick={() => void onSubmitSolution()}
                      disabled={isSubmitting || !attempt.steps?.length}>
                      {isSubmitting ? "Đang nộp bài..." : "Nộp bài giải"}
                    </button>
                  </>
                ) : attempt.status === "SUBMITTED" ? (
                  <>
                    <p>AI chỉ gợi ý điểm từng bước. Bài thiếu đáp án sẽ chờ giáo viên xem.</p>
                    {aiReviewAvailability?.available === false ? (
                      <p className={styles.aiReviewNotice}>Bài này chưa có đáp án tham chiếu đã duyệt. Bài làm đã nộp được giữ lại, nhưng chưa thể nhờ Gemini chấm từng bước. Giáo viên cần bổ sung đáp án trước.</p>
                    ) : aiReviewAvailability === null ? (
                      <p className={styles.aiReviewNotice}>Chưa kiểm tra được đáp án tham chiếu. Hãy tải lại trang khi kết nối ổn định.</p>
                    ) : !aiReview ? (
                      <button type="button" className={styles.aiReviewButton}
                        onClick={() => void onAIReview()} disabled={isReviewing}>
                        {isReviewing ? "Đang đối chiếu..." : "Nhận xét bằng Gemini"}
                      </button>
                    ) : (
                      <>
                        <p className={styles.aiReviewNotice}>Kết quả tham khảo, chưa phải điểm chính thức.</p>
                        <ol className={styles.aiReviewList}>
                          {aiReview.step_grades.map((grade) => (
                            <li key={grade.step_index}>
                              <strong>Bước {grade.step_index}: {grade.verdict === "VALID" ? "Hợp lý" : grade.verdict === "INVALID" ? "Cần sửa" : "Cần xem lại"}</strong>
                              {grade.score !== null ? <span>Gợi ý: {Math.round(grade.score * 100)}%</span> : null}
                              <p>{grade.feedback}</p>
                            </li>
                          ))}
                        </ol>
                        {aiReview.needs_teacher_review ? <p>Ít nhất một bước cần giáo viên xem lại.</p> : null}
                      </>
                    )}
                  </>
                ) : null}
                {gradingError ? <p role="alert" className={styles.aiReviewError}>{gradingError}</p> : null}
              </section>
            ) : null}
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
