import assert from "node:assert/strict";
import test from "node:test";

import {
  AI_REVIEW_DISCLAIMER,
  AI_TEACHER_REVIEW_NOTICE,
  computeAIReviewSummaryStats,
  createInitialAIReviewState,
  formatAuthenticStepTitle,
  formatStepScoreDisplay,
  formatStepVerdictMeta,
  getStepCardVisualState,
  reduceAIReviewState,
  type StepGradeItem,
} from "../src/features/math-workspace/utils/ai-review-controller.js";

test("AI review state machine transitions through REQUESTING -> REVEALING -> PAUSED -> COMPLETED for 3+ steps", () => {
  let state = createInitialAIReviewState(false);
  assert.equal(state.uiState, "IDLE");

  state = reduceAIReviewState(state, { type: "START_REQUEST" });
  assert.equal(state.uiState, "REQUESTING");
  assert.equal(state.revealedCount, 0);

  const stepIndices = [1, 2, 3];
  state = reduceAIReviewState(state, {
    type: "RECEIVE_DATA",
    stepIndices,
    reducedMotion: false,
  });

  // First step is active and revealed immediately upon receiving data
  assert.equal(state.uiState, "REVEALING");
  assert.equal(state.totalSteps, 3);
  assert.equal(state.revealedCount, 1);
  assert.equal(state.activeStepIndex, 1);
  assert.deepEqual(state.expandedStepIndices, [1]);
  assert.equal(getStepCardVisualState(state, 0, 1), "active");
  assert.equal(getStepCardVisualState(state, 1, 2), "pending");
  assert.equal(getStepCardVisualState(state, 2, 3), "pending");

  // Advance to step 2 -> step 1 collapses, step 2 becomes active
  state = reduceAIReviewState(state, { type: "ADVANCE_STEP", stepIndices });
  assert.equal(state.uiState, "REVEALING");
  assert.equal(state.revealedCount, 2);
  assert.equal(state.activeStepIndex, 2);
  assert.equal(getStepCardVisualState(state, 0, 1), "collapsed");
  assert.equal(getStepCardVisualState(state, 1, 2), "active");
  assert.equal(getStepCardVisualState(state, 2, 3), "pending");

  // Pause and resume during reveal
  state = reduceAIReviewState(state, { type: "PAUSE" });
  assert.equal(state.uiState, "PAUSED");
  // Advancing while paused is a no-op
  const pausedSnapshot = reduceAIReviewState(state, {
    type: "ADVANCE_STEP",
    stepIndices,
  });
  assert.equal(pausedSnapshot.revealedCount, 2);

  state = reduceAIReviewState(state, { type: "RESUME", stepIndices });
  assert.equal(state.uiState, "REVEALING");

  // Advance to step 3
  state = reduceAIReviewState(state, { type: "ADVANCE_STEP", stepIndices });
  assert.equal(state.revealedCount, 3);
  assert.equal(state.activeStepIndex, 3);
  assert.equal(getStepCardVisualState(state, 1, 2), "collapsed");
  assert.equal(getStepCardVisualState(state, 2, 3), "active");

  // Next tick after all steps revealed transitions to COMPLETED
  state = reduceAIReviewState(state, { type: "ADVANCE_STEP", stepIndices });
  assert.equal(state.uiState, "COMPLETED");
  assert.equal(state.revealedCount, 3);
  assert.deepEqual(state.expandedStepIndices, [1, 2, 3]);
});

test("single-step attempt reveals step 1 and completes cleanly", () => {
  let state = createInitialAIReviewState(false);
  state = reduceAIReviewState(state, {
    type: "RECEIVE_DATA",
    stepIndices: [1],
  });
  assert.equal(state.uiState, "REVEALING");
  assert.equal(state.revealedCount, 1);

  state = reduceAIReviewState(state, {
    type: "ADVANCE_STEP",
    stepIndices: [1],
  });
  assert.equal(state.uiState, "COMPLETED");
  assert.equal(state.revealedCount, 1);
});

test("skipToEnd and replay work locally without requiring new API requests", () => {
  const stepIndices = [1, 2, 3, 4];
  let state = createInitialAIReviewState(false);
  state = reduceAIReviewState(state, {
    type: "RECEIVE_DATA",
    stepIndices,
  });
  assert.equal(state.revealedCount, 1);

  state = reduceAIReviewState(state, {
    type: "SKIP_TO_END",
    stepIndices,
  });
  assert.equal(state.uiState, "COMPLETED");
  assert.equal(state.revealedCount, 4);

  // Replay restarts from step 1
  state = reduceAIReviewState(state, {
    type: "REPLAY",
    stepIndices,
    reducedMotion: false,
  });
  assert.equal(state.uiState, "REVEALING");
  assert.equal(state.revealedCount, 1);
  assert.equal(state.activeStepIndex, 1);
});

test("prefers-reduced-motion skips sequential timers and reveals all steps immediately", () => {
  let state = createInitialAIReviewState(true);
  state = reduceAIReviewState(state, {
    type: "RECEIVE_DATA",
    stepIndices: [1, 2, 3],
    reducedMotion: true,
  });
  assert.equal(state.uiState, "COMPLETED");
  assert.equal(state.revealedCount, 3);
  assert.deepEqual(state.expandedStepIndices, [1, 2, 3]);
});

test("score formatting never shows 0% when score is null and never uses confidence", () => {
  assert.equal(formatStepScoreDisplay(null), null);
  assert.equal(formatStepScoreDisplay(undefined), null);
  assert.equal(formatStepScoreDisplay(Number.NaN), null);
  assert.equal(formatStepScoreDisplay(0.85), "85%");
  assert.equal(formatStepScoreDisplay(1), "100%");
  assert.equal(formatStepScoreDisplay(0), "0%");
});

test("verdict metadata preserves pedagogical distinction between VALID, INVALID, and NEEDS_REVIEW", () => {
  const valid = formatStepVerdictMeta("VALID");
  const invalid = formatStepVerdictMeta("INVALID");
  const review = formatStepVerdictMeta("NEEDS_REVIEW");

  assert.equal(valid.label, "Hợp lý");
  assert.equal(invalid.label, "Cần sửa");
  assert.equal(review.label, "Cần xem lại");
  assert.notEqual(review.label, "Sai");
});

test("authentic step title avoids inventing fake titles for generic EXPLANATION or CUSTOM steps", () => {
  assert.equal(formatAuthenticStepTitle("EXPLANATION", false), null);
  assert.equal(formatAuthenticStepTitle("CUSTOM", false), null);
  assert.equal(formatAuthenticStepTitle(undefined, false), null);
  assert.equal(
    formatAuthenticStepTitle("DERIVATIVE_CALCULATION", false),
    "Tính đạo hàm",
  );
  assert.equal(
    formatAuthenticStepTitle("EXPLANATION", true),
    "Bảng biến thiên",
  );
});

test("summary stats aggregate verdicts accurately and include mandatory non-final disclaimer", () => {
  const grades: StepGradeItem[] = [
    {
      step_index: 1,
      verdict: "VALID",
      score: 1,
      confidence: 0.96,
      feedback: "Bước đạo hàm đúng.",
    },
    {
      step_index: 2,
      verdict: "INVALID",
      score: null,
      confidence: 0.91,
      feedback: "Chuyển vế đổi dấu bị nhầm.",
    },
    {
      step_index: 3,
      verdict: "NEEDS_REVIEW",
      score: null,
      confidence: 0.62,
      feedback: "Cần trình bày rõ thêm điều kiện nghiệm.",
    },
  ];

  const stats = computeAIReviewSummaryStats(grades, true);
  assert.equal(stats.totalSteps, 3);
  assert.equal(stats.validCount, 1);
  assert.equal(stats.invalidCount, 1);
  assert.equal(stats.needsReviewCount, 1);
  assert.deepEqual(stats.issueStepIndices, [2, 3]);
  assert.equal(stats.isFinal, false);
  assert.equal(stats.disclaimer, AI_REVIEW_DISCLAIMER);
  assert.equal(stats.teacherReviewNotice, AI_TEACHER_REVIEW_NOTICE);
});
