import type { ProblemRead, SolutionAttemptRead } from "@/lib/api/contracts";

export function getSolutionSubmissionState(
  problem: Pick<ProblemRead, "is_read_only"> | null,
  attempt: { status: SolutionAttemptRead["status"]; steps?: readonly unknown[] } | null,
  needsSourceReview: boolean,
) {
  const canEdit = Boolean(problem && attempt && !problem.is_read_only
    && (attempt.status === "DRAFT" || attempt.status === "IN_PROGRESS"));
  const showSubmitButton = canEdit && !needsSourceReview;
  return {
    canEdit,
    showSubmitButton,
    canSubmit: showSubmitButton && Boolean(attempt?.steps?.length),
    submitted: attempt?.status === "SUBMITTED",
  };
}
