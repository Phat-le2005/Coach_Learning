import type { BatchJournal, BatchJournalStore, BatchLock } from "./batch-manager";

const DB_NAME = "edums_step_batch_journal_v1";
const STORE_NAME = "pending_batches";

const VALID_BATCH_STATES = new Set(["PREPARED", "PAUSED", "COMPLETE", "ABANDONED"]);
const VALID_ENTRY_STATES = new Set(["QUEUED", "SENDING", "UNKNOWN", "COMMITTED", "REJECTED"]);

export function isValidBatchJournal(value: unknown): value is BatchJournal {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const j = value as Record<string, unknown>;

  // 1. Root schema validation
  if (j.schemaVersion !== 1) return false;
  if (typeof j.attemptId !== "string" || !j.attemptId.trim()) return false;
  if (typeof j.batchId !== "string" || !j.batchId.trim()) return false;
  if (typeof j.createdAt !== "number" || !Number.isFinite(j.createdAt) || j.createdAt <= 0) return false;
  if (typeof j.nextRevision !== "number" || !Number.isSafeInteger(j.nextRevision) || j.nextRevision < 0) return false;
  if (typeof j.state !== "string" || !VALID_BATCH_STATES.has(j.state)) return false;
  if (j.message !== null && typeof j.message !== "string") return false;
  if (!Array.isArray(j.entries)) return false;

  const seenActionIds = new Set<string>();
  const seenDraftIds = new Set<string>();
  const seenServerStepIds = new Set<string>();

  // 2. Entries validation
  for (const e of j.entries) {
    if (!e || typeof e !== "object" || Array.isArray(e)) return false;
    const entry = e as Record<string, unknown>;

    // draftId & actionId consistency
    if (typeof entry.draftId !== "string" || !entry.draftId.trim()) return false;
    if (typeof entry.actionId !== "string" || !entry.actionId.trim()) return false;
    if (seenActionIds.has(entry.actionId) || seenDraftIds.has(entry.draftId)) return false;
    seenActionIds.add(entry.actionId);
    seenDraftIds.add(entry.draftId);

    // Duplicate serverStepId check
    if (entry.serverStepId !== null && entry.serverStepId !== undefined) {
      if (typeof entry.serverStepId !== "string" || !entry.serverStepId.trim()) return false;
      if (seenServerStepIds.has(entry.serverStepId)) return false;
      seenServerStepIds.add(entry.serverStepId);
    }

    // Entry state
    if (typeof entry.state !== "string" || !VALID_ENTRY_STATES.has(entry.state)) return false;

    // Content structure
    if (!entry.content || typeof entry.content !== "object" || Array.isArray(entry.content)) return false;
    const content = entry.content as Record<string, unknown>;
    if (typeof content.step_type !== "string" || !content.step_type.trim()) return false;
    if (content.content_latex !== null && typeof content.content_latex !== "string") return false;
    if (content.explanation_text !== null && typeof content.explanation_text !== "string") return false;
    if (content.artifact !== null) return false;

    // Frozen request structure & consistency
    if (entry.frozen !== null) {
      if (typeof entry.frozen !== "object" || Array.isArray(entry.frozen)) return false;
      const frozen = entry.frozen as Record<string, unknown>;
      if (!Number.isSafeInteger(frozen.expected_attempt_revision) || (frozen.expected_attempt_revision as number) < 0) return false;
      // Invariant: client_action_id MUST strictly equal entry.actionId
      if (frozen.client_action_id !== entry.actionId) return false;
      // Invariant: frozen payload content must match entry content
      if (frozen.step_type !== content.step_type) return false;
      if (frozen.content_latex !== content.content_latex) return false;
      if (frozen.explanation_text !== content.explanation_text) return false;
      if (frozen.artifact !== null) return false;
    }

    // beforeStepIds validation
    if (entry.beforeStepIds !== null) {
      if (!Array.isArray(entry.beforeStepIds)) return false;
      for (const id of entry.beforeStepIds) {
        if (typeof id !== "string") return false;
      }
    }

    // Error and errorCode field validation (backward compatible with undefined/null)
    if (entry.error !== null && typeof entry.error !== "string") return false;
    if (entry.errorCode !== undefined && entry.errorCode !== null && typeof entry.errorCode !== "string") return false;

    // Invariant: entry state vs frozen, beforeStepIds, serverStepId, serverRevision
    switch (entry.state) {
      case "QUEUED":
        if (entry.frozen !== null || entry.beforeStepIds !== null || entry.serverStepId !== null || entry.serverRevision !== null) {
          return false;
        }
        break;
      case "SENDING":
      case "UNKNOWN":
        if (entry.frozen === null || !Array.isArray(entry.beforeStepIds) || entry.serverStepId !== null || entry.serverRevision !== null) {
          return false;
        }
        break;
      case "COMMITTED":
        if (
          entry.frozen === null ||
          !Array.isArray(entry.beforeStepIds) ||
          typeof entry.serverStepId !== "string" ||
          !entry.serverStepId.trim() ||
          !Number.isSafeInteger(entry.serverRevision) ||
          (entry.serverRevision as number) < 1 ||
          entry.error !== null
        ) {
          return false;
        }
        break;
      case "REJECTED":
        if (entry.serverStepId !== null || entry.serverRevision !== null) {
          return false;
        }
        break;
      default:
        return false;
    }
  }

  // 3. Contradictory batch-level states
  if (j.state === "COMPLETE") {
    if (j.entries.length === 0) return false;
    if (!j.entries.every((e: any) => e.state === "COMMITTED")) return false;
  }
  if (j.state === "ABANDONED") {
    if (!j.entries.some((e: any) => e.state === "REJECTED")) return false;
    if (j.entries.some((e: any) => e.state === "SENDING" || e.state === "UNKNOWN")) return false;
  }

  return true;
}

export function validateBatchJournal(value: unknown): BatchJournal {
  if (!isValidBatchJournal(value)) {
    throw new Error("BATCH_JOURNAL_CORRUPT");
  }
  return value;
}

/** Browser-only adapter. Never open IndexedDB during SSR or at module import. */
export class IndexedDbBatchJournal implements BatchJournalStore {
  private async open(): Promise<IDBDatabase> {
    if (typeof indexedDB === "undefined") throw new Error("BATCH_INDEXEDDB_UNAVAILABLE");
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) db.createObjectStore(STORE_NAME, { keyPath: "attemptId" });
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("BATCH_INDEXEDDB_OPEN_FAILED"));
      request.onblocked = () => reject(new Error("BATCH_INDEXEDDB_BLOCKED"));
    });
  }

  async load(attemptId: string): Promise<BatchJournal | null> {
    const db = await this.open();
    try {
      return await new Promise<BatchJournal | null>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, "readonly");
        const req = tx.objectStore(STORE_NAME).get(attemptId);
        let result: BatchJournal | null = null;
        req.onsuccess = () => {
          const raw = req.result;
          if (raw === undefined || raw === null) {
            result = null;
          } else if (isValidBatchJournal(raw)) {
            result = raw;
          } else {
            // Fail closed on schema corruption rather than guessing
            reject(new Error("BATCH_JOURNAL_CORRUPT"));
            return;
          }
        };
        tx.oncomplete = () => resolve(result);
        tx.onabort = () => reject(tx.error ?? new Error("BATCH_JOURNAL_READ_ABORTED"));
        tx.onerror = () => reject(tx.error ?? new Error("BATCH_JOURNAL_READ_FAILED"));
      });
    } finally { db.close(); }
  }

  async save(journal: BatchJournal): Promise<void> {
    const db = await this.open();
    try {
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, "readwrite");
        tx.objectStore(STORE_NAME).put(journal);
        // Request success is NOT enough: wait for the IndexedDB transaction commit.
        tx.oncomplete = () => resolve();
        tx.onabort = () => reject(tx.error ?? new Error("BATCH_JOURNAL_WRITE_ABORTED"));
        tx.onerror = () => reject(tx.error ?? new Error("BATCH_JOURNAL_WRITE_FAILED"));
      });
    } finally { db.close(); }
  }
}

/** Fails closed on browsers without Web Locks, avoiding unsafe cross-tab concurrency. */
export class BrowserBatchLock implements BatchLock {
  async runExclusive<T>(attemptId: string, work: () => Promise<T>): Promise<T | null> {
    if (typeof navigator === "undefined" || !navigator.locks) return null;
    return navigator.locks.request(`edums-ocr-batch:${attemptId}`, { mode: "exclusive", ifAvailable: true },
      async (lock) => lock ? work() : null);
  }
}
