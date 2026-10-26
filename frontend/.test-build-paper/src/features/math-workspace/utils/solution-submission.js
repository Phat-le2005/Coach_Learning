"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getSolutionSubmissionState = getSolutionSubmissionState;
function getSolutionSubmissionState(problem, attempt, needsSourceReview) {
    var _a;
    const canEdit = Boolean(problem && attempt && !problem.is_read_only
        && (attempt.status === "DRAFT" || attempt.status === "IN_PROGRESS"));
    const showSubmitButton = canEdit && !needsSourceReview;
    return {
        canEdit,
        showSubmitButton,
        canSubmit: showSubmitButton && Boolean((_a = attempt === null || attempt === void 0 ? void 0 : attempt.steps) === null || _a === void 0 ? void 0 : _a.length),
        submitted: (attempt === null || attempt === void 0 ? void 0 : attempt.status) === "SUBMITTED",
    };
}
