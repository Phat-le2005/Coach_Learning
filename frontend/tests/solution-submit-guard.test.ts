import test from "node:test";
import assert from "node:assert/strict";
import { withSafeBatchSubmission } from "../src/features/math-workspace/utils/solution-submit-guard.js";
import type { BatchJournal, BatchLock } from "../src/features/math-workspace/utils/batch-manager.js";

function journal(state: BatchJournal["state"], attemptId = "attempt-1"): BatchJournal {
  const frozen = { expected_attempt_revision: 1, client_action_id: "action-1", step_type: "ROOT_FINDING" as const,
    content_latex: "x=1", explanation_text: null, artifact: null };
  const content = { step_type: frozen.step_type, content_latex: frozen.content_latex, explanation_text: null, artifact: null };
  const entry: BatchJournal["entries"][number] = { draftId: "draft-1", actionId: "action-1", content,
    state: state === "COMPLETE" ? "COMMITTED" : state === "ABANDONED" ? "REJECTED" : "QUEUED",
    frozen: state === "COMPLETE" ? frozen : null,
    beforeStepIds: state === "COMPLETE" ? [] : null,
    serverStepId: state === "COMPLETE" ? "step-1" : null,
    serverRevision: state === "COMPLETE" ? 2 : null,
    error: null };
  return { schemaVersion: 1, batchId: "batch-1", attemptId, createdAt: 1234567,
    nextRevision: 2, state, entries: [entry], message: null };
}
const lock: BatchLock = { runExclusive: async (_id, work) => work() };

for (const state of ["PREPARED", "PAUSED"] as const) {
  test(`submission fails closed on ${state} journal even if React recovery state is still empty`, async () => {
    let sent = 0;
    await assert.rejects(withSafeBatchSubmission("attempt-1", {load: async () => journal(state)}, lock, async () => {sent++; return "submitted";}),
      /BATCH_PENDING_RECOVERY_REQUIRED/);
    assert.equal(sent, 0);
  });
}

for (const state of ["COMPLETE", "ABANDONED"] as const) {
  test(`submission accepts authoritative ${state} journal`, async () => {
    let sent = 0;
    const result = await withSafeBatchSubmission("attempt-1", {load: async () => journal(state)}, lock, async () => {sent++; return "submitted";});
    assert.equal(result, "submitted");
    assert.equal(sent, 1);
  });
}

test("no existing journal permits ordinary single-step submission", async () => {
  assert.equal(await withSafeBatchSubmission("attempt-1", {load: async () => null}, lock, async () => 42), 42);
});

test("invalid or mismatched journal never invokes submit", async () => {
  let sent = 0;
  for (const value of [{state:"PAUSED"}, journal("PAUSED", "different-attempt")] as unknown[]) {
    await assert.rejects(withSafeBatchSubmission("attempt-1", {load: async () => value as BatchJournal}, lock,
      async () => {sent++; return "submitted";}), /BATCH_JOURNAL_CORRUPT/);
  }
  assert.equal(sent, 0);
});

test("storage failure is fail-closed, not an empty journal", async () => {
  let sent = 0;
  await assert.rejects(withSafeBatchSubmission("attempt-1", {
    load: async () => {throw new Error("BATCH_INDEXEDDB_UNAVAILABLE");},
  }, lock, async () => {sent++; return "submitted";}), /BATCH_INDEXEDDB_UNAVAILABLE/);
  assert.equal(sent, 0);
});

test("Web Lock collision rejects submission before database mutation", async () => {
  let sent = 0;
  const deniedLock: BatchLock = {runExclusive: async () => null};
  await assert.rejects(withSafeBatchSubmission("attempt-1", {load: async () => null}, deniedLock,
    async () => {sent++; return "submitted";}), /BATCH_SUBMIT_LOCK_UNAVAILABLE/);
  assert.equal(sent, 0);
});

test("the lock is held during journal verification AND the actual submit call", async () => {
  let insideLock = false;
  const enforcingLock: BatchLock = {runExclusive: async (_id, work) => {
    insideLock = true;
    try {return await work();} finally {insideLock = false;}
  }};
  const result = await withSafeBatchSubmission("attempt-1", {
    load: async () => {assert.equal(insideLock, true); return null;},
  }, enforcingLock, async () => {assert.equal(insideLock, true); return "committed";});
  assert.equal(result, "committed");
  assert.equal(insideLock, false);
});

test("a blocked preflight never allocates an action key; next attempt uses refreshed revision", async () => {
  let generated = 0;
  let pending: { revision: number; actionId: string } | null = null;
  let uiRevision = 2;
  let stored: BatchJournal | null = journal("PAUSED");
  const submit = async () => withSafeBatchSubmission("attempt-1", { load: async () => stored }, lock, async () => {
    const token = pending ?? { revision: uiRevision, actionId: `action-${++generated}` };
    pending = token;
    return token;
  });

  await assert.rejects(submit(), /BATCH_PENDING_RECOVERY_REQUIRED/);
  assert.equal(pending, null);
  assert.equal(generated, 0);
  uiRevision = 3; // authoritative server state after another tab completed its batch
  stored = journal("COMPLETE");
  const result = await submit();
  assert.deepEqual(result, { revision: 3, actionId: "action-1" });
  assert.equal(generated, 1);
});

test("an ambiguous network outcome reuses the same action key for idempotent replay", async () => {
  let generated = 0;
  let pending: { revision: number; actionId: string } | null = null;
  const calls: string[] = [];
  const send = async () => withSafeBatchSubmission("attempt-1", { load: async () => null }, lock, async () => {
    const token = pending ?? { revision: 5, actionId: `action-${++generated}` };
    pending = token;
    calls.push(token.actionId);
    if (calls.length === 1) throw new Error("NETWORK_UNKNOWN_OUTCOME");
    return token;
  });
  await assert.rejects(send(), /NETWORK_UNKNOWN_OUTCOME/);
  const retried = await send();
  assert.equal(retried.revision, 5);
  assert.deepEqual(calls, ["action-1", "action-1"]);
  assert.equal(generated, 1);
});
