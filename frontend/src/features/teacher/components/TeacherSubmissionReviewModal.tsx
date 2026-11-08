"use client";

import { useEffect, useState } from "react";
import {
  X,
  CheckCircle2,
  AlertCircle,
  Clock,
  Sparkles,
  FileCheck2,
  ChevronLeft,
  ChevronRight,
  Eye,
  MessageSquare,
  Award,
  Layers,
  HelpCircle,
} from "lucide-react";
import { MathRenderer } from "@/components/ui/MathRenderer";
import {
  teacherApi,
  type TeacherStudentSubmissionDetail,
  type TeacherSubmissionItem,
} from "../api";
import styles from "../TeacherDashboard.module.css";

export interface TeacherSubmissionReviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  assignmentId: string;
  studentId: string;
  studentName?: string;
  onUpdated: () => void;
}

export function TeacherSubmissionReviewModal({
  isOpen,
  onClose,
  assignmentId,
  studentId,
  studentName,
  onUpdated,
}: TeacherSubmissionReviewModalProps) {
  const [submission, setSubmission] = useState<TeacherStudentSubmissionDetail | null>(null);
  const [activeItemIndex, setActiveItemIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  // Grade edit states for the current item
  const [scoreInput, setScoreInput] = useState<number>(1.0);
  const [isCorrectInput, setIsCorrectInput] = useState<boolean>(true);
  const [feedbackInput, setFeedbackInput] = useState<string>("");
  const [isSavingItem, setIsSavingItem] = useState(false);
  const [isFinalizing, setIsFinalizing] = useState(false);

  // Load submission detail
  const loadSubmission = async () => {
    if (!assignmentId || !studentId) return;
    setIsLoading(true);
    setErrorMessage("");
    try {
      const data = await teacherApi.submissionDetail(assignmentId, studentId);
      setSubmission(data);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Không thể tải chi tiết bài làm.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      setActiveItemIndex(0);
      setSuccessMessage("");
      loadSubmission();
    } else {
      setSubmission(null);
    }
  }, [isOpen, assignmentId, studentId]);

  const currentItem: TeacherSubmissionItem | undefined = submission?.items[activeItemIndex];

  // Sync edit form with current item
  useEffect(() => {
    if (currentItem) {
      const defaultScore =
        currentItem.score !== null
          ? currentItem.score
          : currentItem.provisional_score !== null && currentItem.provisional_score !== undefined
          ? currentItem.provisional_score
          : 1.0;
      setScoreInput(defaultScore);
      setIsCorrectInput(
        currentItem.is_correct !== null
          ? currentItem.is_correct
          : defaultScore >= 0.8
      );
      setFeedbackInput(currentItem.teacher_feedback || "");
    }
  }, [currentItem]);

  if (!isOpen) return null;

  const handleSaveCurrentItemGrade = async () => {
    if (!currentItem || !submission || isSavingItem) return;
    setIsSavingItem(true);
    setErrorMessage("");
    setSuccessMessage("");
    try {
      if (currentItem.source_kind === "CANONICAL") {
        await teacherApi.gradeCanonicalItem(
          submission.assignment_id,
          submission.student_id,
          currentItem.id,
          scoreInput,
          isCorrectInput,
          feedbackInput.trim() || undefined
        );
      } else {
        await teacherApi.gradeMaterialItem(
          submission.assignment_id,
          submission.student_id,
          currentItem.id,
          scoreInput,
          isCorrectInput,
          feedbackInput.trim() || undefined
        );
      }
      setSuccessMessage(`Đã cập nhật điểm Câu ${activeItemIndex + 1}!`);
      setTimeout(() => setSuccessMessage(""), 2500);
      await loadSubmission();
      onUpdated();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Không thể lưu điểm câu hỏi.");
    } finally {
      setIsSavingItem(false);
    }
  };

  const handleFinalizeSubmission = async () => {
    if (!submission || isFinalizing) return;
    setIsFinalizing(true);
    setErrorMessage("");
    setSuccessMessage("");
    try {
      await teacherApi.finalizeSubmission(submission.assignment_id, submission.student_id);
      setSuccessMessage("Đã duyệt và chốt điểm chính thức thành công!");
      setTimeout(() => setSuccessMessage(""), 3000);
      await loadSubmission();
      onUpdated();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Không thể chốt điểm bài làm.");
    } finally {
      setIsFinalizing(false);
    }
  };

  const getScoreBadgeClass = (score: number | null, isCorrect: boolean | null) => {
    if (score === null) return styles.scoreBadgeUnscored;
    if (isCorrect === true || score >= 0.8) return styles.scoreBadgeHigh;
    if (score > 0) return styles.scoreBadgeMid;
    return styles.scoreBadgeLow;
  };

  return (
    <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-labelledby="review-submission-title">
      <div className={styles.modalContentFullScreen}>
        {/* Top Header */}
        <div className={styles.modalHeaderCompact}>
          <div className={styles.modalTitleGroup}>
            <div className={styles.modalIconWrap}>
              <Award size={20} />
            </div>
            <div>
              <div className={styles.reviewHeaderBadges}>
                <h2 id="review-submission-title" className={styles.modalTitle}>
                  Bài làm của {submission?.student_name || studentName || "Học sinh"}
                </h2>
                {submission && (
                  <span
                    className={
                      submission.delivery_mode === "EXAM"
                        ? styles.modeTagPurple
                        : styles.modeTagGreen
                    }
                  >
                    {submission.delivery_mode === "EXAM" ? "Đề Thi / Kiểm tra" : "Luyện tập từng câu"}
                  </span>
                )}
                <span className={styles.statusPillActive}>
                  {submission?.status === "GRADED"
                    ? "Giáo viên đã duyệt"
                    : submission?.status === "SUBMITTED"
                    ? "Chờ GV kiểm duyệt"
                    : submission?.status || "Đang tải"}
                </span>
                {submission?.score !== null && submission?.score !== undefined ? (
                  <span className={styles.overallScoreBadge}>
                    Điểm tổng: <strong>{submission.score <= 1.0 ? Number((submission.score * 10).toFixed(1)) : submission.score}/10</strong>
                  </span>
                ) : submission?.provisional_score !== null && submission?.provisional_score !== undefined ? (
                  <span className={styles.overallScoreBadge} style={{ background: "rgba(16, 185, 129, 0.12)", borderColor: "rgba(16, 185, 129, 0.4)", color: "#065f46" }}>
                    AI đề xuất: <strong>{submission.provisional_score <= 1.0 ? Number((submission.provisional_score * 10).toFixed(1)) : submission.provisional_score}/10</strong>
                  </span>
                ) : null}
              </div>
              <p className={styles.modalSubtitle}>
                {submission?.assignment_title || "Chi tiết đợt giao bài"} ·{" "}
                {submission?.submitted_at
                  ? `Nộp lúc: ${new Date(submission.submitted_at).toLocaleString("vi-VN")}`
                  : "Chưa ghi nhận thời điểm nộp"}
              </p>
            </div>
          </div>
          <button
            type="button"
            className={styles.modalCloseBtn}
            onClick={onClose}
            aria-label="Đóng cửa sổ"
          >
            <X size={18} />
          </button>
        </div>

        {/* Global Alerts */}
        {errorMessage && (
          <div className={styles.formAlert} role="alert">
            <AlertCircle size={16} />
            <span>{errorMessage}</span>
          </div>
        )}
        {successMessage && (
          <div className={styles.formSuccess} role="status">
            <CheckCircle2 size={16} />
            <span>{successMessage}</span>
          </div>
        )}

        {isLoading ? (
          <div className={styles.tableLoadingState}>
            <div className={styles.spinner} aria-hidden="true" />
            <p>Đang tải chi tiết bài giải của học sinh và đánh giá từng bước AI...</p>
          </div>
        ) : !submission || submission.items.length === 0 ? (
          <div className={styles.emptyCard}>
            <AlertCircle size={32} className={styles.emptyIcon} />
            <h4>Chưa có dữ liệu bài làm</h4>
            <p>Học sinh này chưa nộp câu hỏi nào trong bài giao đã chọn.</p>
          </div>
        ) : (
          <div className={styles.reviewMainWorkspace}>
            {/* 1. Horizontal Question Stepper Bar */}
            <div className={styles.questionStepperBar}>
              <div className={styles.questionStepperLabel}>
                Danh sách {submission.items.length} câu:
              </div>
              <div className={styles.questionStepperList}>
                {submission.items.map((item, idx) => {
                  const isActive = idx === activeItemIndex;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`${styles.stepperQuestionBtn} ${
                        isActive ? styles.stepperQuestionBtnActive : ""
                      }`}
                      onClick={() => setActiveItemIndex(idx)}
                    >
                      <span className={styles.stepperNumber}>Câu {idx + 1}</span>
                      <span
                        className={`${styles.stepperScoreChip} ${getScoreBadgeClass(
                          item.score,
                          item.is_correct
                        )}`}
                      >
                        {item.score !== null
                          ? `${Number((item.score * 10).toFixed(1))}/10`
                          : item.provisional_score !== null && item.provisional_score !== undefined
                          ? `AI: ${Number((item.provisional_score * 10).toFixed(1))}`
                          : "Chờ GV"}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* 2. Split Screen Review Area */}
            {currentItem && (
              <div className={styles.reviewSplitGrid}>
                {/* Left Column: Question Prompt & Student Submitted Steps */}
                <div className={styles.reviewLeftPane}>
                  <div className={styles.paneSectionHeader}>
                    <h3 className={styles.paneTitle}>
                      Đề bài Câu {activeItemIndex + 1} &amp; Bài làm của học sinh
                    </h3>
                    <span className={styles.tagPillSecondary}>
                      {currentItem.question_type || "Tự luận"}
                    </span>
                  </div>

                  {/* Problem statement */}
                  <div className={styles.reviewQuestionBox}>
                    <MathRenderer content={currentItem.content || "Không có nội dung câu hỏi."} />
                  </div>

                  {/* Options if MCQ */}
                  {currentItem.options && currentItem.options.length > 0 && (
                    <div className={styles.previewOptionsGrid}>
                      {currentItem.options.map((opt) => (
                        <div
                          key={opt.id}
                          className={`${styles.previewOptionRow} ${
                            currentItem.student_answer === opt.label
                              ? styles.previewOptionSelected
                              : ""
                          } ${
                            currentItem.correct_answer === opt.label
                              ? styles.previewOptionCorrect
                              : ""
                          }`}
                        >
                          <span className={styles.optionLabelBadge}>{opt.label}</span>
                          <div className={styles.optionTextContent}>
                            <MathRenderer content={opt.content} inline={true} />
                          </div>
                          {currentItem.student_answer === opt.label && (
                            <span className={styles.badgeChosen}>Học sinh chọn</span>
                          )}
                          {currentItem.correct_answer === opt.label && (
                            <span className={styles.badgeCorrect}>Đáp án chuẩn</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Reference Correct Answer if provided */}
                  {currentItem.correct_answer && currentItem.options.length === 0 && (
                    <div className={styles.referenceAnswerBox}>
                      <span className={styles.referenceAnswerLabel}>Đáp án chuẩn giáo viên:</span>
                      <div className={styles.referenceAnswerBody}>
                        <MathRenderer content={currentItem.correct_answer} />
                      </div>
                    </div>
                  )}

                  {/* Student Written Work / Steps */}
                  <div className={styles.studentWorkContainer}>
                    <h4 className={styles.subHeading}>Lời giải từng bước của học sinh:</h4>
                    {currentItem.steps && currentItem.steps.length > 0 ? (
                      <div className={styles.stepsSequence}>
                        {currentItem.steps.map((st) => (
                          <div key={st.step_id} className={styles.stepRowCard}>
                            <div className={styles.stepRowTop}>
                              <span className={styles.stepIndexPill}>Bước {st.step_index + 1}</span>
                              <span
                                className={
                                  st.math_validity === "VALID"
                                    ? styles.tagPillGreen
                                    : st.math_validity === "INVALID"
                                    ? styles.tagPillRed
                                    : styles.tagPillYellow
                                }
                              >
                                {st.math_validity === "VALID"
                                  ? "Hợp lệ ✔"
                                  : st.math_validity === "INVALID"
                                  ? "Có lỗi sai ✖"
                                  : "Cần xem xét ⚠️"}
                              </span>
                            </div>
                            {st.content_latex && (
                              <div className={styles.stepLatexWrap}>
                                <MathRenderer content={st.content_latex} />
                              </div>
                            )}
                            {st.explanation_text && (
                              <p className={styles.stepExplanationText}>
                                {st.explanation_text}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : currentItem.student_answer ? (
                      <div className={styles.studentTextAnswerBox}>
                        <MathRenderer content={currentItem.student_answer} />
                      </div>
                    ) : (
                      <p className={styles.emptyTextMuted}>
                        Học sinh không để lại lời giải dạng văn bản cho câu hỏi này.
                      </p>
                    )}

                    {/* Paper photos if student uploaded handwriting via QR */}
                    {currentItem.paper_attachments && currentItem.paper_attachments.length > 0 && (
                      <div className={styles.paperAttachmentsSection}>
                        <h4 className={styles.subHeading}>Ảnh chụp bài làm viết tay:</h4>
                        <div className={styles.paperPhotosGrid}>
                          {currentItem.paper_attachments.map((p) => (
                            <div key={p.id} className={styles.paperPhotoCard}>
                              <img
                                src={`/api/v3/math-solutions/attempts/${currentItem.attempt_id}/paper`}
                                alt={p.file_name}
                                className={styles.paperImg}
                              />
                              <span className={styles.paperFileName}>{p.file_name}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Right Column: AI Analysis & Teacher Check / Override */}
                <div className={styles.reviewRightPane}>
                  <div className={styles.paneSectionHeader}>
                    <h3 className={styles.paneTitle}>
                      Phân tích AI &amp; Quyết định của Giáo viên
                    </h3>
                    <Sparkles size={16} className={styles.textSky} />
                  </div>

                  {/* AI step-by-step assessment breakdown */}
                  <div className={styles.aiAssessmentBox}>
                    <div className={styles.aiAssessmentHeader}>
                      <span className={styles.aiBadgeTitle}>Trợ lý AI Đánh giá sơ bộ</span>
                      <span className={styles.aiConfidenceBadge}>
                        {currentItem.provisional_score !== null && currentItem.provisional_score !== undefined ? (
                          <>
                            AI đề xuất: <strong>{Number((currentItem.provisional_score * 10).toFixed(1))}/10</strong>
                          </>
                        ) : currentItem.score !== null ? (
                          <>
                            Điểm chính thức: <strong>{Number((currentItem.score * 10).toFixed(1))}/10</strong>
                          </>
                        ) : (
                          "Cần GV thẩm định tự luận"
                        )}
                      </span>
                    </div>

                    {currentItem.steps && currentItem.steps.some((s) => s.error_detected) ? (
                      <div className={styles.aiErrorList}>
                        {currentItem.steps
                          .filter((s) => s.error_detected)
                          .map((s) => (
                            <div key={s.step_id} className={styles.aiErrorItem}>
                              <AlertCircle size={14} className={styles.textAmber} />
                              <div>
                                <strong>Bước {s.step_index + 1}: </strong>
                                <span>{s.error_description || "Phát hiện sai sót toán học."}</span>
                              </div>
                            </div>
                          ))}
                      </div>
                    ) : (
                      <p className={styles.aiOkText}>
                        Không phát hiện lỗi ngộ nhận hoặc vi phạm toán học nghiêm trọng.
                      </p>
                    )}
                  </div>

                  {/* Teacher Grading & Override Controls */}
                  <div className={styles.teacherGradingBox}>
                    <h4 className={styles.teacherBoxTitle}>Chấm điểm &amp; Lời phê Giáo viên:</h4>

                    {/* Quick presets */}
                    <div className={styles.quickPresetButtons}>
                      {currentItem.provisional_score !== null && currentItem.provisional_score !== undefined && (
                        <button
                          type="button"
                          className={styles.presetBtnCorrect}
                          style={{ borderColor: "#10b981", color: "#065f46" }}
                          onClick={() => {
                            setScoreInput(currentItem.provisional_score!);
                            setIsCorrectInput(currentItem.provisional_score! >= 0.8);
                          }}
                        >
                          ✨ Nhận điểm AI ({Number((currentItem.provisional_score * 10).toFixed(1))}đ)
                        </button>
                      )}
                      <button
                        type="button"
                        className={styles.presetBtnCorrect}
                        onClick={() => {
                          setScoreInput(1.0);
                          setIsCorrectInput(true);
                        }}
                      >
                        ✔ Đúng (1.0đ)
                      </button>
                      <button
                        type="button"
                        className={styles.presetBtnPartial}
                        onClick={() => {
                          setScoreInput(0.5);
                          setIsCorrectInput(false);
                        }}
                      >
                        ⚠️ Đúng 1 phần (0.5đ)
                      </button>
                      <button
                        type="button"
                        className={styles.presetBtnWrong}
                        onClick={() => {
                          setScoreInput(0.0);
                          setIsCorrectInput(false);
                        }}
                      >
                        ✖ Sai (0.0đ)
                      </button>
                    </div>

                    {/* Score Slider & Inputs */}
                    <div className={styles.formGroup}>
                      <div className={styles.scoreInputRow}>
                        <label className={styles.formLabel}>Điểm câu này (thang 0.0 - 1.0):</label>
                        <input
                          type="number"
                          min="0"
                          max="1"
                          step="0.05"
                          className={styles.scoreNumberInput}
                          value={scoreInput}
                          onChange={(e) => setScoreInput(Number(e.target.value))}
                        />
                      </div>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={scoreInput}
                        onChange={(e) => setScoreInput(Number(e.target.value))}
                        className={styles.scoreSlider}
                      />
                    </div>

                    {/* Correctness Toggle */}
                    <div className={styles.formGroup}>
                      <label className={styles.checkboxLabel}>
                        <input
                          type="checkbox"
                          checked={isCorrectInput}
                          onChange={(e) => setIsCorrectInput(e.target.checked)}
                          className={styles.checkboxInput}
                        />
                        <span>Đánh dấu câu hỏi này ĐẠT YÊU CẦU (Chấp nhận kết quả)</span>
                      </label>
                    </div>

                    {/* Teacher Feedback textarea */}
                    <div className={styles.formGroup}>
                      <label htmlFor="teacher-feedback-input" className={styles.formLabel}>
                        Lời phê / Nhắc nhở của Giáo viên:
                      </label>
                      <textarea
                        id="teacher-feedback-input"
                        className={styles.formTextarea}
                        rows={3}
                        placeholder="VD: Em làm đúng hướng nhưng chú ý dấu âm khi rút gọn ở bước 2..."
                        value={feedbackInput}
                        onChange={(e) => setFeedbackInput(e.target.value)}
                      />
                    </div>

                    {/* Save Button for this item */}
                    <button
                      type="button"
                      className={styles.btnPrimary}
                      onClick={handleSaveCurrentItemGrade}
                      disabled={isSavingItem}
                    >
                      {isSavingItem ? (
                        <>Đang lưu điểm...</>
                      ) : (
                        <>
                          <CheckCircle2 size={15} />
                          Lưu điểm &amp; Lời phê Câu {activeItemIndex + 1}
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* 3. Bottom Action Bar */}
            <div className={styles.reviewBottomBar}>
              <div className={styles.stepperNavButtons}>
                <button
                  type="button"
                  className={styles.btnSecondary}
                  onClick={() => setActiveItemIndex((curr) => Math.max(0, curr - 1))}
                  disabled={activeItemIndex === 0}
                >
                  <ChevronLeft size={16} /> Câu trước
                </button>
                <button
                  type="button"
                  className={styles.btnSecondary}
                  onClick={() =>
                    setActiveItemIndex((curr) => Math.min(submission.items.length - 1, curr + 1))
                  }
                  disabled={activeItemIndex === submission.items.length - 1}
                >
                  Câu tiếp theo <ChevronRight size={16} />
                </button>
              </div>

              <div className={styles.finalizeButtonGroup}>
                <button
                  type="button"
                  className={styles.btnAccentGreen}
                  onClick={handleFinalizeSubmission}
                  disabled={isFinalizing}
                >
                  {isFinalizing ? (
                    <>Đang chốt điểm...</>
                  ) : (
                    <>
                      <FileCheck2 size={16} />
                      Xác nhận &amp; Trả bài (Chốt điểm chính thức)
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
