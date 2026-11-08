"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileCheck,
  HelpCircle,
  Layers,
  Send,
  Sparkles,
  XCircle,
} from "lucide-react";

import styles from "../assignments.module.css";
import { getCsrfToken } from "@/lib/auth/browser";
import { QuestionContent } from "@/components/ui/QuestionContent";
import type { QuestionVisual } from "@/lib/api/question-visuals";

export interface QuestionItem {
  source_kind: "CANONICAL_QUESTION" | "TEACHER_MATERIAL_ITEM" | "CANONICAL" | "TEACHER_MATERIAL";
  question_id?: string | null;
  teacher_material_item_id?: string | null;
  assignment_material_item_id?: string | null;
  student_material_item_id?: string | null;
  order_index: number;
  content: string;
  visuals?: QuestionVisual[];
  question_type: string;
  difficulty?: number | null;
  options?: Array<{ id: string; label: string; content: string; order_index: number }>;
  student_answer?: string | null;
  is_correct?: boolean | null;
  score?: number | null;
  correct_answer?: string | null;
  explanation?: string | null;
}

export interface AssignmentDetail {
  id: string; // student_assignment_id
  assignment_id: string;
  title: string;
  description?: string | null;
  delivery_mode: "PRACTICE" | "EXAM";
  status: "NOT_STARTED" | "IN_PROGRESS" | "SUBMITTED" | "GRADED";
  question_count: number;
  due_at?: string | null;
  score?: number | null;
  questions: QuestionItem[];
}

export function AssignmentWorkspaceClient({
  initialAssignment,
}: {
  initialAssignment: AssignmentDetail;
}) {
  const router = useRouter();
  const [assignment, setAssignment] = useState<AssignmentDetail>(initialAssignment);
  const [activeIdx, setActiveIdx] = useState<number>(0);

  // Per-question answers/drafts
  const [studentAnswers, setStudentAnswers] = useState<Record<number, string>>(() => {
    const init: Record<number, string> = {};
    initialAssignment.questions.forEach((q, idx) => {
      init[idx] = q.student_answer || "";
    });
    return init;
  });

  const [stepExplanations, setStepExplanations] = useState<Record<number, string>>({});
  const [stepFeedback, setStepFeedback] = useState<Record<number, any>>({});
  const [isGradingStep, setIsGradingStep] = useState<boolean>(false);
  const [isSubmittingExam, setIsSubmittingExam] = useState<boolean>(false);
  const [showSubmitModal, setShowSubmitModal] = useState<boolean>(false);
  const [revealedSolutions, setRevealedSolutions] = useState<Record<number, boolean>>({});
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [successMessage, setSuccessMessage] = useState<string>("");

  const currentQ: QuestionItem | undefined = assignment.questions[activeIdx];
  const isExam = assignment.delivery_mode === "EXAM";
  const isFinalized = assignment.status === "GRADED" || assignment.status === "SUBMITTED";

  // Handlers
  const handleAnswerChange = (val: string) => {
    setStudentAnswers((prev) => ({ ...prev, [activeIdx]: val }));
  };

  const handleExplanationChange = (val: string) => {
    setStepExplanations((prev) => ({ ...prev, [activeIdx]: val }));
  };

  // Grade single step with AI (PRACTICE MODE)
  const handleGradeCurrentStep = async () => {
    if (!currentQ || isGradingStep) return;
    const answerText = studentAnswers[activeIdx] || "";
    if (!answerText.trim()) {
      setErrorMessage("Vui lòng nhập bước giải hoặc đáp án của bạn trước khi chấm.");
      return;
    }

    setIsGradingStep(true);
    setErrorMessage("");
    setSuccessMessage("");

    try {
      const isCanonical = currentQ.source_kind === "CANONICAL" || currentQ.source_kind === "CANONICAL_QUESTION";
      const itemId = isCanonical ? currentQ.question_id : (currentQ.student_material_item_id || currentQ.teacher_material_item_id);
      const snapshotId = isCanonical ? currentQ.question_id : (currentQ.assignment_material_item_id || currentQ.teacher_material_item_id);

      const csrfToken = await getCsrfToken().catch(() => "");
      const res = await fetch(`/api/student/assignments/${assignment.id}/grade-step`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
        },
        body: JSON.stringify({
          source_kind: isCanonical ? "CANONICAL" : "TEACHER_MATERIAL",
          student_assignment_id: assignment.id,
          item_id: itemId,
          snapshot_id: snapshotId,
          step_latex: answerText,
          explanation: stepExplanations[activeIdx] || "",
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error?.message || "Không thể chấm bước giải.");
      }

      const review = data.review;
      setStepFeedback((prev) => ({ ...prev, [activeIdx]: review }));
      setSuccessMessage("🌱 AI đã chấm xong bước giải của bạn và cập nhật vào Cây tri thức!");

      // Update question state in UI
      const primaryStep = review.step_grades?.[0];
      const isStepValid = primaryStep?.verdict === "VALID";
      const qScore = isStepValid ? 1.0 : (primaryStep?.score ?? 0.5);

      setAssignment((prev) => {
        const nextQuestions = [...prev.questions];
        nextQuestions[activeIdx] = {
          ...nextQuestions[activeIdx],
          is_correct: isStepValid,
          score: qScore,
        };
        return { ...prev, questions: nextQuestions };
      });
    } catch (err: any) {
      setErrorMessage(err.message || "Đã xảy ra lỗi khi chấm bước giải.");
    } finally {
      setIsGradingStep(false);
    }
  };

  // Submit Exam (EXAM MODE)
  const handleSubmitExam = async () => {
    setIsSubmittingExam(true);
    setErrorMessage("");
    setSuccessMessage("");

    try {
      const answersPayload = assignment.questions.map((q, idx) => {
        const isCanonical = q.source_kind === "CANONICAL" || q.source_kind === "CANONICAL_QUESTION";
        return {
          question_id: isCanonical ? q.question_id : undefined,
          teacher_material_item_id: !isCanonical ? (q.teacher_material_item_id || q.assignment_material_item_id) : undefined,
          student_answer: studentAnswers[idx] || "",
        };
      });

      const csrfToken = await getCsrfToken().catch(() => "");
      const res = await fetch(`/api/student/assignments/${assignment.id}/submit`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
        },
        body: JSON.stringify({ answers: answersPayload }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error?.message || "Không thể nộp bài thi.");
      }

      setShowSubmitModal(false);
      setAssignment((prev) => ({ ...prev, status: "SUBMITTED" }));
      setSuccessMessage("🎉 Bạn đã nộp bài thi thành công! Đề thi đã được chuyển đến Giáo viên để chấm điểm.");
      setTimeout(() => {
        router.refresh();
      }, 1500);
    } catch (err: any) {
      setErrorMessage(err.message || "Đã xảy ra lỗi khi nộp bài thi.");
    } finally {
      setIsSubmittingExam(false);
    }
  };

  const answeredCount = Object.values(studentAnswers).filter((s) => s.trim().length > 0).length;

  return (
    <div className={styles.canvas}>
      <main className={styles.mainContainer}>
        {/* Workspace Top Bar */}
        <div className={styles.workspaceTopBar}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
            <Link href="/student/attempts?tab=classroom" className={styles.btnActionSecondary}>
              <ArrowLeft size={16} /> Quay lại
            </Link>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.2rem" }}>
                {isExam ? (
                  <span className={styles.modeBadgeExam}>
                    <FileCheck size={14} /> Kiểm tra tập trung
                  </span>
                ) : (
                  <span className={styles.modeBadgePractice}>
                    <Sparkles size={14} /> Luyện tập từng câu
                  </span>
                )}
                <span className={styles.statusPill}>
                  {assignment.status === "GRADED"
                    ? "Đã có điểm"
                    : assignment.status === "SUBMITTED"
                    ? "Đã nộp bài"
                    : "Đang làm bài"}
                </span>
              </div>
              <h1 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0, color: "#0F172A" }}>
                {assignment.title}
              </h1>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <div style={{ fontSize: "0.875rem", color: "#64748B" }}>
              Tiến độ: <b>{answeredCount}/{assignment.questions.length}</b> câu
            </div>
            <button
              type="button"
              className={styles.btnAction}
              onClick={async () => {
                try {
                  const csrfToken = await getCsrfToken().catch(() => "");
                  const res = await fetch(`/api/student/assignments/${assignment.id}/launch`, {
                    method: "POST",
                    headers: {
                      "Content-Type": "application/json",
                      ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
                    },
                    body: JSON.stringify({ index: activeIdx }),
                  });
                  if (res.ok) {
                    const data = await res.json();
                    if (data.attemptId) {
                      router.push(`/student/attempts/${data.attemptId}`);
                    }
                  }
                } catch {}
              }}
              style={{ background: "#059669", color: "#ffffff", display: "inline-flex", alignItems: "center", gap: "6px" }}
            >
              <Sparkles size={16} /> Làm bài trên Canvas
            </button>
            {isExam && !isFinalized && (
              <button
                type="button"
                className={styles.btnActionSecondary}
                onClick={() => setShowSubmitModal(true)}
              >
                <Send size={15} /> Nộp bài kiểm tra
              </button>
            )}
          </div>
        </div>

        {/* Question Navigator */}
        <div style={{ margin: "1.25rem 0 0.5rem" }}>
          <div className={styles.questionNavigatorBar}>
            {assignment.questions.map((q, idx) => {
              const isActive = idx === activeIdx;
              const hasAnswer = (studentAnswers[idx] || "").trim().length > 0;
              const isGradedCorrect = q.is_correct === true;
              const isGradedWrong = q.is_correct === false;

              let pillClass = styles.qNavPill;
              if (isActive) pillClass += ` ${styles.qNavPillActive}`;
              else if (isGradedCorrect) pillClass += ` ${styles.qNavPillGradedOk}`;
              else if (isGradedWrong) pillClass += ` ${styles.qNavPillGradedWarn}`;
              else if (hasAnswer) pillClass += ` ${styles.qNavPillAnswered}`;

              return (
                <button
                  key={idx}
                  type="button"
                  className={pillClass}
                  onClick={() => {
                    setActiveIdx(idx);
                    setErrorMessage("");
                    setSuccessMessage("");
                  }}
                >
                  {idx + 1}
                </button>
              );
            })}
          </div>
        </div>

        {/* Notification alerts */}
        {errorMessage && (
          <div style={{ background: "#FEF2F2", border: "1px solid #FCA5A5", color: "#991B1B", padding: "0.85rem 1.25rem", borderRadius: "0.75rem", margin: "1rem 0" }}>
            ⚠️ {errorMessage}
          </div>
        )}
        {successMessage && (
          <div style={{ background: "#ECFDF5", border: "1px solid #6EE7B7", color: "#065F46", padding: "0.85rem 1.25rem", borderRadius: "0.75rem", margin: "1rem 0" }}>
            {successMessage}
          </div>
        )}

        {/* Current Question Main Card */}
        {currentQ ? (
          <div className={styles.questionCardMain}>
            <div className={styles.questionHeader}>
              <h2 className={styles.questionIndexTitle}>
                Câu {activeIdx + 1} / {assignment.questions.length}
              </h2>
              <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                {currentQ.difficulty && (
                  <span style={{ fontSize: "0.8125rem", background: "#F1F5F9", color: "#475569", padding: "0.2rem 0.6rem", borderRadius: "9999px" }}>
                    Độ khó: {Math.round(currentQ.difficulty * 100)}%
                  </span>
                )}
                {currentQ.score !== null && currentQ.score !== undefined && (
                  <span style={{ fontSize: "0.875rem", fontWeight: 700, color: currentQ.score >= 0.7 ? "#059669" : "#D97706" }}>
                    Điểm: {Math.round(currentQ.score * 10) / 10}đ
                  </span>
                )}
              </div>
            </div>

            {/* Question Content */}
            <div className={styles.questionContentBox}>
              <QuestionContent content={currentQ.content} visuals={currentQ.visuals} relatedContent={currentQ.options?.map((option) => option.content)} />
            </div>

            {/* Multiple Choice Options (if present) */}
            {currentQ.options && currentQ.options.length > 0 && (
              <div className={styles.optionsList}>
                {currentQ.options.map((opt) => {
                  const isSelected = studentAnswers[activeIdx] === opt.label;
                  return (
                    <label
                      key={opt.id}
                      className={`${styles.optionItemLabel} ${isSelected ? styles.optionItemSelected : ""}`}
                      onClick={() => !isFinalized && handleAnswerChange(opt.label)}
                    >
                      <input
                        type="radio"
                        name={`q-${activeIdx}`}
                        checked={isSelected}
                        onChange={() => !isFinalized && handleAnswerChange(opt.label)}
                        disabled={isFinalized}
                      />
                      <div>
                        <b>{opt.label}.</b> <QuestionContent content={opt.content} visuals={currentQ.visuals} gallery={false} inline />
                      </div>
                    </label>
                  );
                })}
              </div>
            )}

            {/* Step-by-step Solution Editor */}
            <div className={styles.stepSolutionSection}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem", flexWrap: "wrap", gap: "8px" }}>
                <h3 className={styles.sectionSubtitle} style={{ margin: 0 }}>
                  <Sparkles size={16} color="#059669" />
                  {isExam ? "Lời giải / Bài làm của bạn:" : "Bước giải chi tiết (Hệ thống AI sẽ phân tích từng dòng toán học):"}
                </h3>
                <Link
                  href="/student/attempts?tab=practice"
                  target="_blank"
                  style={{ fontSize: "0.8125rem", color: "#059669", textDecoration: "none", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: "4px" }}
                >
                  📝 Mở Giấy số / Bút vẽ ↗
                </Link>
              </div>
              <textarea
                className={styles.stepLatexTextarea}
                rows={4}
                placeholder="VD: y' = 3x^2 - 6x = 0 <=> x = 0 hoặc x = 2..."
                value={studentAnswers[activeIdx] || ""}
                onChange={(e) => handleAnswerChange(e.target.value)}
                disabled={isFinalized}
              />

              {!isExam && (
                <>
                  <div style={{ fontSize: "0.85rem", color: "#64748B", marginBottom: "0.5rem" }}>
                    Giải thích thêm lý do hoặc định lý bạn áp dụng (không bắt buộc):
                  </div>
                  <input
                    type="text"
                    style={{ width: "100%", padding: "0.6rem 0.85rem", borderRadius: "0.5rem", border: "1px solid #CBD5E1", fontSize: "0.875rem", marginBottom: "1rem" }}
                    placeholder="VD: Áp dụng công thức đạo hàm hàm hợp (u^n)' = n * u^(n-1) * u'..."
                    value={stepExplanations[activeIdx] || ""}
                    onChange={(e) => handleExplanationChange(e.target.value)}
                    disabled={isFinalized}
                  />

                  {/* AI Step Review Button for Practice Mode */}
                  {!isFinalized && (
                    <button
                      type="button"
                      className={styles.btnAction}
                      onClick={handleGradeCurrentStep}
                      disabled={isGradingStep}
                    >
                      {isGradingStep ? "🤖 AI đang phân tích..." : "⚡ Chấm bước giải này với AI"}
                    </button>
                  )}
                </>
              )}

              {/* Instant Step Feedback Box */}
              {stepFeedback[activeIdx] && (
                <div className={stepFeedback[activeIdx].step_grades?.[0]?.verdict === "VALID" ? styles.feedbackBoxSuccess : styles.feedbackBoxWarning}>
                  <div className={styles.feedbackTitle}>
                    {stepFeedback[activeIdx].step_grades?.[0]?.verdict === "VALID" ? (
                      <>
                        <CheckCircle2 size={18} color="#15803D" />
                        Chính xác! Lời giải toán học hợp lệ
                      </>
                    ) : (
                      <>
                        <AlertCircle size={18} color="#B45309" />
                        Cần lưu ý: Lời giải có điểm chưa chính xác
                      </>
                    )}
                  </div>
                  <p style={{ margin: 0, fontSize: "0.9rem", lineHeight: 1.5 }}>
                    {stepFeedback[activeIdx].step_grades?.[0]?.feedback || "Bước giải đã được ghi nhận."}
                  </p>
                </div>
              )}

              {/* Reference Solution Reveal */}
              {(currentQ.explanation || currentQ.correct_answer) && (revealedSolutions[activeIdx] || isFinalized) && (
                <div className={styles.explanationRevealBox}>
                  <b>💡 Lời giải tham khảo từ Giáo viên:</b>
                  <div style={{ marginTop: "0.5rem" }}>
                    {currentQ.correct_answer && <div><b>Đáp số:</b> <QuestionContent content={currentQ.correct_answer} visuals={currentQ.visuals} role="answer" /></div>}
                    {currentQ.explanation && <div style={{ marginTop: "0.25rem" }}><QuestionContent content={currentQ.explanation} visuals={currentQ.visuals} role="solution" /></div>}
                  </div>
                </div>
              )}

              {!isExam && (currentQ.explanation || currentQ.correct_answer) && !revealedSolutions[activeIdx] && !isFinalized && (
                <button
                  type="button"
                  style={{ background: "none", border: "none", color: "#2563EB", cursor: "pointer", fontSize: "0.85rem", marginTop: "0.75rem", padding: 0 }}
                  onClick={() => setRevealedSolutions((p) => ({ ...p, [activeIdx]: true }))}
                >
                  🔍 Xem lời giải gợi ý của đề
                </button>
              )}
            </div>

            {/* Stepper Navigation Buttons */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "2rem", paddingTop: "1.25rem", borderTop: "1px solid #F1F5F9" }}>
              <button
                type="button"
                className={styles.btnActionSecondary}
                onClick={() => setActiveIdx((i) => Math.max(0, i - 1))}
                disabled={activeIdx === 0}
              >
                <ArrowLeft size={16} /> Câu trước
              </button>

              {activeIdx < assignment.questions.length - 1 ? (
                <button
                  type="button"
                  className={styles.btnAction}
                  onClick={() => setActiveIdx((i) => Math.min(assignment.questions.length - 1, i + 1))}
                >
                  Câu tiếp theo <ArrowRight size={16} />
                </button>
              ) : (
                isExam && !isFinalized && (
                  <button
                    type="button"
                    className={styles.btnAction}
                    onClick={() => setShowSubmitModal(true)}
                  >
                    <Send size={15} /> Hoàn thành &amp; Nộp bài
                  </button>
                )
              )}
            </div>
          </div>
        ) : null}

        {/* Confirmation Modal for Exam Submission */}
        {showSubmitModal && (
          <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: "1rem" }}>
            <div style={{ background: "white", borderRadius: "1.25rem", maxWidth: "460px", width: "100%", padding: "1.75rem", boxShadow: "0 20px 25px -5px rgba(0,0,0,0.2)" }}>
              <h3 style={{ fontSize: "1.2rem", fontWeight: 700, margin: "0 0 0.75rem", color: "#0F172A" }}>
                Xác nhận nộp bài kiểm tra?
              </h3>
              <p style={{ fontSize: "0.925rem", color: "#475569", lineHeight: 1.5, margin: "0 0 1.25rem" }}>
                Bạn đã làm <b>{answeredCount}/{assignment.questions.length}</b> câu hỏi. Sau khi nộp, bạn sẽ không thể chỉnh sửa đáp án và bài làm sẽ được chuyển sang Giáo viên để chấm điểm.
              </p>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                <button
                  type="button"
                  className={styles.btnActionSecondary}
                  onClick={() => setShowSubmitModal(false)}
                  disabled={isSubmittingExam}
                >
                  Tiếp tục làm bài
                </button>
                <button
                  type="button"
                  className={styles.btnAction}
                  onClick={handleSubmitExam}
                  disabled={isSubmittingExam}
                >
                  {isSubmittingExam ? "Đang gửi..." : "Đồng ý nộp bài"}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
