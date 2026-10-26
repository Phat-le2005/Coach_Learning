export type AIReviewUIState =
  | "IDLE"
  | "REQUESTING"
  | "READY"
  | "REVEALING"
  | "PAUSED"
  | "COMPLETED"
  | "ERROR";

export type AIReviewStepCardState =
  | "pending"
  | "active"
  | "revealed"
  | "expanded"
  | "collapsed";

export type AIReviewFilterMode = "ALL" | "NEEDS_FIX";

export type StepVerdict = "VALID" | "INVALID" | "NEEDS_REVIEW";

export interface StepGradeItem {
  step_index: number;
  verdict: StepVerdict;
  score: number | null;
  confidence: number;
  feedback: string;
}

export interface AIReviewControllerState {
  uiState: AIReviewUIState;
  totalSteps: number;
  revealedCount: number;
  activeStepIndex: number | null;
  expandedStepIndices: number[];
  filterMode: AIReviewFilterMode;
  reducedMotion: boolean;
  errorMessage: string | null;
}

export type AIReviewControllerAction =
  | { type: "START_REQUEST"; reducedMotion?: boolean }
  | {
      type: "RECEIVE_DATA";
      stepIndices: number[];
      reducedMotion?: boolean;
      instantComplete?: boolean;
    }
  | { type: "ADVANCE_STEP"; stepIndices: number[] }
  | { type: "PAUSE" }
  | { type: "RESUME"; stepIndices: number[] }
  | { type: "SKIP_TO_END"; stepIndices: number[] }
  | { type: "REPLAY"; stepIndices: number[]; reducedMotion?: boolean }
  | { type: "SELECT_STEP"; stepIndex: number }
  | { type: "TOGGLE_EXPAND_STEP"; stepIndex: number }
  | { type: "SET_FILTER"; filterMode: AIReviewFilterMode }
  | { type: "SET_ERROR"; message: string }
  | { type: "RESET" };

export function createInitialAIReviewState(
  reducedMotion = false,
): AIReviewControllerState {
  return {
    uiState: "IDLE",
    totalSteps: 0,
    revealedCount: 0,
    activeStepIndex: null,
    expandedStepIndices: [],
    filterMode: "ALL",
    reducedMotion,
    errorMessage: null,
  };
}

export function reduceAIReviewState(
  state: AIReviewControllerState,
  action: AIReviewControllerAction,
): AIReviewControllerState {
  switch (action.type) {
    case "START_REQUEST":
      return {
        ...state,
        uiState: "REQUESTING",
        totalSteps: 0,
        revealedCount: 0,
        activeStepIndex: null,
        expandedStepIndices: [],
        filterMode: "ALL",
        reducedMotion: action.reducedMotion ?? state.reducedMotion,
        errorMessage: null,
      };

    case "RECEIVE_DATA": {
      const reduced = action.reducedMotion ?? state.reducedMotion;
      const indices = action.stepIndices;
      const total = indices.length;

      if (total === 0) {
        return {
          ...state,
          uiState: "COMPLETED",
          totalSteps: 0,
          revealedCount: 0,
          activeStepIndex: null,
          expandedStepIndices: [],
          reducedMotion: reduced,
          errorMessage: null,
        };
      }

      if (reduced || action.instantComplete) {
        return {
          ...state,
          uiState: "COMPLETED",
          totalSteps: total,
          revealedCount: total,
          activeStepIndex: indices[0] ?? null,
          expandedStepIndices: [...indices],
          reducedMotion: reduced,
          errorMessage: null,
        };
      }

      const firstStep = indices[0]!;
      return {
        ...state,
        uiState: "REVEALING",
        totalSteps: total,
        revealedCount: 1,
        activeStepIndex: firstStep,
        expandedStepIndices: [firstStep],
        filterMode: "ALL",
        reducedMotion: reduced,
        errorMessage: null,
      };
    }

    case "ADVANCE_STEP": {
      if (state.uiState !== "REVEALING") {
        return state;
      }
      const indices = action.stepIndices;
      const total = indices.length;

      if (state.revealedCount < total) {
        const nextCount = state.revealedCount + 1;
        const nextStepIndex = indices[nextCount - 1]!;
        return {
          ...state,
          totalSteps: total,
          revealedCount: nextCount,
          activeStepIndex: nextStepIndex,
          // Collapse previous step into compact state and expand active step
          expandedStepIndices: [nextStepIndex],
        };
      }

      return {
        ...state,
        uiState: "COMPLETED",
        totalSteps: total,
        revealedCount: total,
        expandedStepIndices: [...indices],
      };
    }

    case "PAUSE":
      if (state.uiState !== "REVEALING") return state;
      return {
        ...state,
        uiState: "PAUSED",
      };

    case "RESUME":
      if (state.uiState !== "PAUSED") return state;
      if (state.revealedCount >= action.stepIndices.length && action.stepIndices.length > 0) {
        return {
          ...state,
          uiState: "COMPLETED",
          expandedStepIndices: [...action.stepIndices],
        };
      }
      return {
        ...state,
        uiState: "REVEALING",
      };

    case "SKIP_TO_END": {
      const indices = action.stepIndices;
      return {
        ...state,
        uiState: "COMPLETED",
        totalSteps: indices.length,
        revealedCount: indices.length,
        activeStepIndex:
          state.activeStepIndex ?? indices[indices.length - 1] ?? null,
        expandedStepIndices: [...indices],
      };
    }

    case "REPLAY": {
      const reduced = action.reducedMotion ?? state.reducedMotion;
      const indices = action.stepIndices;
      if (indices.length === 0) {
        return {
          ...state,
          uiState: "COMPLETED",
          totalSteps: 0,
          revealedCount: 0,
          activeStepIndex: null,
          expandedStepIndices: [],
          filterMode: "ALL",
        };
      }
      if (reduced) {
        return {
          ...state,
          uiState: "COMPLETED",
          totalSteps: indices.length,
          revealedCount: indices.length,
          activeStepIndex: indices[0] ?? null,
          expandedStepIndices: [...indices],
          filterMode: "ALL",
          reducedMotion: true,
        };
      }
      const firstStep = indices[0]!;
      return {
        ...state,
        uiState: "REVEALING",
        totalSteps: indices.length,
        revealedCount: 1,
        activeStepIndex: firstStep,
        expandedStepIndices: [firstStep],
        filterMode: "ALL",
        reducedMotion: false,
      };
    }

    case "SELECT_STEP": {
      const exists = state.expandedStepIndices.includes(action.stepIndex);
      return {
        ...state,
        activeStepIndex: action.stepIndex,
        expandedStepIndices: exists
          ? state.expandedStepIndices
          : [...state.expandedStepIndices, action.stepIndex],
      };
    }

    case "TOGGLE_EXPAND_STEP": {
      const exists = state.expandedStepIndices.includes(action.stepIndex);
      return {
        ...state,
        expandedStepIndices: exists
          ? state.expandedStepIndices.filter((idx) => idx !== action.stepIndex)
          : [...state.expandedStepIndices, action.stepIndex],
      };
    }

    case "SET_FILTER":
      return {
        ...state,
        filterMode: action.filterMode,
      };

    case "SET_ERROR":
      return {
        ...state,
        uiState: "ERROR",
        errorMessage: action.message,
      };

    case "RESET":
      return createInitialAIReviewState(state.reducedMotion);

    default:
      return state;
  }
}

export function getStepCardVisualState(
  state: AIReviewControllerState,
  stepOrderIndex: number,
  stepIndex: number,
): AIReviewStepCardState {
  if (stepOrderIndex >= state.revealedCount) {
    return "pending";
  }
  if (
    (state.uiState === "REVEALING" || state.uiState === "PAUSED") &&
    state.activeStepIndex === stepIndex &&
    stepOrderIndex === state.revealedCount - 1
  ) {
    return "active";
  }
  if (state.expandedStepIndices.includes(stepIndex)) {
    return "expanded";
  }
  return "collapsed";
}

export interface StepVerdictMeta {
  verdict: StepVerdict;
  label: string;
  badgeText: string;
  tone: "valid" | "invalid" | "needs_review";
  ariaLabel: string;
}

export function formatStepVerdictMeta(verdict: StepVerdict): StepVerdictMeta {
  switch (verdict) {
    case "VALID":
      return {
        verdict: "VALID",
        label: "Hợp lý",
        badgeText: "Bước hợp lý",
        tone: "valid",
        ariaLabel: "Đánh giá bước giải: Hợp lý",
      };
    case "INVALID":
      return {
        verdict: "INVALID",
        label: "Cần sửa",
        badgeText: "Cần chỉnh sửa",
        tone: "invalid",
        ariaLabel: "Đánh giá bước giải: Cần chỉnh sửa",
      };
    case "NEEDS_REVIEW":
    default:
      return {
        verdict: "NEEDS_REVIEW",
        label: "Cần xem lại",
        badgeText: "Cần xem lại",
        tone: "needs_review",
        ariaLabel: "Đánh giá bước giải: Cần xem lại",
      };
  }
}

/**
 * Formats a step score strictly from `score` (never `confidence`).
 * Returns `null` when `score` is null/undefined so the UI never renders a fake "0%".
 */
export function formatStepScoreDisplay(
  score: number | null | undefined,
): string | null {
  if (score === null || score === undefined || !Number.isFinite(score)) {
    return null;
  }
  if (score >= 0 && score <= 1) {
    return `${Math.round(score * 100)}%`;
  }
  return `${Math.round(score)}`;
}

const SPECIFIC_STEP_KIND_LABELS: Record<string, string> = {
  ASSUMPTION: "Tập xác định & Giả thiết",
  DERIVATIVE_CALCULATION: "Tính đạo hàm",
  ROOT_FINDING: "Tìm nghiệm",
  SIGN_TABLE: "Bảng xét dấu",
  VARIATION_TABLE: "Bảng biến thiên",
  CONCLUSION: "Kết luận",
};

/**
 * Returns an authentic pedagogical title if the step has a specific type,
 * or `null` if generic (`EXPLANATION`, `CUSTOM`, or undefined) so the UI
 * displays `"Bước N"` without inventing a fake title.
 */
export function formatAuthenticStepTitle(
  stepType?: string | null,
  hasVariationTable?: boolean,
): string | null {
  if (hasVariationTable) {
    return "Bảng biến thiên";
  }
  if (!stepType) {
    return null;
  }
  return SPECIFIC_STEP_KIND_LABELS[stepType] ?? null;
}

export interface AIReviewSummaryStats {
  totalSteps: number;
  validCount: number;
  invalidCount: number;
  needsReviewCount: number;
  issueStepIndices: number[];
  needsTeacherReview: boolean;
  isFinal: false;
  disclaimer: string;
  teacherReviewNotice: string | null;
}

export const AI_REVIEW_DISCLAIMER =
  "Kết quả nhận xét AI mang tính tham khảo, chưa phải điểm chính thức.";

export const AI_TEACHER_REVIEW_NOTICE =
  "Bài làm có bước cần giáo viên kiểm tra và đánh giá thêm.";

export function computeAIReviewSummaryStats(
  stepGrades: ReadonlyArray<StepGradeItem>,
  needsTeacherReview: boolean,
): AIReviewSummaryStats {
  let validCount = 0;
  let invalidCount = 0;
  let needsReviewCount = 0;
  const issueStepIndices: number[] = [];

  for (const grade of stepGrades) {
    if (grade.verdict === "VALID") {
      validCount += 1;
    } else if (grade.verdict === "INVALID") {
      invalidCount += 1;
      issueStepIndices.push(grade.step_index);
    } else {
      needsReviewCount += 1;
      issueStepIndices.push(grade.step_index);
    }
  }

  return {
    totalSteps: stepGrades.length,
    validCount,
    invalidCount,
    needsReviewCount,
    issueStepIndices,
    needsTeacherReview,
    isFinal: false,
    disclaimer: AI_REVIEW_DISCLAIMER,
    teacherReviewNotice: needsTeacherReview ? AI_TEACHER_REVIEW_NOTICE : null,
  };
}
