"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SIGN_CYCLE = void 0;
exports.cycleSign = cycleSign;
exports.invertSigns = invertSigns;
exports.addCriticalPoint = addCriticalPoint;
exports.removeCriticalPoint = removeCriticalPoint;
exports.reorderStepsList = reorderStepsList;
exports.canSubmitAttempt = canSubmitAttempt;
exports.SIGN_CYCLE = ["+", "-", "0", "||"];
/**
 * Cycle a sign to the next symbol in ["+", "-", "0", "||"]
 */
function cycleSign(currentSign) {
    const idx = exports.SIGN_CYCLE.indexOf(currentSign);
    if (idx === -1)
        return "+";
    return exports.SIGN_CYCLE[(idx + 1) % exports.SIGN_CYCLE.length];
}
/**
 * Invert all signs: "+" <-> "-", keeping "0" and "||" unchanged
 */
function invertSigns(signs) {
    return signs.map((s) => (s === "+" ? "-" : s === "-" ? "+" : s));
}
/**
 * Add a critical point and ensure signs array length is always (points.length + 1)
 */
function addCriticalPoint(current, pointInput) {
    var _a, _b;
    const rawPoints = (_a = current.critical_points) !== null && _a !== void 0 ? _a : [];
    const rawSigns = (_b = current.signs) !== null && _b !== void 0 ? _b : (rawPoints.length > 0 ? Array(rawPoints.length + 1).fill("+") : ["+"]);
    let pointVal;
    if (typeof pointInput === "number") {
        pointVal = pointInput;
    }
    else {
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
function removeCriticalPoint(current, indexToRemove) {
    var _a, _b;
    const rawPoints = (_a = current.critical_points) !== null && _a !== void 0 ? _a : [];
    const rawSigns = (_b = current.signs) !== null && _b !== void 0 ? _b : ["+"];
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
function reorderStepsList(steps, stepId, direction) {
    const activeSteps = steps.filter((s) => !s.is_deleted);
    const currentIndex = activeSteps.findIndex((s) => s.id === stepId);
    if (currentIndex === -1)
        return null;
    const targetIndex = direction === "up" ? currentIndex - 1 : currentIndex + 1;
    if (targetIndex < 0 || targetIndex >= activeSteps.length)
        return null;
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
function canSubmitAttempt(steps, status) {
    if (status === "SUBMITTED" || status === "EVALUATED") {
        return { canSubmit: false, reason: "Bài giải đã được nộp hoặc đã chấm điểm." };
    }
    const active = (steps !== null && steps !== void 0 ? steps : []).filter((s) => !s.is_deleted);
    if (active.length === 0) {
        return { canSubmit: false, reason: "Cần ít nhất một bước giải để nộp bài." };
    }
    return { canSubmit: true };
}
