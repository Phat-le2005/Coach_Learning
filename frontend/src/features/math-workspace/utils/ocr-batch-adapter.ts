import type { ApiClient } from "@/lib/api/client";
import type { SolutionAttemptRead, StepMutationRequest } from "@/lib/api/contracts";
import { toConfirmedLatex } from "./ocr-correction";
import type { OcrReviewDraft } from "./ocr-review-draft";
import type { ApprovedStepIntent, BatchApi, BatchJournal } from "./batch-manager";

export function createBatchApi(apiClient: ApiClient, accessToken = ""): BatchApi {
  return {
    getAttempt: (attemptId: string): Promise<SolutionAttemptRead> =>
      apiClient.getMathAttempt(accessToken, attemptId),
    addStep: (attemptId: string, request: StepMutationRequest): Promise<SolutionAttemptRead> =>
      apiClient.createMathStep(accessToken, attemptId, request),
  };
}

/** A paused batch owns its frozen and queued intents; review mutations must wait for recovery. */
export function canMutateReviewState(saving: boolean, batchSaving: boolean, pausedJournal: BatchJournal | null): boolean {
  return !saving && !batchSaving && pausedJournal === null;
}

export interface ReviewRowLike {
  draft: OcrReviewDraft;
  actionId: string;
  status: string;
  serverStepId?: string | null;
  error?: string | null;
}

export function buildApprovedIntents(rows: readonly ReviewRowLike[]): ApprovedStepIntent[] {
  // A row is truly approved ONLY if BOTH row.status === "approved"
  // AND its draft model is definitively approved (r.draft.reviewStatus === "APPROVED")!
  const approvedRows = rows.filter(
    (r) => r.status === "approved" && r.draft.reviewStatus === "APPROVED",
  );
  return approvedRows.map((r) => {
    const raw = r.draft.contentLatex.trim();
    const confirmedLatex = raw ? toConfirmedLatex(raw) : null;
    const explanation = r.draft.explanationText.trim() || null;
    return {
      draftId: r.draft.localId,
      actionId: r.actionId,
      approved: true as const,
      stepType: r.draft.selectedStepKind!,
      contentLatex: confirmedLatex,
      explanationText: explanation,
    };
  });
}

export function canStartBatchReview(rows: readonly ReviewRowLike[]): { canStart: boolean; reason?: string } {
  // A row is approved only when its draft model is strictly APPROVED and UI status is approved
  const isRowApproved = (r: ReviewRowLike) =>
    r.status === "approved" && r.draft.reviewStatus === "APPROVED";

  const pendingToSave = rows.filter(isRowApproved);
  if (pendingToSave.length === 0) {
    return { canStart: false, reason: "Chưa có bước nào được duyệt để lưu." };
  }

  // Find the index of the last approved row that is to be saved
  let lastApprovedIndex = -1;
  for (let i = rows.length - 1; i >= 0; i--) {
    if (isRowApproved(rows[i])) {
      lastApprovedIndex = i;
      break;
    }
  }

  // All rows prior to the last approved row must be either approved, saved, or skipped
  for (let i = 0; i <= lastApprovedIndex; i++) {
    const r = rows[i];
    const isReady =
      isRowApproved(r) ||
      r.status === "saved" ||
      r.status === "skipped" ||
      r.draft.reviewStatus === "SKIPPED";
    if (!isReady) {
      return {
        canStart: false,
        reason: `Vùng ${i + 1} chưa được duyệt hoặc bỏ qua. Hãy duyệt theo thứ tự từ trên xuống dưới.`,
      };
    }
  }

  return { canStart: true };
}

export function syncRowsFromJournal<T extends ReviewRowLike>(rows: T[], journal: BatchJournal): T[] {
  const entryByDraftId = new Map(journal.entries.map((e) => [e.draftId, e]));
  return rows.map((row) => {
    const entry = entryByDraftId.get(row.draft.localId);
    if (!entry) return row;
    if (entry.state === "COMMITTED") {
      return {
        ...row,
        status: "saved",
        serverStepId: entry.serverStepId,
        error: null,
      };
    }
    if (entry.state === "REJECTED" || entry.state === "UNKNOWN") {
      return {
        ...row,
        status: "manual",
        error: entry.error ?? "Lưu bước giải chưa thành công",
      };
    }
    return row;
  });
}
