import type { SolutionAttemptRead, StepKind, StepMutationRequest } from "@/lib/api/contracts";
import { isValidBatchJournal } from "./batch-journal";

/** Safe client-side orchestration of existing atomic ADD_STEP mutations. No UI or backend coupling. */
export type BatchEntryState = "QUEUED" | "SENDING" | "UNKNOWN" | "COMMITTED" | "REJECTED";
export type BatchState = "PREPARED" | "PAUSED" | "COMPLETE" | "ABANDONED";

export interface ApprovedStepIntent {
  draftId: string;
  actionId: string; // UUID issued once for this intended operation; never regenerated on retry.
  approved: true;
  stepType: StepKind;
  contentLatex: string | null;
  explanationText: string | null;
}

export interface FrozenStepRequest {
  expected_attempt_revision: number;
  client_action_id: string;
  step_type: StepKind;
  content_latex: string | null;
  explanation_text: string | null;
  artifact: null;
}

export interface BatchEntry {
  draftId: string;
  actionId: string;
  content: Readonly<Pick<FrozenStepRequest, "step_type" | "content_latex" | "explanation_text" | "artifact">>;
  state: BatchEntryState;
  frozen: FrozenStepRequest | null;
  beforeStepIds: string[] | null;
  serverStepId: string | null;
  serverRevision: number | null;
  error: string | null;
  errorCode?: string | null;
}

export interface BatchJournal {
  schemaVersion: 1;
  batchId: string;
  attemptId: string;
  createdAt: number;
  nextRevision: number;
  state: BatchState;
  entries: BatchEntry[];
  message: string | null;
}

export interface BatchJournalStore {
  load(attemptId: string): Promise<BatchJournal | null>;
  save(journal: BatchJournal): Promise<void>; // Must resolve only after durable transaction completes.
}
export interface BatchApi {
  getAttempt(attemptId: string): Promise<SolutionAttemptRead>;
  addStep(attemptId: string, request: StepMutationRequest): Promise<SolutionAttemptRead>;
}
/** Cross-tab mutual exclusion is mandatory: returning null means lock unavailable. */
export interface BatchLock {
  runExclusive<T>(attemptId: string, work: () => Promise<T>): Promise<T | null>;
}
export type BatchRunResult =
  | { status: "COMPLETE"; journal: BatchJournal; attempt: SolutionAttemptRead }
  | { status: "PAUSED"; journal: BatchJournal }
  | { status: "LOCKED" };

function validateAttempt(attempt: SolutionAttemptRead, attemptId: string): string[] {
  if (attempt.id !== attemptId || !Array.isArray(attempt.steps)) throw new Error("BATCH_ATTEMPT_INCOMPLETE");
  if (attempt.status !== "DRAFT" && attempt.status !== "IN_PROGRESS") throw new Error("BATCH_ATTEMPT_LOCKED");
  if (!Number.isSafeInteger(attempt.current_revision) || attempt.current_revision < 0) throw new Error("BATCH_BAD_REVISION");
  return attempt.steps.map((step) => step.id);
}
function copyJournal(j: BatchJournal): BatchJournal {
  return JSON.parse(JSON.stringify(j)) as BatchJournal;
}
function reason(error: unknown): string {
  if (error instanceof Error) return error.message.slice(0, 400);
  return "BATCH_OPERATION_FAILED";
}
function statusAndCode(error: unknown): { status: number | undefined; code: string | undefined } {
  if (!error || typeof error !== "object") return { status: undefined, code: undefined };
  const e = error as { status?: unknown; code?: unknown };
  return { status: typeof e.status === "number" ? e.status : undefined,
    code: typeof e.code === "string" ? e.code : undefined };
}

const SAFE_ABANDON_ERROR_CODES = new Set(["INVALID_DRAFT", "HTTP_422", "VALIDATION_ERROR"]);

function normalizeContractString(val: string | null | undefined): string | null {
  if (val === undefined || val === null) return null;
  const trimmed = val.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function verifyStepContentMatches(
  serverStep: { step_type: string; content_latex?: string | null; explanation_text?: string | null },
  expected: FrozenStepRequest
): boolean {
  if (serverStep.step_type !== expected.step_type) return false;
  if (normalizeContractString(serverStep.content_latex) !== normalizeContractString(expected.content_latex)) {
    return false;
  }
  if (normalizeContractString(serverStep.explanation_text) !== normalizeContractString(expected.explanation_text)) {
    return false;
  }
  return true;
}

export class SequentialBatchManager {
  constructor(private readonly api: BatchApi, private readonly store: BatchJournalStore, private readonly lock: BatchLock) {}

  /** Starts only after explicit human review, and does not replace an unfinished journal. */
  async start(attemptId: string, batchId: string, intents: readonly ApprovedStepIntent[]): Promise<BatchRunResult> {
    const result = await this.lock.runExclusive(attemptId, async () => {
      const existing = await this.store.load(attemptId);
      if (existing) {
        if (!isValidBatchJournal(existing)) throw new Error("BATCH_JOURNAL_CORRUPT");
        if (existing.state !== "COMPLETE" && existing.state !== "ABANDONED") throw new Error("BATCH_PENDING_RECOVERY_REQUIRED");
      }
      if (!batchId || !attemptId || !intents.length) throw new Error("BATCH_EMPTY_OR_BAD_ID");
      if (new Set(intents.map((x) => x.actionId)).size !== intents.length
          || new Set(intents.map((x) => x.draftId)).size !== intents.length) throw new Error("BATCH_DUPLICATE_ID");
      if (intents.some((x) => x.approved !== true || !x.actionId || !x.draftId ||
          !(x.contentLatex?.trim() || x.explanationText?.trim()))) throw new Error("BATCH_DRAFT_NOT_APPROVED");
      const current = await this.api.getAttempt(attemptId);
      validateAttempt(current, attemptId);
      const journal: BatchJournal = {
        schemaVersion: 1, batchId, attemptId, createdAt: Date.now(), nextRevision: current.current_revision,
        state: "PREPARED", message: null,
        entries: intents.map((x) => ({ draftId: x.draftId, actionId: x.actionId,
          content: { step_type: x.stepType, content_latex: x.contentLatex,
            explanation_text: x.explanationText, artifact: null },
          state: "QUEUED", frozen: null, beforeStepIds: null,
          serverStepId: null, serverRevision: null, error: null, errorCode: null })),
      };
      // Write-ahead: no POST can occur until the entire initial plan is persisted.
      await this.store.save(copyJournal(journal));
      return this.execute(journal);
    });
    return result ?? { status: "LOCKED" };
  }

  /** Resume only an existing journal; never reconstruct or silently rebase lost requests. */
  async resume(attemptId: string): Promise<BatchRunResult> {
    const result = await this.lock.runExclusive(attemptId, async () => {
      const journal = await this.store.load(attemptId);
      if (!journal) throw new Error("BATCH_JOURNAL_NOT_FOUND");
      if (journal.attemptId !== attemptId) throw new Error("BATCH_ATTEMPT_MISMATCH");
      if (!isValidBatchJournal(journal)) throw new Error("BATCH_JOURNAL_CORRUPT");
      return this.execute(journal);
    });
    return result ?? { status: "LOCKED" };
  }

  /** Explicit abandonment is allowed only when no request has an uncertain outcome
   * and all rejected entries are definitively uncommitted (e.g. HTTP 422 validation error).
   * Operations that may have committed (UNKNOWN, CONTENT_MISMATCH) or terminal errors
   * (ACTION_KEY_REUSED) must NEVER be abandoned.
   */
  async abandonRejected(attemptId: string): Promise<BatchJournal | null> {
    return this.lock.runExclusive(attemptId, async () => {
      const journal = await this.store.load(attemptId);
      if (!journal) throw new Error("BATCH_JOURNAL_NOT_FOUND");
      if (journal.attemptId !== attemptId) throw new Error("BATCH_ATTEMPT_MISMATCH");
      if (!isValidBatchJournal(journal)) throw new Error("BATCH_JOURNAL_CORRUPT");

      // 1. Must be in PAUSED state
      if (journal.state !== "PAUSED") {
        throw new Error("BATCH_NOT_SAFE_TO_ABANDON");
      }

      // 2. Must not contain any operation whose outcome is uncertain or potentially committed
      if (journal.entries.some((entry) => entry.state === "SENDING" || entry.state === "UNKNOWN")) {
        throw new Error("BATCH_NOT_SAFE_TO_ABANDON");
      }

      // 3. Must not have non-abandonable fatal codes
      const hasUnsafeError = journal.entries.some(
        (entry) =>
          entry.errorCode === "CONTENT_MISMATCH" ||
          entry.errorCode === "ACTION_KEY_REUSED" ||
          entry.error?.includes("CONTENT_MISMATCH") ||
          entry.error?.includes("ACTION_KEY_REUSED") ||
          journal.message === "BATCH_SERVER_CONTENT_MISMATCH" ||
          journal.message === "BATCH_SEND_ACTION_KEY_REUSED"
      );
      if (hasUnsafeError) {
        throw new Error("BATCH_NOT_SAFE_TO_ABANDON");
      }

      // 4. Must have at least one REJECTED entry
      const rejectedEntries = journal.entries.filter((entry) => entry.state === "REJECTED");
      if (rejectedEntries.length === 0) {
        throw new Error("BATCH_NOT_SAFE_TO_ABANDON");
      }

      // 5. Allowlist: all rejected entries must be definitively uncommitted (e.g. HTTP 422)
      const isDefinitiveUncommittedRejection = (entry: BatchEntry): boolean => {
        if (entry.serverStepId !== null || entry.serverRevision !== null) return false;
        if (entry.errorCode && SAFE_ABANDON_ERROR_CODES.has(entry.errorCode)) return true;
        return false;
      };

      if (!rejectedEntries.every(isDefinitiveUncommittedRejection)) {
        throw new Error("BATCH_NOT_SAFE_TO_ABANDON");
      }

      // 6. Authoritative server reconciliation for all COMMITTED entries
      const server = await this.api.getAttempt(attemptId);
      if (!Array.isArray(server.steps) || server.id !== attemptId) {
        throw new Error("BATCH_RECONCILIATION_REQUIRED");
      }
      const serverStepsMap = new Map(server.steps.map((s) => [s.id, s]));
      for (const entry of journal.entries) {
        if (entry.state === "COMMITTED") {
          if (!entry.serverStepId) throw new Error("BATCH_RECONCILIATION_REQUIRED");
          const step = serverStepsMap.get(entry.serverStepId);
          if (!step) throw new Error("BATCH_RECONCILIATION_REQUIRED");
          if (entry.frozen && !verifyStepContentMatches(step, entry.frozen)) {
            throw new Error("BATCH_RECONCILIATION_REQUIRED");
          }
        }
      }
      journal.state = "ABANDONED";
      journal.message = "BATCH_ABANDONED_AFTER_REJECTION";
      await this.store.save(copyJournal(journal));
      return copyJournal(journal);
    });
  }

  private async pause(journal: BatchJournal, message: string): Promise<BatchRunResult> {
    journal.state = "PAUSED";
    journal.message = message;
    try {
      await this.store.save(copyJournal(journal));
    } catch {
      // Best-effort journal write during pause: do not mask the original pause reason
    }
    return { status: "PAUSED", journal: copyJournal(journal) };
  }

  private async execute(journal: BatchJournal): Promise<BatchRunResult> {
    if (journal.state === "ABANDONED") throw new Error("BATCH_ALREADY_ABANDONED");
    if (journal.state === "COMPLETE") {
      const fresh = await this.api.getAttempt(journal.attemptId);
      if (!Array.isArray(fresh.steps) || fresh.id !== journal.attemptId) {
        return this.pause(journal, "BATCH_PREVIOUS_RESULT_CHANGED");
      }
      const stepsMap = new Map(fresh.steps.map((s) => [s.id, s]));
      const allMatch = journal.entries.every((e) => {
        if (!e.serverStepId) return false;
        const step = stepsMap.get(e.serverStepId);
        if (!step) return false;
        if (e.frozen && !verifyStepContentMatches(step, e.frozen)) return false;
        return true;
      });
      if (!allMatch) {
        return this.pause(journal, "BATCH_PREVIOUS_RESULT_CHANGED");
      }
      return { status: "COMPLETE", journal: copyJournal(journal), attempt: fresh };
    }
    for (let i = 0; i < journal.entries.length; i++) {
      const entry = journal.entries[i];
      if (entry.state === "COMMITTED") continue;
      if (entry.errorCode === "CONTENT_MISMATCH") return this.pause(journal, "BATCH_SERVER_CONTENT_MISMATCH");
      if (entry.errorCode === "ACTION_KEY_REUSED") return this.pause(journal, "BATCH_SEND_ACTION_KEY_REUSED");
      if (entry.state === "REJECTED") return this.pause(journal, "BATCH_REJECTED_REQUIRES_REVIEW");

      if (entry.frozen === null) {
        // No request was sent yet. Reject revisions changed by other tabs rather than silently rebasing.
        let current: SolutionAttemptRead;
        try { current = await this.api.getAttempt(journal.attemptId); }
        catch (error) { return this.pause(journal, `BATCH_PREPARE_${reason(error)}`); }
        let beforeIds: string[];
        try { beforeIds = validateAttempt(current, journal.attemptId); }
        catch (error) { return this.pause(journal, reason(error)); }
        if (current.current_revision !== journal.nextRevision) {
          return this.pause(journal, "BATCH_REVISION_CONFLICT_BEFORE_SEND");
        }
        entry.frozen = {
          expected_attempt_revision: current.current_revision,
          client_action_id: entry.actionId,
          step_type: entry.content.step_type,
          content_latex: entry.content.content_latex,
          explanation_text: entry.content.explanation_text,
          artifact: null,
        };
        entry.beforeStepIds = beforeIds;
        entry.state = "SENDING";
        // Persist exactly what the backend will hash BEFORE sending it.
        await this.store.save(copyJournal(journal));
      }
      // If this is a resumed UNKNOWN/SENDING operation, replay exactly the frozen request.
      const request = entry.frozen;
      if (!request || !entry.beforeStepIds) throw new Error("BATCH_JOURNAL_CORRUPT");
      let response: SolutionAttemptRead;
      try {
        response = await this.api.addStep(journal.attemptId, { ...request });
      } catch (error) {
        // Network/HTTP error: preserve frozen request for retry
        const { status, code } = statusAndCode(error);
        entry.error = reason(error);
        entry.errorCode = code ?? (status !== undefined ? `HTTP_${status}` : "UNKNOWN");
        entry.state = status === undefined || status >= 500 || status === 401 || status === 429
          ? "UNKNOWN" : "REJECTED";
        if (code === "ACTION_KEY_REUSED") {
          entry.state = "REJECTED";
          entry.errorCode = "ACTION_KEY_REUSED";
        }
        return this.pause(journal, `BATCH_SEND_${code ?? status ?? "UNKNOWN"}`);
      }

      if (!Array.isArray(response.steps) || response.id !== journal.attemptId
        || !Number.isSafeInteger(response.current_revision)
        || response.current_revision !== request.expected_attempt_revision + 1) {
        // The POST may have committed. Leave the frozen request retryable and DO NOT send next step.
        return this.pause(journal, "BATCH_UNVERIFIABLE_RESPONSE");
      }
      const before = new Set(entry.beforeStepIds);
      const additions = response.steps.filter((step) => !before.has(step.id));
      if (additions.length !== 1) return this.pause(journal, "BATCH_UNVERIFIABLE_STEP_ID");
      const addedStep = additions[0];
      if (!verifyStepContentMatches(addedStep, request)) {
        // Step committed on server, but content does not match the frozen request.
        // This is Case B: potentially committed with corrupt/mismatched content.
        // It MUST be classified as UNKNOWN with persistent CONTENT_MISMATCH,
        // and MUST NEVER be classified as safely abandonable REJECTED!
        entry.state = "UNKNOWN";
        entry.error = "BATCH_SERVER_CONTENT_MISMATCH";
        entry.errorCode = "CONTENT_MISMATCH";
        return this.pause(journal, "BATCH_SERVER_CONTENT_MISMATCH");
      }
      entry.serverStepId = addedStep.id;
      entry.serverRevision = response.current_revision;
      entry.state = "COMMITTED";
      entry.error = null;
      entry.errorCode = null;
      journal.nextRevision = response.current_revision;
      journal.state = "PREPARED";
      journal.message = null;

      try {
        await this.store.save(copyJournal(journal));
      } catch (saveError) {
        // Persistence failed AFTER a successful server commit.
        // The step IS committed on the server; do NOT classify as network error or overwrite state to UNKNOWN.
        // Returning PAUSED preserves in-memory COMMITTED state and avoids sending subsequent steps.
        journal.state = "PAUSED";
        journal.message = "BATCH_PERSISTENCE_FAILED_AFTER_COMMIT";
        return {
          status: "PAUSED",
          journal: copyJournal(journal),
        };
      }
    }
    // A replay may have returned a historic snapshot. GET authoritative state before success.
    let fresh: SolutionAttemptRead;
    try { fresh = await this.api.getAttempt(journal.attemptId); }
    catch (error) { return this.pause(journal, `BATCH_VERIFY_${reason(error)}`); }
    if (!Array.isArray(fresh.steps) || fresh.id !== journal.attemptId) {
      return this.pause(journal, "BATCH_SERVER_RECONCILIATION_REQUIRED");
    }
    const freshStepsMap = new Map(fresh.steps.map((step) => [step.id, step]));
    for (const entry of journal.entries) {
      if (!entry.serverStepId) {
        return this.pause(journal, "BATCH_SERVER_RECONCILIATION_REQUIRED");
      }
      const serverStep = freshStepsMap.get(entry.serverStepId);
      if (!serverStep) {
        return this.pause(journal, "BATCH_SERVER_RECONCILIATION_REQUIRED");
      }
      if (entry.frozen && !verifyStepContentMatches(serverStep, entry.frozen)) {
        // Content discrepancy discovered after commit is a batch-level reconciliation problem.
        // Keep the committed entry identity, serverStepId, and serverRevision intact
        // so the journal schema remains completely valid and recoverable.
        return this.pause(journal, "BATCH_SERVER_CONTENT_MISMATCH");
      }
    }
    journal.state = "COMPLETE";
    journal.message = null;
    try {
      await this.store.save(copyJournal(journal));
    } catch (saveError) {
      return this.pause(journal, "BATCH_PERSISTENCE_FAILED_ON_COMPLETE");
    }
    return { status: "COMPLETE", journal: copyJournal(journal), attempt: fresh };
  }
}
