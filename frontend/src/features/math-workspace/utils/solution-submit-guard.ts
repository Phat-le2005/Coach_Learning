import type { BatchJournalStore, BatchLock } from "./batch-manager";
import { isValidBatchJournal } from "./batch-journal";

/**
 * Serialize SUBMIT with the same per-attempt Web Lock as OCR batch mutations.
 * Reading journal on click (inside the lock) closes the F5 / stale React-state gap.
 * A callback result is wrapped to distinguish it from the lock's null signal.
 */
export async function withSafeBatchSubmission<T>(
  attemptId: string,
  store: Pick<BatchJournalStore, "load">,
  lock: BatchLock,
  submit: () => Promise<T>,
): Promise<T> {
  if (!attemptId) throw new Error("BATCH_ATTEMPT_MISMATCH");
  const result = await lock.runExclusive(attemptId, async () => {
    const journal = await store.load(attemptId);
    if (journal) {
      if (!isValidBatchJournal(journal) || journal.attemptId !== attemptId) {
        throw new Error("BATCH_JOURNAL_CORRUPT");
      }
      if (journal.state !== "COMPLETE" && journal.state !== "ABANDONED") {
        throw new Error("BATCH_PENDING_RECOVERY_REQUIRED");
      }
    }
    return { value: await submit() };
  });
  if (result === null) throw new Error("BATCH_SUBMIT_LOCK_UNAVAILABLE");
  return result.value;
}
