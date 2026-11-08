"use client";

import React, { useState } from "react";
import Link from "next/link";
import { BookOpen, PanelLeftClose, PanelLeft, Trash2, Sparkles, PenLine } from "lucide-react";
import type { ProblemRead, SolutionAttemptRead } from "../types";
import type { AIReviewRead, AIReviewAvailabilityRead, SolutionStepRead, VariationTablePayload } from "@/lib/api/contracts";
import { parseVariationTablePayload } from "@/lib/api/contracts";
import { QuestionContent } from "@/components/ui/QuestionContent";
import { ApiNetworkError, ApiResponseError } from "@/lib/api/client";
import { OcrMathPreview } from "./OcrMathPreview";
import { VariationTableGrid } from "./VariationTableModal";
import { problemNeedsSourceReview } from "../utils/question-presentation";
import { getSolutionSubmissionState } from "../utils/solution-submission";
import styles from "../MathWorkspace.module.css";

interface ProblemPaneProps {
  problem: ProblemRead | null;
  attempt: SolutionAttemptRead | null;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  onVisualizeFormula?: (formula: string) => void;
  onDeleteStep: (stepId: string) => Promise<void>;
  onEditVariationTable: (stepId: string, payload: VariationTablePayload) => void;
  onSubmitSolution: () => Promise<void>;
  onConfirmExamQuestion?: () => Promise<void>;
  onPrepareSubmission: () => void;
  onReopenAttempt?: () => Promise<void>;
  onAIReview: () => Promise<void>;
  onOpenReviewWorkspace?: () => void;
  aiReview: AIReviewRead | null;
  aiReviewAvailability: AIReviewAvailabilityRead | null;
  gradingError: string | null;
  isSubmitting: boolean;
  isReviewing: boolean;
  submissionBlocked: boolean;
  examMode?: boolean;
}

function variationPayload(step: SolutionStepRead): VariationTablePayload | null {
  if (step.artifact?.artifact_type !== "VARIATION_TABLE") return null;
  try { return parseVariationTablePayload(step.artifact.payload); }
  catch { return null; }
}

export function ProblemPane({
  problem,
  attempt,
  isCollapsed,
  onToggleCollapse,
  onVisualizeFormula,
  onDeleteStep,
  onEditVariationTable,
  onSubmitSolution,
  onConfirmExamQuestion,
  onPrepareSubmission,
  onReopenAttempt,
  onAIReview,
  onOpenReviewWorkspace,
  aiReview,
  aiReviewAvailability,
  gradingError,
  isSubmitting,
  isReviewing,
  submissionBlocked,
  examMode = false,
}: ProblemPaneProps) {
  const [confirmStepId, setConfirmStepId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const needsSourceReview = problem ? problemNeedsSourceReview(problem.content, problem.options) : false;
  const submission = getSolutionSubmissionState(problem, attempt, needsSourceReview);
  const canDelete = submission.canEdit;

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
          <h2 className={styles.problemTitle}>
            {problem?.context_type === "CLASSROOM_ASSIGNMENT" &&
            problem.order_index !== undefined &&
            problem.order_index !== null
              ? `Câu ${problem.order_index + 1}`
              : "Đề bài"}
          </h2>
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
            {problem.is_read_only && attempt?.status !== "SUBMITTED" && attempt?.status !== "EVALUATED" ? (
              <section className={styles.questionSourceWarning} role="alert">
                Câu hỏi này đang chờ kiểm tra nguồn. Bài làm cũ được giữ để xem lại; hiện không thể tiếp tục hoặc nộp bài này.
              </section>
            ) : null}
            {needsSourceReview ? (
              <section className={styles.questionSourceWarning} role="alert">
                <h3>Đề bài cần kiểm tra lại bản gốc</h3>
                <p>Ký hiệu toán trong bản trích xuất bị sai thứ tự hoặc thiếu nét. Hệ thống không thể ghép lại công thức và các đáp án một cách đáng tin cậy. Em hãy chọn bài khác; bài này cần được đối chiếu với nguồn trước khi sử dụng.</p>
                <p>Mã câu hỏi: <code>{problem.id}</code></p>
                <Link href="/student/attempts">Quay về danh sách bài làm</Link>
                <details className={styles.questionRawDetails}>
                  <summary>Xem văn bản trích xuất gốc để báo lỗi</summary>
                  <pre>{problem.content}</pre>
                  {problem.options.map((option) => (
                    <pre key={option.id}>{option.label}. {option.content}</pre>
                  ))}
                </details>
              </section>
            ) : (
              <>
                {/* Question Text */}
                <div className={styles.problemBody}>
                  <div className={styles.problemContentText}>
                    <QuestionContent content={problem.content} visuals={problem.visuals} relatedContent={problem.options.map((option) => option.content)} />
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
                            <QuestionContent content={opt.content} visuals={problem.visuals} gallery={false} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {/* Attempt info footer */}
            {attempt && (
              <div className={styles.attemptMeta}>
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>Trạng thái:</span>
                  <span className={styles.metaValue}>
                    {formatAttemptStatus(attempt.status)}
                  </span>
                </div>
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>Phiên bản:</span>
                  <span className={styles.metaValue}>v{attempt.current_revision}</span>
                </div>
              </div>
            )}

            {/* Confirmed Solution Steps - displayed prominently right after question */}
            {attempt?.steps && attempt.steps.length > 0 ? (
              <section className={styles.savedSteps} aria-label="Các bước giải đã lưu">
                <h3>Các bước giải đã xác nhận ({attempt.steps.length} bước)</h3>
                <ol>
                  {[...attempt.steps].sort((a, b) => a.step_index - b.step_index).map((step) => {
                    const table = variationPayload(step);
                    return <li key={step.id}>
                      <div className={styles.savedStepHeader}>
                        <strong>Bước {step.step_index}</strong>
                        {!table && step.content_latex && onVisualizeFormula ? <button type="button" className={styles.buttonSecondary}
                          onClick={() => onVisualizeFormula(step.content_latex!)}>Xem hình 2D/3D</button> : null}
                        {canDelete && table ? (
                          <button type="button" className={styles.buttonSecondary}
                            onClick={() => onEditVariationTable(step.id, table)}>Sửa bảng</button>
                        ) : null}
                        {canDelete ? (
                          <button type="button" className={styles.deleteStepButton}
                            onClick={() => { setConfirmStepId(step.id); setDeleteError(null); }}
                            disabled={isDeleting || (confirmStepId !== null && confirmStepId !== step.id)}
                            aria-label={`Xóa bước giải ${step.step_index}`}>
                            <Trash2 size={15} aria-hidden="true" /> Xóa
                          </button>
                        ) : null}
                      </div>
                      {table ? <VariationTableGrid value={table} />
                        : step.content_latex ? <OcrMathPreview latex={step.content_latex} /> : null}
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
                    </li>;
                  })}
                </ol>
              </section>
            ) : (
              <section className={styles.noStepsNotice}>
                <p>Chưa có bước giải nào được xác nhận. Hãy viết bài hoặc tải ảnh chụp ở bên phải rồi xác nhận các bước.</p>
              </section>
            )}

            {/* AI Review Launch Card */}
            {aiReview && !examMode ? (
              <section className={styles.aiReviewPanel} aria-label="Nhận xét từng bước giải">
                <h3>{aiReview.is_final ? "Đã có điểm chính thức" : "Đã có nhận xét từng bước"}</h3>
                <p className={styles.aiReviewNotice}>
                  {aiReview.review_source === "UNANSWERED_AI"
                    ? `${aiReview.step_grades.length} bước có góp ý sơ bộ, chưa xác định đúng sai`
                    : aiReview.step_grades.length
                      ? `${aiReview.step_grades.filter((g) => g.verdict === "VALID").length}/${aiReview.step_grades.length} bước ${aiReview.is_final ? "đã kiểm chứng" : "AI nhận xét có thể hợp lý"}`
                      : "Chưa có nhận xét chi tiết theo từng bước"}
                  {aiReview.step_grades.some((g) => g.verdict === "INVALID")
                    ? ` · ${aiReview.step_grades.filter((g) => g.verdict === "INVALID").length} bước ${aiReview.is_final ? "cần sửa" : "AI gợi ý xem lại"}`
                    : ""}
                  {aiReview.step_grades.some((g) => g.verdict === "NEEDS_REVIEW")
                    ? ` · ${aiReview.step_grades.filter((g) => g.verdict === "NEEDS_REVIEW").length} bước cần xem lại`
                    : ""}
                </p>
                <button
                  type="button"
                  className={styles.primaryGradeButton}
                  onClick={() => (onOpenReviewWorkspace ? onOpenReviewWorkspace() : void onAIReview())}
                >
                  <Sparkles size={15} />
                  Mở chế độ đối chiếu từng bước
                </button>
              </section>
            ) : null}
          </>
        ) : (
          <div className={styles.problemPlaceholder}>
            <p>Đang tải thông tin đề bài...</p>
          </div>
        )}
      </div>

      {/* Each exam question is confirmed separately; the whole paper is submitted once. */}
      {examMode && problem && attempt && !needsSourceReview ? (
        <div className={styles.problemPaneFooter}>
          <div className={styles.footerSubmitAction}>
            {attempt.status === "SUBMITTED" ? (
              <>
                <small className={styles.footerHint}>Câu này đã xác nhận. Muốn chỉnh lại, bấm “Sửa câu này” ở thanh trên.</small>
              </>
            ) : ["DRAFT", "IN_PROGRESS"].includes(attempt.status) && !problem.is_read_only ? (
              <>
                <small className={styles.footerHint}>
                  {attempt.steps?.length
                    ? `Đã lưu ${attempt.steps.length} bước giải. Bước này sẽ tự động nộp khi bấm “Nộp bài kiểm tra” hoặc em có thể xác nhận sớm.`
                    : "Trích xuất hoặc nhập bước giải cho câu này."}
                </small>
                {attempt.steps?.length ? (
                  <button type="button" className={styles.primaryGradeButton}
                    disabled={isSubmitting || submissionBlocked}
                    onClick={() => void onConfirmExamQuestion?.()}>
                    {isSubmitting ? "Đang xác nhận..." : "Xác nhận câu này"}
                  </button>
                ) : (
                  <button type="button" className={styles.primaryGradeButton}
                    disabled={isSubmitting || submissionBlocked}
                    onClick={onPrepareSubmission}>
                    Trích xuất hoặc nhập bước giải
                  </button>
                )}
              </>
            ) : null}
            {gradingError ? <p role="alert" className={styles.aiReviewError}>{gradingError}</p> : null}
          </div>
        </div>
      ) : null}
      {/* Sticky Bottom Footer: Always Visible Submit & Grade Bar */}
      {problem && attempt && !examMode && !needsSourceReview &&
        (!problem.is_read_only || attempt.status === "SUBMITTED" || attempt.status === "EVALUATED") ? (
        <div className={styles.problemPaneFooter}>
          {attempt.status === "SUBMITTED" || attempt.status === "EVALUATED" ? (
            aiReview ? (
              <div className={styles.footerReviewed}>
                <div className={styles.footerStatusInfo}>
                  <span className={styles.footerSuccessDot}>●</span>
                  <span>{aiReview.is_final
                    ? `Điểm chính thức: ${Math.round((aiReview.final_score ?? 0) * 100)}%`
                    : aiReview.review_source === "UNANSWERED_AI"
                      ? "Góp ý sơ bộ · Chờ đáp án và giáo viên duyệt"
                      : "Nhận xét tạm thời · Chưa có điểm chính thức"}</span>
                </div>
                <button
                  type="button"
                  className={styles.primaryGradeButton}
                  onClick={() => (onOpenReviewWorkspace ? onOpenReviewWorkspace() : void onAIReview())}
                  disabled={isReviewing}
                >
                  <Sparkles size={15} />
                  {isReviewing ? "Đang kiểm tra..." : "Xem chi tiết từng bước"}
                </button>
              </div>
            ) : (
              <div className={styles.footerSubmitAction}>
                <button
                  type="button"
                  className={styles.primaryGradeButton}
                  onClick={() => void onAIReview()}
                  disabled={isReviewing || aiReviewAvailability?.available === false}
                >
                  <Sparkles size={16} />
                  {isReviewing ? "Đang kiểm tra bài..." : "Kiểm tra bài làm"}
                </button>
                {aiReviewAvailability?.available === false ? (
                  <>
                    <small className={styles.footerNotice}>{aiReviewAvailability.reason_code === "GRADING_ASSIGNMENT_NOT_SUBMITTED"
                      ? "Hãy nộp toàn bộ bài giáo viên giao trước khi kiểm tra lời giải."
                      : "Đề bài chưa đủ điều kiện kiểm tra"}</small>
                    {onReopenAttempt && (
                      <button
                        type="button"
                        className={styles.buttonSecondary}
                        onClick={() => void onReopenAttempt()}
                        title="Mở khóa bài làm để tiếp tục vẽ hoặc sửa các bước giải"
                        style={{ marginTop: "0.5rem", width: "100%", justifyContent: "center" }}
                      >
                        <PenLine size={15} /> Tiếp tục sửa bài này
                      </button>
                    )}
                  </>
                ) : (
                  <small className={styles.footerHint}>{aiReviewAvailability?.reason_code === "PROVISIONAL_WITHOUT_ANSWER"
                    ? "Chưa có đáp án: chỉ nhận góp ý sơ bộ, không cho điểm"
                    : "Ưu tiên chấm bằng quy tắc; bước chưa rõ sẽ nhận góp ý AI"}</small>
                )}
              </div>
            )
          ) : (
            <div className={styles.footerSubmitAction}>
              <button
                type="button"
                className={styles.buttonSecondary}
                onClick={onPrepareSubmission}
                disabled={isSubmitting || isReviewing || submissionBlocked}
                title="Mở giao diện trích xuất trang chi tiết để kiểm tra và chỉnh sửa từng bước"
                style={{ width: "100%", justifyContent: "center", marginBottom: "0.5rem" }}
              >
                <Sparkles size={15} /> Trích xuất trang (OCR)
              </button>
              <button
                type="button"
                className={styles.primaryGradeButton}
                onClick={() => void onSubmitSolution()}
                disabled={isSubmitting || isReviewing || submissionBlocked || !submission.canSubmit}
                title={submissionBlocked ? "Hãy hoàn tất phục hồi lưu OCR trước khi nộp bài" : !attempt.steps?.length ? "Trích xuất hoặc nhập bước giải để xác nhận trước khi nộp" : "Nộp bài và kiểm tra các bước đã xác nhận"}
              >
                <Sparkles size={16} />
                {isSubmitting ? "Đang nộp bản đã xác nhận…" : isReviewing ? "Đang kiểm tra bài..." : "Nộp bài & kiểm tra"}
              </button>
              {!attempt.steps?.length ? (
                <small className={styles.footerHint}>Trích xuất bằng Gemini → sửa và xác nhận bản chép → lưu bước giải → nộp chấm</small>
              ) : (
                <small className={styles.footerHint}>Đã có {attempt.steps.length} bước giải • Điểm chính thức chỉ có khi đủ đáp án và rubric</small>
              )}
            </div>
          )}
          {gradingError ? <p role="alert" className={styles.aiReviewError}>{gradingError}</p> : null}
        </div>
      ) : null}
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
    case "OPEN_RESPONSE":
      return "Tự luận";
    default:
      return type;
  }
}

function formatAttemptStatus(status: string): string {
  switch (status.toUpperCase()) {
    case "DRAFT":
      return "Bản nháp";
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
