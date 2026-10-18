"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Plus,
  Send,
  AlertCircle,
  CheckCircle2,
  BookOpen,
  ArrowRight,
  Loader2,
  HelpCircle,
} from "lucide-react";
import type {
  SolutionSolverAttempt,
  SolutionStepItem,
  StepKind,
  SignTablePayload,
} from "./types";
import { STEP_KINDS, STEP_KIND_DISPLAY_NAMES } from "./types";
import { StepCard } from "./components/StepCard";
import { SignTableEditor } from "./components/SignTableEditor";
import { RevisionViewerModal } from "./components/RevisionViewerModal";
import { reorderStepsList, canSubmitAttempt } from "./utils";
import type { ProblemRead } from "@/lib/api/contracts";
import styles from "./MathSolutionSolver.module.css";

function generateClientActionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

interface MathSolutionSolverProps {
  attemptId: string;
  accessToken: string;
  initialProblem?: ProblemRead | null;
  initialAttempt?: SolutionSolverAttempt | null;
  apiBaseUrl?: string;
}

export function MathSolutionSolver({
  attemptId,
  accessToken,
  initialProblem = null,
  initialAttempt = null,
  apiBaseUrl = "",
}: MathSolutionSolverProps) {
  const [attempt, setAttempt] = useState<SolutionSolverAttempt | null>(initialAttempt);
  const [problem, setProblem] = useState<ProblemRead | null>(initialProblem);
  const [isLoading, setIsLoading] = useState(!initialAttempt);
  const [actionError, setActionError] = useState<string | null>(null);

  const baseUrl = apiBaseUrl || "";

  // New step draft state
  const [isAddingStep, setIsAddingStep] = useState(false);
  const [newStepType, setNewStepType] = useState<StepKind>("DERIVATIVE_CALCULATION");
  const [newContentLatex, setNewContentLatex] = useState("");
  const [newExplanation, setNewExplanation] = useState("");
  const [newSignTable, setNewSignTable] = useState<SignTablePayload>({
    // Start without exercise-specific roots or pre-filled correct signs.
    critical_points: [],
    signs: ["+"],
  });
  const [isSavingStep, setIsSavingStep] = useState(false);

  // Revision viewer modal state
  const [selectedStepForRevision, setSelectedStepForRevision] = useState<SolutionStepItem | null>(null);

  // Submit attempt state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);

  // Fetch attempt and problem data
  const loadData = useCallback(async () => {
    setIsLoading(true);
    setActionError(null);
    try {
      const headers = {
        Authorization: `Bearer ${accessToken}`,
        Accept: "application/json",
      };

      const [attemptRes, problemRes] = await Promise.all([
        fetch(`${baseUrl}/api/v2/math-solutions/attempts/${attemptId}`, { headers }),
        fetch(`${baseUrl}/api/v2/math-solutions/attempts/${attemptId}/problem`, { headers }),
      ]);

      if (!attemptRes.ok) {
        throw new Error(`Không thể nạp bài giải (mã lỗi: ${attemptRes.status})`);
      }
      const attemptData = await attemptRes.json();
      setAttempt(attemptData);

      if (problemRes.ok) {
        const problemData = await problemRes.json();
        setProblem(problemData);
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Lỗi khi nạp dữ liệu bài tập");
    } finally {
      setIsLoading(false);
    }
  }, [attemptId, accessToken]);

  useEffect(() => {
    if (!initialAttempt) {
      loadData();
    }
  }, [initialAttempt, loadData]);

  const isReadOnly = attempt?.status === "SUBMITTED" || attempt?.status === "EVALUATED";

  // Add Step
  const handleAddStepSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!attempt || isReadOnly) return;

    setIsSavingStep(true);
    setActionError(null);

    const body: Record<string, unknown> = {
      expected_attempt_revision: attempt.attempt_revision_number,
      client_action_id: generateClientActionId(),
      step_type: newStepType,
      content_latex: newContentLatex.trim() || null,
      explanation_text: newExplanation.trim() || null,
    };

    if (newStepType === "SIGN_TABLE") {
      body.artifact = {
        artifact_type: "SIGN_TABLE",
        payload: newSignTable,
      };
      if (!body.content_latex) {
        body.content_latex = "Bảng xét dấu đạo hàm";
      }
    }

    try {
      const res = await fetch(`${baseUrl}/api/v2/math-solutions/attempts/${attempt.id}/steps`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        throw new Error(errJson?.message || `Lỗi khi lưu bước giải (HTTP ${res.status})`);
      }

      const updatedAttempt = await res.json();
      setAttempt(updatedAttempt);
      // Reset form
      setNewContentLatex("");
      setNewExplanation("");
      setIsAddingStep(false);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Lỗi khi thêm bước giải");
    } finally {
      setIsSavingStep(false);
    }
  };

  // Reorder Steps (Move Up / Down)
  const handleReorderStep = async (stepId: string, direction: "up" | "down") => {
    if (!attempt || isReadOnly) return;
    const reorderedResult = reorderStepsList(attempt.steps || [], stepId, direction);
    if (!reorderedResult) return;
    const { stepIds } = reorderedResult;

    try {
      const res = await fetch(`${baseUrl}/api/v2/math-solutions/attempts/${attempt.id}/reorder`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          expected_attempt_revision: attempt.attempt_revision_number,
          client_action_id: generateClientActionId(),
          step_ids: stepIds,
        }),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        throw new Error(errJson?.message || `Lỗi khi đổi thứ tự bước (HTTP ${res.status})`);
      }

      const updatedAttempt = await res.json();
      setAttempt(updatedAttempt);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Lỗi khi đổi thứ tự bước");
    }
  };

  // Delete Step
  const handleDeleteStep = async (stepId: string) => {
    if (!attempt || isReadOnly) return;
    if (!confirm("Bạn có chắc chắn muốn xóa bước giải này?")) return;

    try {
      const res = await fetch(
        `${baseUrl}/api/v2/math-solutions/attempts/${attempt.id}/steps/${stepId}/delete`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${accessToken}`,
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({
            expected_attempt_revision: attempt.attempt_revision_number,
            client_action_id: generateClientActionId(),
          }),
        },
      );

      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        throw new Error(errJson?.message || `Lỗi khi xóa bước (HTTP ${res.status})`);
      }

      const updatedAttempt = await res.json();
      setAttempt(updatedAttempt);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Lỗi khi xóa bước giải");
    }
  };

  // Rollback Step
  const handleRollbackStep = async (stepId: string, toRevision: number) => {
    if (!attempt || isReadOnly) return;

    const res = await fetch(
      `${baseUrl}/api/v2/math-solutions/attempts/${attempt.id}/steps/${stepId}/rollback`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          expected_attempt_revision: attempt.attempt_revision_number,
          client_action_id: generateClientActionId(),
          to_revision: toRevision,
        }),
      },
    );

    if (!res.ok) {
      const errJson = await res.json().catch(() => null);
      throw new Error(errJson?.message || `Lỗi khi khôi phục bước giải (HTTP ${res.status})`);
    }

    const updatedAttempt = await res.json();
    setAttempt(updatedAttempt);
  };

  // Submit Attempt
  const handleSubmitAttempt = async () => {
    if (!attempt || isReadOnly) return;
    const check = canSubmitAttempt(attempt.steps, attempt.status);
    if (!check.canSubmit) {
      setActionError(check.reason ?? "Không thể nộp bài.");
      return;
    }

    if (!confirm("Sau khi nộp bài, bạn sẽ không thể chỉnh sửa các bước giải nữa. Bạn có chắc chắn muốn nộp bài?")) {
      return;
    }

    setIsSubmitting(true);
    setActionError(null);

    try {
      const res = await fetch(`${baseUrl}/api/v2/math-solutions/attempts/${attempt.id}/submit`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          expected_attempt_revision: attempt.attempt_revision_number,
          client_action_id: generateClientActionId(),
        }),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        throw new Error(errJson?.message || `Lỗi khi nộp bài giải (HTTP ${res.status})`);
      }

      const submittedAttempt = await res.json();
      setAttempt(submittedAttempt);
      setSubmitSuccess(true);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Lỗi khi nộp bài giải");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className={styles.loadingContainer}>
        <Loader2 className={styles.spinIcon} size={32} />
        <p>Đang tải không gian giải toán...</p>
      </div>
    );
  }

  const activeSteps = (attempt?.steps || []).filter((s) => !s.is_deleted);

  return (
    <div className={styles.solverContainer}>
      {/* Top Header */}
      <header className={styles.header}>
        <div className={styles.headerInfo}>
          <h1 className={styles.headerTitle}>Trình giải toán từng bước (Step Solver)</h1>
          <div className={styles.attemptStatusRow}>
            <span
              className={`${styles.statusPill} ${
                attempt?.status === "EVALUATED"
                  ? styles.statusEvaluated
                  : attempt?.status === "SUBMITTED"
                  ? styles.statusSubmitted
                  : styles.statusInProgress
              }`}
            >
              Trạng thái: {attempt?.status}
            </span>
            <span className={styles.revisionPill}>
              Phiên làm việc: #{attempt?.attempt_revision_number}
            </span>
          </div>
        </div>

        {/* Action button: Submit */}
        {!isReadOnly && (
          <button
            type="button"
            className={styles.submitBtn}
            onClick={handleSubmitAttempt}
            disabled={isSubmitting || activeSteps.length === 0}
          >
            {isSubmitting ? (
              <Loader2 className={styles.spinIcon} size={16} />
            ) : (
              <Send size={16} />
            )}
            Nộp bài giải
          </button>
        )}
      </header>

      {/* Alert Notices */}
      {actionError && (
        <div className={styles.errorAlert} role="alert">
          <AlertCircle size={18} />
          <span>{actionError}</span>
        </div>
      )}

      {submitSuccess && (
        <div className={styles.successAlert} role="status">
          <CheckCircle2 size={18} />
          <span>
            Bài giải đã nộp thành công! Hệ thống đang tiến hành phân tích sư phạm 4 tầng và đánh giá năng lực của bạn.
          </span>
        </div>
      )}

      {/* Main Grid: Problem on left, Steps on right */}
      <main className={styles.mainGrid}>
        {/* Left: Problem Details */}
        <section className={styles.problemSection} aria-label="Đề bài">
          <div className={styles.problemCard}>
            <div className={styles.cardHeader}>
              <BookOpen size={18} className={styles.problemIcon} />
              <h2 className={styles.problemTitle}>Đề bài</h2>
            </div>
            <div className={styles.problemContent}>
              <p className={styles.problemText}>
                {problem?.content || "Đang tải đề bài toán..."}
              </p>
            </div>
            {isReadOnly && (
              <div className={styles.readOnlyNotice}>
                <p>Bài làm đã được nộp. Không thể thêm hoặc chỉnh sửa các bước giải.</p>
              </div>
            )}
          </div>
        </section>

        {/* Right: Steps Feed */}
        <section className={styles.stepsSection} aria-label="Các bước giải">
          <div className={styles.stepsHeader}>
            <h2 className={styles.stepsTitle}>
              Các bước giải ({activeSteps.length})
            </h2>

            {!isReadOnly && !isAddingStep && (
              <button
                type="button"
                className={styles.addStepTriggerBtn}
                onClick={() => setIsAddingStep(true)}
              >
                <Plus size={16} />
                Thêm bước giải
              </button>
            )}
          </div>

          {/* Add Step Card Form */}
          {!isReadOnly && isAddingStep && (
            <form onSubmit={handleAddStepSubmit} className={styles.addStepCard}>
              <div className={styles.addStepHeader}>
                <span className={styles.addStepTitle}>Bước mới #{activeSteps.length + 1}</span>
                <button
                  type="button"
                  className={styles.cancelAddBtn}
                  onClick={() => setIsAddingStep(false)}
                >
                  Hủy
                </button>
              </div>

              {/* Step Type Selector */}
              <div className={styles.formGroup}>
                <label htmlFor="step-type-select" className={styles.formLabel}>
                  Phân loại bước giải:
                </label>
                <select
                  id="step-type-select"
                  className={styles.formSelect}
                  value={newStepType}
                  onChange={(e) => setNewStepType(e.target.value as StepKind)}
                >
                  {STEP_KINDS.map((kind) => (
                    <option key={kind} value={kind}>
                      {STEP_KIND_DISPLAY_NAMES[kind] || kind}
                    </option>
                  ))}
                </select>
              </div>

              {/* If SIGN_TABLE is selected, render SignTableEditor */}
              {newStepType === "SIGN_TABLE" && (
                <div className={styles.formGroup}>
                  <SignTableEditor
                    value={newSignTable}
                    onChange={setNewSignTable}
                  />
                </div>
              )}

              {/* LaTeX Formula Input */}
              <div className={styles.formGroup}>
                <label htmlFor="content-latex-input" className={styles.formLabel}>
                  Công thức LaTeX (tùy chọn nếu đã dùng Bảng xét dấu):
                </label>
                <textarea
                  id="content-latex-input"
                  className={styles.formTextarea}
                  rows={2}
                  value={newContentLatex}
                  onChange={(e) => setNewContentLatex(e.target.value)}
                  placeholder={
                    newStepType === "DERIVATIVE_CALCULATION"
                      ? "Ví dụ: y' = 3x^2 - 6x - 9"
                      : newStepType === "ROOT_FINDING"
                      ? "Ví dụ: y' = 0 <=> x = -1 hoặc x = 3"
                      : newStepType === "CONCLUSION"
                      ? "Ví dụ: Hàm số đồng biến trên (-inf, -1) và (3, +inf)"
                      : "Nhập công thức toán học..."
                  }
                />
              </div>

              {/* Live Preview */}
              {newContentLatex.trim() && (
                <div className={styles.previewBox}>
                  <span className={styles.previewLabel}>Xem trước:</span>
                  <code>{newContentLatex}</code>
                </div>
              )}

              {/* Explanation Input */}
              <div className={styles.formGroup}>
                <label htmlFor="explanation-input" className={styles.formLabel}>
                  Lời giải thích / Lý lẽ sư phạm (tùy chọn):
                </label>
                <textarea
                  id="explanation-input"
                  className={styles.formTextarea}
                  rows={2}
                  value={newExplanation}
                  onChange={(e) => setNewExplanation(e.target.value)}
                  placeholder="Giải thích cách làm, áp dụng công thức nào..."
                />
              </div>

              <div className={styles.addStepActions}>
                <button
                  type="submit"
                  className={styles.saveStepBtn}
                  disabled={
                    isSavingStep ||
                    (newStepType !== "SIGN_TABLE" &&
                      !newContentLatex.trim() &&
                      !newExplanation.trim())
                  }
                >
                  {isSavingStep ? (
                    <Loader2 className={styles.spinIcon} size={16} />
                  ) : (
                    <ArrowRight size={16} />
                  )}
                  Lưu bước giải
                </button>
              </div>
            </form>
          )}

          {/* Steps List */}
          {activeSteps.length === 0 && !isAddingStep && (
            <div className={styles.emptyStepsNotice}>
              <HelpCircle size={32} className={styles.emptyIcon} />
              <p>Chưa có bước giải nào được thêm.</p>
              <button
                type="button"
                className={styles.addStepTriggerBtn}
                onClick={() => setIsAddingStep(true)}
              >
                <Plus size={16} />
                Thêm bước giải đầu tiên
              </button>
            </div>
          )}

          <div className={styles.stepsList}>
            {activeSteps.map((step) => (
              <StepCard
                key={step.id}
                step={step}
                totalSteps={activeSteps.length}
                onMoveUp={(id) => handleReorderStep(id, "up")}
                onMoveDown={(id) => handleReorderStep(id, "down")}
                onDelete={handleDeleteStep}
                onViewRevisions={setSelectedStepForRevision}
                isReadOnly={isReadOnly}
              />
            ))}
          </div>
        </section>
      </main>

      {/* Revision History Modal */}
      <RevisionViewerModal
        isOpen={selectedStepForRevision !== null}
        onClose={() => setSelectedStepForRevision(null)}
        step={selectedStepForRevision}
        attemptId={attemptId}
        accessToken={accessToken}
        onRollback={handleRollbackStep}
        apiBaseUrl={apiBaseUrl}
      />
    </div>
  );
}
