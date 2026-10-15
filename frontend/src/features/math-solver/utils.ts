import type { SignTablePayload, SolutionStepItem } from "./types";

export const SIGN_CYCLE = ["+", "-", "0", "||"] as const;
export type SignSymbol = (typeof SIGN_CYCLE)[number];

/**
 * Cycle a sign to the next symbol in ["+", "-", "0", "||"]
 */
export function cycleSign(currentSign: string): string {
  const idx = SIGN_CYCLE.indexOf(currentSign as SignSymbol);
  if (idx === -1) return "+";
  return SIGN_CYCLE[(idx + 1) % SIGN_CYCLE.length];
}

/**
 * Invert all signs: "+" <-> "-", keeping "0" and "||" unchanged
 */
export function invertSigns(signs: string[]): string[] {
  return signs.map((s) => (s === "+" ? "-" : s === "-" ? "+" : s));
}

/**
 * Add a critical point and ensure signs array length is always (points.length + 1)
 */
export function addCriticalPoint(
  current: SignTablePayload,
  pointInput: string | number,
): SignTablePayload {
  const rawPoints = current.critical_points ?? [];
  const rawSigns = current.signs ?? (rawPoints.length > 0 ? Array(rawPoints.length + 1).fill("+") : ["+"]);

  let pointVal: number | string;
  if (typeof pointInput === "number") {
    pointVal = pointInput;
  } else {
    const trimmed = pointInput.trim();
    const num = Number(trimmed);
    pointVal = isNaN(num) || trimmed === "" ? trimmed : num;
  }

  const updatedPoints = [...rawPoints, pointVal];
  const updatedSigns = [...rawSigns];
  while (updatedSigns.length < updatedPoints.length + 1) {
    updatedSigns.push("+");
  }

  return {
    critical_points: updatedPoints,
    signs: updatedSigns.slice(0, updatedPoints.length + 1),
  };
}

/**
 * Remove a critical point by index and keep signs array length = points.length + 1
 */
export function removeCriticalPoint(
  current: SignTablePayload,
  indexToRemove: number,
): SignTablePayload {
  const rawPoints = current.critical_points ?? [];
  const rawSigns = current.signs ?? ["+"];

  const updatedPoints = rawPoints.filter((_, i) => i !== indexToRemove);
  const updatedSigns = rawSigns.filter((_, i) => i !== indexToRemove);

  while (updatedSigns.length < updatedPoints.length + 1) {
    updatedSigns.push("+");
  }

  return {
    critical_points: updatedPoints,
    signs: updatedSigns.slice(0, Math.max(1, updatedPoints.length + 1)),
  };
}

/**
 * Reorder steps by moving a step up or down
 */
export function reorderStepsList<T extends { id: string; is_deleted?: boolean }>(
  steps: T[],
  stepId: string,
  direction: "up" | "down",
): { reorderedSteps: T[]; stepIds: string[] } | null {
  const activeSteps = steps.filter((s) => !s.is_deleted);
  const currentIndex = activeSteps.findIndex((s) => s.id === stepId);
  if (currentIndex === -1) return null;

  const targetIndex = direction === "up" ? currentIndex - 1 : currentIndex + 1;
  if (targetIndex < 0 || targetIndex >= activeSteps.length) return null;

  const reordered = [...activeSteps];
  const temp = reordered[currentIndex];
  reordered[currentIndex] = reordered[targetIndex];
  reordered[targetIndex] = temp;

  return {
    reorderedSteps: reordered,
    stepIds: reordered.map((s) => s.id),
  };
}

/**
 * Validate that an attempt is eligible for submission
 */
export function canSubmitAttempt(
  steps: SolutionStepItem[] | undefined,
  status: string,
): { canSubmit: boolean; reason?: string } {
  if (status === "SUBMITTED" || status === "EVALUATED") {
    return { canSubmit: false, reason: "Bài giải đã được nộp hoặc đã chấm điểm." };
  }
  const active = (steps ?? []).filter((s) => !s.is_deleted);
  if (active.length === 0) {
    return { canSubmit: false, reason: "Cần ít nhất một bước giải để nộp bài." };
  }
  return { canSubmit: true };
}
