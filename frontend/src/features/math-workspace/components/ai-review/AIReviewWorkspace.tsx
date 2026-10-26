"use client";

import React, {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useState,
} from "react";
import {
  AlertCircle,
  RotateCcw,
  Sparkles,
  PenTool,
  SkipForward,
} from "lucide-react";
import type { ApiClient } from "@/lib/api/client";
import type { AIReviewRead } from "@/lib/api/contracts";
import type { InkStroke, ProblemRead, SolutionAttemptRead } from "../../types";
import {
  computeAIReviewSummaryStats,
  createInitialAIReviewState,
  getStepCardVisualState,
  reduceAIReviewState,
  type AIReviewFilterMode,
} from "../../utils/ai-review-controller";
import { AIReviewHeader } from "./AIReviewHeader";
import { AIReviewLoading } from "./AIReviewLoading";
import { AIReviewControls } from "./AIReviewControls";
import { AIReviewStepIndicator } from "./AIReviewStepIndicator";
import { AIReviewStepCard } from "./AIReviewStepCard";
import { AIReviewSummary } from "./AIReviewSummary";
import { AIReviewPaperViewer } from "./AIReviewPaperViewer";
import styles from "./AIReview.module.css";

interface AIReviewWorkspaceProps {
  attemptId: string;
  accessToken: string;
  apiClient: ApiClient;
  problem: ProblemRead | null;
  attempt: SolutionAttemptRead | null;
  aiReview: AIReviewRead | null;
  isRequesting: boolean;
  errorMessage: string | null;
  pages: Record<number, InkStroke[]>;
  currentPageIndex: number;
  instantOpen?: boolean;
  onRetryReview: () => void;
  onClose: () => void;
}

const SCAN_CEREMONY_DURATION_MS = 2350;
const STEP_REVEAL_INTERVAL_MS = 1500;

export function AIReviewWorkspace({
  attemptId,
  accessToken,
  apiClient,
  problem,
  attempt,
  aiReview,
  isRequesting,
  errorMessage,
  pages,
  currentPageIndex,
  instantOpen = false,
  onRetryReview,
  onClose,
}: AIReviewWorkspaceProps) {
  const [mobileTab, setMobileTab] = useState<"timeline" | "paper">("timeline");
  // Always play Phase A scan ceremony for 2.35s when opening (unless instantOpen is requested)
  const [isCeremonyScanning, setIsCeremonyScanning] = useState<boolean>(
    !instantOpen && !errorMessage,
  );
  const [ceremonyNonce, setCeremonyNonce] = useState(0);

  const [controllerState, dispatch] = useReducer(
    reduceAIReviewState,
    false,
    createInitialAIReviewState,
  );

  const stepGrades = useMemo(() => aiReview?.step_grades ?? [], [aiReview]);
  const stepIndices = useMemo(
    () => stepGrades.map((g) => g.step_index),
    [stepGrades],
  );

  const sortedSteps = useMemo(
    () =>
      [...(attempt?.steps ?? [])].sort((a, b) => a.step_index - b.step_index),
    [attempt?.steps],
  );

  const stepLookup = useMemo(() => {
    const map = new Map(sortedSteps.map((step) => [step.step_index, step]));
    return map;
  }, [sortedSteps]);

  // Phase A Scan Ceremony Timer
  useEffect(() => {
    if (!isCeremonyScanning) return;
    const timer = window.setTimeout(() => {
      setIsCeremonyScanning(false);
    }, SCAN_CEREMONY_DURATION_MS);
    return () => window.clearTimeout(timer);
  }, [isCeremonyScanning, ceremonyNonce]);

  // Synchronize external request / data / scan ceremony into state machine
  useEffect(() => {
    if (errorMessage) {
      setIsCeremonyScanning(false);
      dispatch({ type: "SET_ERROR", message: errorMessage });
      return;
    }

    if (isRequesting || isCeremonyScanning) {
      if (controllerState.uiState !== "REQUESTING") {
        dispatch({ type: "START_REQUEST", reducedMotion: false });
      }
      return;
    }

    if (aiReview && aiReview.attempt_id === attemptId) {
      if (
        controllerState.uiState === "IDLE" ||
        controllerState.uiState === "REQUESTING" ||
        controllerState.uiState === "READY"
      ) {
        const indices = aiReview.step_grades.map((g) => g.step_index);
        dispatch({
          type: "RECEIVE_DATA",
          stepIndices: indices,
          reducedMotion: false,
          instantComplete: instantOpen,
        });
      }
    }
  }, [
    aiReview,
    attemptId,
    controllerState.uiState,
    errorMessage,
    instantOpen,
    isCeremonyScanning,
    isRequesting,
  ]);

  // Sequential reveal timer during REVEALING phase
  useEffect(() => {
    if (controllerState.uiState !== "REVEALING") return;
    const timer = window.setTimeout(() => {
      dispatch({ type: "ADVANCE_STEP", stepIndices });
    }, STEP_REVEAL_INTERVAL_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [controllerState.uiState, controllerState.revealedCount, stepIndices]);

  const handleSkipAll = useCallback(() => {
    setIsCeremonyScanning(false);
    if (stepIndices.length > 0) {
      dispatch({ type: "SKIP_TO_END", stepIndices });
    }
  }, [stepIndices]);

  const handleFullReplay = useCallback(() => {
    dispatch({ type: "START_REQUEST", reducedMotion: false });
    setIsCeremonyScanning(true);
    setCeremonyNonce((n) => n + 1);
  }, []);

  const revealedStepIndices = useMemo(
    () => stepIndices.slice(0, controllerState.revealedCount),
    [stepIndices, controllerState.revealedCount],
  );

  const activePos =
    controllerState.activeStepIndex !== null
      ? revealedStepIndices.indexOf(controllerState.activeStepIndex)
      : -1;
  const canGoPrev = activePos > 0;
  const canGoNext =
    activePos >= 0 && activePos < revealedStepIndices.length - 1;

  const handlePrevStep = useCallback(() => {
    if (!canGoPrev) return;
    const prevIdx = revealedStepIndices[activePos - 1];
    if (prevIdx !== undefined) {
      dispatch({ type: "SELECT_STEP", stepIndex: prevIdx });
    }
  }, [activePos, canGoPrev, revealedStepIndices]);

  const handleNextStep = useCallback(() => {
    if (!canGoNext) return;
    const nextIdx = revealedStepIndices[activePos + 1];
    if (nextIdx !== undefined) {
      dispatch({ type: "SELECT_STEP", stepIndex: nextIdx });
    }
  }, [activePos, canGoNext, revealedStepIndices]);

  // Keyboard shortcuts
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
        if (
          document.activeElement?.tagName !== "INPUT" &&
          document.activeElement?.tagName !== "TEXTAREA" &&
          document.activeElement?.tagName !== "SELECT"
        ) {
          handlePrevStep();
        }
      } else if (event.key === "ArrowRight" || event.key === "ArrowDown") {
        if (
          document.activeElement?.tagName !== "INPUT" &&
          document.activeElement?.tagName !== "TEXTAREA" &&
          document.activeElement?.tagName !== "SELECT"
        ) {
          handleNextStep();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleNextStep, handlePrevStep, onClose]);

  const summaryStats = useMemo(
    () =>
      computeAIReviewSummaryStats(
        stepGrades,
        Boolean(aiReview?.needs_teacher_review),
      ),
    [aiReview?.needs_teacher_review, stepGrades],
  );

  const visibleStepGrades = useMemo(() => {
    if (
      controllerState.uiState === "COMPLETED" &&
      controllerState.filterMode === "NEEDS_FIX"
    ) {
      return stepGrades.filter((g) => g.verdict !== "VALID");
    }
    return stepGrades;
  }, [controllerState.filterMode, controllerState.uiState, stepGrades]);

  const activeStep =
    controllerState.activeStepIndex !== null
      ? stepLookup.get(controllerState.activeStepIndex)
      : undefined;

  const isScanningPhase =
    isRequesting ||
    isCeremonyScanning ||
    controllerState.uiState === "REQUESTING" ||
    controllerState.uiState === "READY";

  const effectiveHeaderState = isScanningPhase
    ? "REQUESTING"
    : controllerState.uiState;

  const liveAnnouncement = useMemo(() => {
    if (isScanningPhase) {
      return "Gemini đang quét và đối chiếu lời giải với đáp án tham chiếu.";
    }
    if (controllerState.uiState === "COMPLETED") {
      return `Đã hoàn tất đối chiếu ${summaryStats.totalSteps} bước giải: ${summaryStats.validCount} bước hợp lý, ${summaryStats.invalidCount} bước cần sửa.`;
    }
    if (controllerState.uiState === "ERROR") {
      return (
        controllerState.errorMessage ?? "Không thể hoàn tất nhận xét AI."
      );
    }
    return "";
  }, [
    controllerState.errorMessage,
    controllerState.uiState,
    isScanningPhase,
    summaryStats.invalidCount,
    summaryStats.totalSteps,
    summaryStats.validCount,
  ]);

  const confirmedCount = attempt?.steps?.length ?? stepGrades.length;

  return (
    <section
      className={styles.reviewWorkspaceOverlay}
      role="dialog"
      aria-modal="true"
      aria-label="Không gian đối chiếu lời giải từng bước cùng AI"
    >
      <div className={styles.srOnly} aria-live="polite" aria-atomic="true">
        {liveAnnouncement}
      </div>

      <AIReviewHeader
        uiState={effectiveHeaderState}
        confirmedStepCount={confirmedCount}
        problem={problem}
        onClose={onClose}
      />

      <div className={styles.mobileSegmentedBar} role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={mobileTab === "timeline"}
          onClick={() => setMobileTab("timeline")}
          className={`${styles.mobileSegmentBtn} ${
            mobileTab === "timeline" ? styles.mobileSegmentBtnActive : ""
          }`}
        >
          <Sparkles size={14} />
          <span>Nhận xét AI ({confirmedCount})</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mobileTab === "paper"}
          onClick={() => setMobileTab("paper")}
          className={`${styles.mobileSegmentBtn} ${
            mobileTab === "paper" ? styles.mobileSegmentBtnActive : ""
          }`}
        >
          <PenTool size={14} />
          <span>Bài viết gốc</span>
        </button>
      </div>

      <div className={styles.splitBody}>
        {/* Left Column: AI Review Timeline */}
        <div
          className={`${styles.timelineColumn} ${
            mobileTab !== "timeline" ? styles.timelineColumnHiddenMobile : ""
          }`}
        >
          {!isScanningPhase &&
            (controllerState.uiState === "REVEALING" ||
              controllerState.uiState === "PAUSED" ||
              controllerState.uiState === "COMPLETED") &&
            stepGrades.length > 0 && (
              <div className={styles.timelineControlsWrap}>
                <AIReviewControls
                  uiState={controllerState.uiState}
                  revealedCount={controllerState.revealedCount}
                  totalSteps={stepGrades.length}
                  canGoPrev={canGoPrev}
                  canGoNext={canGoNext}
                  onPause={() => dispatch({ type: "PAUSE" })}
                  onResume={() => dispatch({ type: "RESUME", stepIndices })}
                  onSkipToEnd={handleSkipAll}
                  onReplay={handleFullReplay}
                  onPrevStep={handlePrevStep}
                  onNextStep={handleNextStep}
                />
                <AIReviewStepIndicator
                  stepGrades={stepGrades}
                  revealedCount={controllerState.revealedCount}
                  activeStepIndex={controllerState.activeStepIndex}
                  onSelectStep={(idx) =>
                    dispatch({ type: "SELECT_STEP", stepIndex: idx })
                  }
                />
              </div>
            )}

          <div className={styles.timelineScrollArea}>
            {isScanningPhase && (
              <>
                <AIReviewLoading
                  key={ceremonyNonce}
                  stepCount={confirmedCount}
                  steps={sortedSteps}
                />
                {aiReview && !isRequesting && (
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "center",
                      marginTop: "0.25rem",
                    }}
                  >
                    <button
                      type="button"
                      onClick={handleSkipAll}
                      className={styles.controlIconBtn}
                    >
                      <SkipForward size={13} />
                      <span>Bỏ qua hiệu ứng quét (Xem ngay kết quả)</span>
                    </button>
                  </div>
                )}
              </>
            )}

            {!isScanningPhase && controllerState.uiState === "ERROR" && (
              <div className={styles.errorCard} role="alert">
                <h3 className={styles.errorTitle}>
                  <AlertCircle size={18} />
                  <span>Chưa nhận được kết quả chấm từ AI</span>
                </h3>
                <p className={styles.errorMessage}>
                  {controllerState.errorMessage ||
                    "Không thể nhận kết quả chấm từ AI lúc này. Các bước giải của bạn vẫn được giữ nguyên."}
                </p>
                <div className={styles.errorActionRow}>
                  <button
                    type="button"
                    onClick={onRetryReview}
                    className={styles.summaryPrimaryBtn}
                  >
                    <RotateCcw size={14} />
                    <span>Thử lại</span>
                  </button>
                  <button
                    type="button"
                    onClick={onClose}
                    className={styles.summarySecondaryBtn}
                  >
                    <span>Đóng chế độ nhận xét</span>
                  </button>
                </div>
              </div>
            )}

            {!isScanningPhase &&
              (controllerState.uiState === "REVEALING" ||
                controllerState.uiState === "PAUSED" ||
                controllerState.uiState === "COMPLETED") && (
                <>
                  <div className={styles.stepListContainer}>
                    {visibleStepGrades.map((grade) => {
                      const orderIdx = stepIndices.indexOf(grade.step_index);
                      const cardState = getStepCardVisualState(
                        controllerState,
                        orderIdx,
                        grade.step_index,
                      );
                      const stepData = stepLookup.get(grade.step_index);

                      return (
                        <AIReviewStepCard
                          key={`${ceremonyNonce}-${grade.step_index}`}
                          grade={grade}
                          step={stepData}
                          cardState={cardState}
                          isSelected={
                            controllerState.activeStepIndex === grade.step_index
                          }
                          onSelectStep={(idx) =>
                            dispatch({ type: "SELECT_STEP", stepIndex: idx })
                          }
                          onToggleExpand={(idx) =>
                            dispatch({
                              type: "TOGGLE_EXPAND_STEP",
                              stepIndex: idx,
                            })
                          }
                          onInspectOnPaper={(idx) => {
                            dispatch({ type: "SELECT_STEP", stepIndex: idx });
                            setMobileTab("paper");
                          }}
                        />
                      );
                    })}
                  </div>

                  {controllerState.uiState === "COMPLETED" && (
                    <AIReviewSummary
                      stats={summaryStats}
                      filterMode={controllerState.filterMode}
                      onSetFilter={(mode: AIReviewFilterMode) =>
                        dispatch({ type: "SET_FILTER", filterMode: mode })
                      }
                      onJumpToStep={(idx) =>
                        dispatch({ type: "SELECT_STEP", stepIndex: idx })
                      }
                      onReplay={handleFullReplay}
                      onClose={onClose}
                    />
                  )}
                </>
              )}
          </div>
        </div>

        {/* Right Column: Student Solution Viewer */}
        <div
          className={`${
            mobileTab !== "paper" ? styles.viewerColumnHiddenMobile : ""
          }`}
          style={{ display: "flex", flexDirection: "column", minHeight: 0 }}
        >
          <AIReviewPaperViewer
            attemptId={attemptId}
            accessToken={accessToken}
            apiClient={apiClient}
            pages={pages}
            initialPageIndex={currentPageIndex}
            activeStep={activeStep}
            activeStepIndex={controllerState.activeStepIndex}
            isScanning={isScanningPhase}
            isRevealing={controllerState.uiState === "REVEALING"}
          />
        </div>
      </div>
    </section>
  );
}
