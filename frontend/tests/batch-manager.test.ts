import test from "node:test";
import assert from "node:assert/strict";
import type { SolutionAttemptRead, StepMutationRequest } from "../src/lib/api/contracts.js";
import { SequentialBatchManager, type BatchApi, type BatchJournal, type BatchJournalStore, type BatchLock, type ApprovedStepIntent } from "../src/features/math-workspace/utils/batch-manager.js";
import { isValidBatchJournal, validateBatchJournal } from "../src/features/math-workspace/utils/batch-journal.js";
import { ApiResponseError } from "../src/lib/api/client.js";

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
const approved = (count: number): ApprovedStepIntent[] => Array.from({ length: count }, (_, i) => ({
  draftId: `draft-${i}`, actionId: `action-${i}`, approved: true as const,
  stepType: "EXPLANATION" as const, contentLatex: `x=${i}`, explanationText: null,
}));

class Store implements BatchJournalStore {
  saved: BatchJournal | null = null;
  writes = 0;
  failOnWrite: number | null = null;
  async load(): Promise<BatchJournal | null> { return this.saved ? clone(this.saved) : null; }
  async save(v: BatchJournal): Promise<void> {
    this.writes++;
    if (this.failOnWrite === this.writes) throw new Error("DISK_FULL");
    this.saved = clone(v);
  }
}
class Lock implements BatchLock {
  busy = false;
  async runExclusive<T>(_id: string, work: () => Promise<T>): Promise<T | null> {
    if (this.busy) return null;
    this.busy = true;
    try { return await work(); } finally { this.busy = false; }
  }
}
class Api implements BatchApi {
  attempt: SolutionAttemptRead = { id: "attempt", question_id: null, status: "DRAFT", current_revision: 1, created_at: "2026-10-31", steps: [] };
  history = new Map<string, { request: StepMutationRequest; response: SolutionAttemptRead }>();
  calls: StepMutationRequest[] = [];
  failBefore = new Set<number>();
  failAfter = new Set<number>();
  responseMissingSteps = new Set<number>();
  async getAttempt(): Promise<SolutionAttemptRead> { return clone(this.attempt); }
  async addStep(_id: string, request: StepMutationRequest): Promise<SolutionAttemptRead> {
    const call = this.calls.length + 1;
    this.calls.push(clone(request));
    if (this.failBefore.has(call)) throw new Error("Network offline before commit");
    const prior = this.history.get(request.client_action_id);
    if (prior) {
      if (JSON.stringify(prior.request) !== JSON.stringify(request)) throw { status: 409, code: "ACTION_KEY_REUSED" };
      return clone(prior.response);
    }
    if (this.attempt.current_revision !== request.expected_attempt_revision) throw { status: 409, code: "SOLUTION_REVISION_CONFLICT" };
    const step = { id: `step-${this.history.size + 1}`, step_index: this.history.size + 1,
      step_type: request.step_type, content_latex: request.content_latex ?? null,
      explanation_text: request.explanation_text ?? null, step_revision_number: 1 };
    this.attempt.steps = [...(this.attempt.steps ?? []), step];
    this.attempt.current_revision++;
    this.attempt.status = "IN_PROGRESS";
    const response = clone(this.attempt);
    this.history.set(request.client_action_id, { request: clone(request), response });
    if (this.failAfter.has(call)) throw new Error("Response lost after commit");
    if (this.responseMissingSteps.has(call)) return { ...response, steps: undefined };
    return response;
  }
}
function setup() {
  const api = new Api(), store = new Store(), lock = new Lock();
  return { api, store, lock, manager: new SequentialBatchManager(api, store, lock) };
}

test("five approved steps save sequentially, chaining server responses", async () => {
  const { manager, api, store } = setup();
  const out = await manager.start("attempt", "batch1", approved(5));
  assert.equal(out.status, "COMPLETE");
  assert.equal(api.attempt.steps?.length, 5);
  assert.deepEqual(api.calls.map(x => x.expected_attempt_revision), [1, 2, 3, 4, 5]);
  assert.equal(store.saved?.state, "COMPLETE");
});
test("different attempts cannot be used through a response with mismatched ID", async () => {
  const { manager } = setup();
  await assert.rejects(() => manager.start("other", "batch1", approved(1)), /BATCH_ATTEMPT_INCOMPLETE/);
});
test("rejects empty, duplicate action IDs and unapproved content before sending", async () => {
  const { manager, api } = setup();
  await assert.rejects(() => manager.start("attempt", "b", []), /BATCH_EMPTY_OR_BAD_ID/);
  const intent = approved(2); intent[1].actionId = intent[0].actionId;
  await assert.rejects(() => manager.start("attempt", "b", intent), /BATCH_DUPLICATE_ID/);
  await assert.rejects(() => manager.start("attempt", "b", [{ ...approved(1)[0], approved: false as true }]), /BATCH_DRAFT_NOT_APPROVED/);
  assert.equal(api.calls.length, 0);
});
test("write-ahead failure prohibits any mutation", async () => {
  const { manager, store, api } = setup();
  store.failOnWrite = 1;
  await assert.rejects(() => manager.start("attempt", "b", approved(2)), /DISK_FULL/);
  assert.equal(api.calls.length, 0);
});
test("frozen request is persisted BEFORE first POST", async () => {
  const { manager, store, api } = setup();
  let observed = false;
  const real = api.addStep.bind(api);
  api.addStep = async (id, req) => {
    assert.equal(store.saved?.entries[0].state, "SENDING");
    assert.deepEqual(store.saved?.entries[0].frozen, req);
    observed = true;
    return real(id, req);
  };
  assert.equal((await manager.start("attempt", "b", approved(1))).status, "COMPLETE");
  assert.equal(observed, true);
});
test("timeout before server commit preserves frozen request; retry commits once", async () => {
  const { manager, api, store } = setup();
  api.failBefore.add(1);
  assert.equal((await manager.start("attempt", "b", approved(2))).status, "PAUSED");
  assert.equal(api.attempt.steps?.length, 0);
  assert.equal(store.saved?.entries[0].state, "UNKNOWN");
  const frozen = clone(store.saved!.entries[0].frozen);
  assert.equal((await manager.resume("attempt")).status, "COMPLETE");
  assert.equal(api.attempt.steps?.length, 2);
  assert.deepEqual(api.calls[1], frozen);
});
test("lost response after commit retries exact action without duplicate", async () => {
  const { manager, api, store } = setup();
  api.failAfter.add(1);
  assert.equal((await manager.start("attempt", "b", approved(3))).status, "PAUSED");
  assert.equal(api.attempt.steps?.length, 1);
  const firstRequest = clone(api.calls[0]);
  assert.equal((await manager.resume("attempt")).status, "COMPLETE");
  assert.deepEqual(api.calls[1], firstRequest);
  assert.equal(api.attempt.steps?.length, 3);
  assert.equal(store.saved?.entries.every(x=>x.state==="COMMITTED"),true);
});
test("unknown retry remains idempotent after simulated F5/new manager", async () => {
  const { manager, api, store, lock } = setup();
  api.failAfter.add(2);
  assert.equal((await manager.start("attempt", "b", approved(5))).status, "PAUSED");
  assert.equal(api.attempt.steps?.length, 2);
  const loaded = new SequentialBatchManager(api, store, lock);
  assert.equal((await loaded.resume("attempt")).status, "COMPLETE");
  assert.equal(api.attempt.steps?.length, 5);
  assert.deepEqual(api.calls.map(x=>x.client_action_id), ["action-0", "action-1", "action-1", "action-2", "action-3", "action-4"]);
});
test("a second batch cannot replace a pending journal", async () => {
  const { manager, api } = setup();
  api.failBefore.add(1);
  assert.equal((await manager.start("attempt", "first", approved(1))).status, "PAUSED");
  await assert.rejects(() => manager.start("attempt", "second", approved(1)), /BATCH_PENDING_RECOVERY_REQUIRED/);
});
test("external revision changes before next POST cause fail-closed pause", async () => {
  const { manager, api, store } = setup();
  const old = api.addStep.bind(api);
  api.addStep = async (id, request) => {
    const res = await old(id, request);
    if (api.calls.length === 1) api.attempt.current_revision += 1; // other client mutation
    return res;
  };
  assert.equal((await manager.start("attempt", "b", approved(3))).status, "PAUSED");
  assert.equal(api.calls.length, 1);
  assert.equal(store.saved?.message, "BATCH_REVISION_CONFLICT_BEFORE_SEND");
});
test("409 conflict rejects current operation and does not send later steps", async () => {
  const { manager, api, store } = setup();
  api.addStep = async () => { throw { status: 409, code: "SOLUTION_REVISION_CONFLICT" }; };
  assert.equal((await manager.start("attempt", "b", approved(2))).status, "PAUSED");
  assert.equal(store.saved?.entries[0].state, "REJECTED");
  assert.equal(store.saved?.entries[1].state, "QUEUED");
});
test("401 and 422 halt safely, preserving pending steps", async () => {
  for (const status of [401, 422]) {
    const { manager, api, store } = setup();
    api.addStep = async () => { throw { status, code: "REJECTED" }; };
    assert.equal((await manager.start("attempt", "b", approved(3))).status, "PAUSED");
    assert.equal(store.saved?.entries[0].state, status === 401 ? "UNKNOWN" : "REJECTED");
    assert.equal(store.saved?.entries[2].state, "QUEUED");
  }
});
test("unverifiable response pauses; old exact request can be replayed", async () => {
  const { manager, api, store } = setup();
  api.responseMissingSteps.add(1);
  assert.equal((await manager.start("attempt", "b", approved(2))).status, "PAUSED");
  assert.equal(store.saved?.entries[0].state, "SENDING");
  assert.equal((await manager.resume("attempt")).status, "COMPLETE");
  assert.equal(api.attempt.steps?.length, 2);
});
test("GET final verifies authoritative steps; missing step never reports complete", async () => {
  const { manager, api, store } = setup();
  const real = api.getAttempt.bind(api);
  let calls = 0;
  api.getAttempt = async () => {
    const a = await real();
    calls++;
    if (calls >= 3) return { ...a, steps: [] };
    return a;
  };
  assert.equal((await manager.start("attempt", "b", approved(1))).status, "PAUSED");
  assert.equal(store.saved?.message, "BATCH_SERVER_RECONCILIATION_REQUIRED");
});
test("same-attempt concurrent run is locked, no duplicate job started", async () => {
  const { manager, lock, api } = setup();
  lock.busy = true;
  assert.equal((await manager.start("attempt", "b", approved(1))).status, "LOCKED");
  assert.equal(api.calls.length, 0);
});
test("already completed journal is safely replayable and allows a new batch", async () => {
  const { manager, api } = setup();
  assert.equal((await manager.start("attempt", "first", approved(2))).status, "COMPLETE");
  assert.equal((await manager.resume("attempt")).status, "COMPLETE");
  assert.equal((await manager.start("attempt", "second", [{...approved(1)[0],actionId:"new-action",draftId:"new-draft"}])).status, "COMPLETE");
  assert.equal(api.attempt.steps?.length,3);
});

test("401 can retry same frozen request after reauthentication", async () => {
  const { manager, api, store } = setup();
  const original = api.addStep.bind(api);
  let denied = true;
  api.addStep = async (id, request) => {
    if (denied) { denied = false; throw { status: 401, code: "UNAUTHORIZED" }; }
    return original(id, request);
  };
  assert.equal((await manager.start("attempt", "b", approved(1))).status, "PAUSED");
  const frozen = clone(store.saved!.entries[0].frozen);
  assert.equal((await manager.resume("attempt")).status, "COMPLETE");
  assert.equal(api.attempt.steps?.length, 1);
  assert.deepEqual(store.saved!.entries[0].frozen, frozen);
});

test("422 rejection can be explicitly abandoned after server reconciliation", async () => {
  const { manager, api, store } = setup();
  const original = api.addStep.bind(api);
  let reject = true;
  api.addStep = async (id, request) => {
    if (reject && request.client_action_id === 'action-1') throw { status: 422, code: "INVALID_DRAFT" };
    return original(id, request);
  };
  assert.equal((await manager.start("attempt", "b", approved(3))).status, "PAUSED");
  assert.equal(api.attempt.steps?.length, 1);
  await assert.rejects(() => manager.start('attempt','new',approved(2)), /BATCH_PENDING_RECOVERY_REQUIRED/);
  const abandoned = await manager.abandonRejected('attempt');
  assert.equal(abandoned?.state, 'ABANDONED');
  reject = false;
  const newPlans = [
    { ...approved(2)[0], draftId: 'corrected1', actionId: 'corrected-action1' },
    { ...approved(2)[1], draftId: 'corrected2', actionId: 'corrected-action2' },
  ];
  assert.equal((await manager.start('attempt', 'revised', newPlans)).status, 'COMPLETE');
  assert.equal(api.attempt.steps?.length, 3);
  assert.equal(store.saved?.entries.length, 2);
});

test("unknown commit cannot be abandoned, preventing duplicate replay", async () => {
  const { manager, api } = setup();
  api.failAfter.add(1);
  assert.equal((await manager.start("attempt", "b", approved(2))).status, "PAUSED");
  await assert.rejects(() => manager.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);
  assert.equal(api.attempt.steps?.length, 1);
});

test("action key reused blocks abandonment even with explicit confirmation", async () => {
  const { manager, api, store } = setup();
  api.addStep = async () => { throw { status: 409, code: "ACTION_KEY_REUSED" }; };
  assert.equal((await manager.start("attempt", "b", approved(1))).status, "PAUSED");
  assert.equal(store.saved?.message, 'BATCH_SEND_ACTION_KEY_REUSED');
  await assert.rejects(() => manager.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);
});

test("BLOCKER 1 regression: action key reused rejection cannot be bypassed by resume or message overwrite", async () => {
  const { manager, api } = setup();
  api.addStep = async () => { throw { status: 409, code: "ACTION_KEY_REUSED" }; };
  assert.equal((await manager.start("attempt", "b", approved(1))).status, "PAUSED");
  await assert.rejects(() => manager.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);

  // Resume overwrites mutable message
  const resumeResult = await manager.resume("attempt");
  assert.equal(resumeResult.status, "PAUSED");

  // Invariant: abandonment MUST still be rejected after resume
  await assert.rejects(() => manager.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);
});

test("BLOCKER 2 regression: server content mismatch MUST NOT return COMPLETE", async () => {
  const { manager, api } = setup();
  const original = api.addStep.bind(api);
  api.addStep = async (id, req) => {
    const res = await original(id, req);
    // Server stored a corrupted content_latex different from frozen request
    const step = res.steps![res.steps!.length - 1];
    step.content_latex = "CORRUPTED_IN_FLIGHT";
    return res;
  };
  const res = await manager.start("attempt", "b", approved(1));
  assert.notEqual(res.status, "COMPLETE");
  assert.equal(res.status, "PAUSED");
});

test("TEST A: content mismatch after server commit MUST NOT become abandonable", async () => {
  const { manager, api } = setup();
  const original = api.addStep.bind(api);
  api.addStep = async (id, req) => {
    const res = await original(id, req);
    // Server stored a different content_latex than requested
    const step = res.steps![res.steps!.length - 1];
    step.content_latex = "DIFFERENT_SERVER_CONTENT";
    return res;
  };
  const res = await manager.start("attempt", "b", approved(1));
  assert.equal(res.status, "PAUSED");

  // Invariant: An operation that committed on server MUST NOT be abandonable!
  await assert.rejects(() => manager.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);

  // Calling resume() must not erase the unsafe status
  const resumed = await manager.resume("attempt");
  assert.equal(resumed.status, "PAUSED");

  // Calling abandonRejected() again must STILL fail!
  await assert.rejects(() => manager.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);

  // No second step with a new action ID may be created through an unsafe abandonment path
  await assert.rejects(() => manager.start("attempt", "new-batch", approved(1)), /BATCH_PENDING_RECOVERY_REQUIRED/);
});

test("TEST B: content mismatch after browser refresh remains fail-closed", async () => {
  const { api, store, lock } = setup();
  const original = api.addStep.bind(api);
  api.addStep = async (id, req) => {
    const res = await original(id, req);
    const step = res.steps![res.steps!.length - 1];
    step.content_latex = "SERVER_TAMPERED";
    return res;
  };

  const mgr1 = new SequentialBatchManager(api, store, lock);
  const res = await mgr1.start("attempt", "b", approved(1));
  assert.equal(res.status, "PAUSED");

  // Simulate F5: new manager instance reading from store
  const mgr2 = new SequentialBatchManager(api, store, lock);
  await assert.rejects(() => mgr2.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);

  // Resume remains fail-closed
  const resumeRes = await mgr2.resume("attempt");
  assert.equal(resumeRes.status, "PAUSED");
  await assert.rejects(() => mgr2.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);
});

test("TEST C: definitive validation rejection before commit allows safe abandonment", async () => {
  const { manager, api } = setup();
  const original = api.addStep.bind(api);
  let reject = true;
  api.addStep = async (id, req) => {
    // Step 0 commits cleanly
    if (req.client_action_id === "action-0") return original(id, req);
    // Step 1 fails with genuine HTTP 422 before commit (no mutation on server)
    if (reject && req.client_action_id === "action-1") throw { status: 422, code: "INVALID_DRAFT" };
    return original(id, req);
  };

  const out = await manager.start("attempt", "b", approved(2));
  assert.equal(out.status, "PAUSED");
  assert.equal(api.attempt.steps?.length, 1); // step 0 committed

  // Explicit abandonment is permitted because step 1 was definitively rejected before commit
  const abandoned = await manager.abandonRejected("attempt");
  assert.equal(abandoned?.state, "ABANDONED");

  // Earlier committed step 0 remains on the server and is not deleted
  assert.equal(api.attempt.steps?.length, 1);
  assert.equal(api.attempt.steps![0].id, "step-1");
});

test("TEST D: ACTION_KEY_REUSED regression remains un-abandonable after resume and reload", async () => {
  const { api, store, lock } = setup();
  api.addStep = async () => { throw { status: 409, code: "ACTION_KEY_REUSED" }; };

  const mgr1 = new SequentialBatchManager(api, store, lock);
  assert.equal((await mgr1.start("attempt", "b", approved(1))).status, "PAUSED");
  await assert.rejects(() => mgr1.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);

  // Resume does not bypass
  await mgr1.resume("attempt");
  await assert.rejects(() => mgr1.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);

  // Reload does not bypass
  const mgr2 = new SequentialBatchManager(api, store, lock);
  await assert.rejects(() => mgr2.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);
});

test("ISSUE 1 regression: final reconciliation content discrepancy preserves valid journal schema across reload", async () => {
  const { api, store, lock } = setup();
  const originalGet = api.getAttempt.bind(api);
  let serverContentTampered = true;

  api.getAttempt = async () => {
    const att = await originalGet();
    // Simulate authoritative GET returning altered content
    if (serverContentTampered && att.steps && att.steps.length > 0) {
      const step = { ...att.steps[0] };
      step.content_latex = "TEMPORARILY_ALTERED_ON_SERVER";
      att.steps = [step];
    }
    return att;
  };

  const mgr1 = new SequentialBatchManager(api, store, lock);
  const res = await mgr1.start("attempt", "b", approved(1));

  // 1. Manager pauses without reporting COMPLETE
  assert.equal(res.status, "PAUSED");
  assert.equal(res.journal?.message, "BATCH_SERVER_CONTENT_MISMATCH");

  // 2. Persisted journal MUST be valid schema, not corrupted
  assert.notEqual(store.saved, null);
  assert.equal(isValidBatchJournal(store.saved), true);

  // 3. New manager instance as after F5
  const mgr2 = new SequentialBatchManager(api, store, lock);

  // 4. Confirm journal loads successfully without throwing BATCH_JOURNAL_CORRUPT
  const resumeRes = await mgr2.resume("attempt");
  assert.equal(resumeRes.status, "PAUSED");
  assert.equal(resumeRes.journal.message, "BATCH_SERVER_CONTENT_MISMATCH");

  // 5. Verify batch remains safely paused and cannot be abandoned
  await assert.rejects(() => mgr2.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);

  // 6. Verify no new ADD_STEP is sent
  assert.equal(api.calls.length, 1);

  // 7. Simulate restored server content: reconciliation succeeds without creating duplicate steps
  serverContentTampered = false;
  const recovered = await mgr2.resume("attempt");
  assert.equal(recovered.status, "COMPLETE");
  assert.equal(api.calls.length, 1);
  assert.equal(api.attempt.steps?.length, 1);
});

test("ISSUE 2 regression: non-422 errors containing '422' or 'INVALID_DRAFT' in message must NOT allow abandonment", async () => {
  const { manager, api, store } = setup();

  // Case A: 500 error containing '422' in error message
  api.addStep = async () => {
    throw new Error("Internal database deadlock at block 422: retry later");
  };
  const res1 = await manager.start("attempt", "b1", approved(1));
  assert.equal(res1.status, "PAUSED");
  // Must NOT allow abandonment
  await assert.rejects(() => manager.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);

  // Case B: 500 error containing 'INVALID_DRAFT' in text message but HTTP status 500
  store.saved = null;
  api.calls = [];
  api.addStep = async () => {
    throw { status: 500, message: "Server crashed while evaluating INVALID_DRAFT rule" };
  };
  const res2 = await manager.start("attempt", "b2", approved(1));
  assert.equal(res2.status, "PAUSED");
  // Must NOT allow abandonment
  await assert.rejects(() => manager.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);

  // Case C: 409 error containing '422' in message
  store.saved = null;
  api.calls = [];
  api.addStep = async () => {
    throw { status: 409, message: "Concurrent edit conflict on line 422" };
  };
  const res3 = await manager.start("attempt", "b3", approved(1));
  assert.equal(res3.status, "PAUSED");
  // Must NOT allow abandonment
  await assert.rejects(() => manager.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);

  // Case D: HTTP 400 error containing '422' in Error.message (rejected state, but NOT a 422 validation rejection!)
  store.saved = null;
  api.calls = [];
  api.addStep = async () => {
    const err = new Error("Field id 422 is not supported in this schema");
    (err as any).status = 400;
    throw err;
  };
  const res4 = await manager.start("attempt", "b4", approved(1));
  assert.equal(res4.status, "PAUSED");
  // Must NOT allow abandonment merely because '422' substring is in error message
  await assert.rejects(() => manager.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);
});

test("COMPATIBILITY 1: real ApiResponseError with HTTP 422 and code HTTP_ERROR allows safe abandonment", async () => {
  const { manager, api } = setup();
  api.addStep = async () => {
    throw new ApiResponseError("Unprocessable entity in step draft", 422, "HTTP_ERROR", "validation");
  };
  const res = await manager.start("attempt", "b_422", approved(1));
  assert.equal(res.status, "PAUSED");

  // Definitive uncommitted validation rejection: abandonment must be allowed!
  const abandoned = await manager.abandonRejected("attempt");
  assert.equal(abandoned?.state, "ABANDONED");
});

test("COMPATIBILITY 2: HTTP 409 or 500 carrying code INVALID_DRAFT MUST NOT allow abandonment", async () => {
  const { manager, api, store } = setup();

  // Case A: HTTP 409 with code "INVALID_DRAFT"
  api.addStep = async () => {
    throw new ApiResponseError("Revision conflict occurred during draft evaluation", 409, "INVALID_DRAFT", "conflict");
  };
  const res409 = await manager.start("attempt", "b_409", approved(1));
  assert.equal(res409.status, "PAUSED");
  await assert.rejects(() => manager.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);

  // Case B: HTTP 500 with code "INVALID_DRAFT"
  store.saved = null;
  api.calls = [];
  api.addStep = async () => {
    throw new ApiResponseError("Internal server error in draft validation module", 500, "INVALID_DRAFT", "http");
  };
  const res500 = await manager.start("attempt", "b_500", approved(1));
  assert.equal(res500.status, "PAUSED");
  await assert.rejects(() => manager.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);
});

test("COMPATIBILITY 3: older journals lacking httpStatus fail closed unless errorCode is explicit HTTP_422", async () => {
  const { manager, store } = setup();

  // Older journal without httpStatus field, errorCode is "INVALID_DRAFT" (unverified status):
  store.saved = {
    schemaVersion: 1,
    batchId: "b_old",
    attemptId: "attempt",
    createdAt: Date.now(),
    nextRevision: 1,
    state: "PAUSED",
    message: "BATCH_SEND_INVALID_DRAFT",
    entries: [
      {
        draftId: "d-0",
        actionId: "a-0",
        content: { step_type: "EXPLANATION", content_latex: "x=0", explanation_text: null, artifact: null },
        state: "REJECTED",
        frozen: null,
        beforeStepIds: null,
        serverStepId: null,
        serverRevision: null,
        error: "Invalid draft syntax",
        errorCode: "INVALID_DRAFT",
        // httpStatus is missing (undefined)
      },
    ],
  };

  // Must fail closed because status was not verified as 422!
  await assert.rejects(() => manager.abandonRejected("attempt"), /BATCH_NOT_SAFE_TO_ABANDON/);

  // If older journal had explicit machine-code "HTTP_422":
  store.saved.entries[0].errorCode = "HTTP_422";
  const abandoned = await manager.abandonRejected("attempt");
  assert.equal(abandoned?.state, "ABANDONED");
});

test("GET failure before preparing next item pauses without sending it", async () => {
  const { manager, api, store } = setup();
  const get = api.getAttempt.bind(api);
  let calls = 0;
  api.getAttempt = async () => {
    calls++;
    if (calls === 3) throw new Error('GET_TEMPORARILY_OFFLINE');
    return get();
  };
  assert.equal((await manager.start("attempt", "b", approved(2))).status, "PAUSED");
  assert.equal(api.calls.length, 1);
  assert.equal(store.saved?.entries[1].frozen, null);
  assert.match(store.saved?.message ?? '', /GET_TEMPORARILY_OFFLINE/);
});

// ---------------------------------------------------------------------------
// Adversarial Hardening Tests (PR3-B)
// ---------------------------------------------------------------------------

test("T6: journal write failure after server commit preserves COMMITTED state", async () => {
  const { manager, api, store } = setup();
  // Write 1 is initial plan (PREPARED).
  // Write 2 is step 0 SENDING.
  // Write 3 is step 0 COMMITTED save.
  store.failOnWrite = 3;
  const out = await manager.start("attempt", "b", approved(2));
  assert.equal(out.status, "PAUSED");
  // Step 0 committed on server
  assert.equal(api.attempt.steps?.length, 1);
  // Entry in journal is COMMITTED, not misattributed to UNKNOWN
  assert.equal(out.journal?.entries[0].state, "COMMITTED");
  assert.equal(out.journal?.entries[0].serverStepId, "step-1");
  // Healing: reset write failure, resume() successfully reconciles and finishes batch
  store.failOnWrite = null;
  store.saved = out.journal;
  const resumed = await manager.resume("attempt");
  assert.equal(resumed.status, "COMPLETE");
  assert.equal(api.attempt.steps?.length, 2);
});

test("T13: two distinct attempts are strictly isolated without cross-attempt interference", async () => {
  const store = new Store();
  const lock = new Lock();
  const api1 = new Api();
  api1.attempt = { id: "att-1", question_id: null, status: "DRAFT", current_revision: 1, created_at: "2026-10-31", steps: [] };
  const api2 = new Api();
  api2.attempt = { id: "att-2", question_id: null, status: "DRAFT", current_revision: 1, created_at: "2026-10-31", steps: [] };

  class MultiStore implements BatchJournalStore {
    journals = new Map<string, BatchJournal>();
    async load(id: string): Promise<BatchJournal | null> {
      const j = this.journals.get(id);
      return j ? clone(j) : null;
    }
    async save(j: BatchJournal): Promise<void> {
      this.journals.set(j.attemptId, clone(j));
    }
  }
  const multiStore = new MultiStore();

  const mgr1 = new SequentialBatchManager(api1, multiStore, lock);
  const mgr2 = new SequentialBatchManager(api2, multiStore, lock);

  const res1 = await mgr1.start("att-1", "b1", approved(2));
  const res2 = await mgr2.start("att-2", "b2", approved(3));

  assert.equal(res1.status, "COMPLETE");
  assert.equal(res2.status, "COMPLETE");
  assert.equal(api1.attempt.steps?.length, 2);
  assert.equal(api2.attempt.steps?.length, 3);
});

test("T14: external mutation of request object in api.addStep does not corrupt frozen journal", async () => {
  const { manager, api, store } = setup();
  const original = api.addStep.bind(api);
  api.addStep = async (id, req) => {
    // Malicious or buggy transport mutating the passed request in-place
    req.content_latex = "CORRUPTED_IN_FLIGHT";
    return original(id, req);
  };
  const res = await manager.start("attempt", "b", approved(1));
  // Content mismatch prevents falsely reporting COMPLETE
  assert.equal(res.status, "PAUSED");
  assert.equal(res.journal?.message, "BATCH_SERVER_CONTENT_MISMATCH");
  // Frozen request in journal remained untouched
  assert.equal(store.saved?.entries[0].frozen?.content_latex, "x=0");
  assert.equal(store.saved?.entries[0].state, "UNKNOWN");
  assert.equal(store.saved?.entries[0].errorCode, "CONTENT_MISMATCH");
});

test("T14_B: whitespace trimming normalization by backend contract matches and completes", async () => {
  const { manager, api } = setup();
  const original = api.addStep.bind(api);
  api.addStep = async (id, req) => {
    const res = await original(id, req);
    // Pydantic str_strip_whitespace behavior
    const step = res.steps![res.steps!.length - 1];
    step.content_latex = "  " + (req.content_latex ?? "") + "  ";
    step.content_latex = step.content_latex.trim();
    return res;
  };
  const res = await manager.start("attempt", "b", approved(1));
  assert.equal(res.status, "COMPLETE");
});

test("T14_C: final reconciliation detects content tampering on server and halts", async () => {
  const { manager, api, store } = setup();
  const originalGet = api.getAttempt.bind(api);
  let getCalls = 0;
  api.getAttempt = async () => {
    getCalls++;
    const att = await originalGet();
    // Tamper with step content during final reconciliation GET
    if (getCalls >= 3 && att.steps && att.steps.length > 0) {
      att.steps[0].content_latex = "TAMPERED_AT_REST";
    }
    return att;
  };
  const res = await manager.start("attempt", "b", approved(1));
  assert.equal(res.status, "PAUSED");
  assert.equal(store.saved?.message, "BATCH_SERVER_CONTENT_MISMATCH");
});

test("schema validation: corrupted journal data fails closed with BATCH_JOURNAL_CORRUPT or not found", async () => {
  const { manager, store } = setup();
  store.saved = {
    schemaVersion: 1,
    batchId: "corrupt",
    attemptId: "attempt",
    createdAt: Date.now(),
    nextRevision: 1,
    state: "INVALID_STATE" as unknown as "PREPARED",
    entries: "NOT_AN_ARRAY" as unknown as [],
    message: null,
  };
  await assert.rejects(() => manager.resume("attempt"), /BATCH_JOURNAL_CORRUPT/);
  store.saved = null;
  await assert.rejects(() => manager.resume("attempt"), /BATCH_JOURNAL_NOT_FOUND/);
});

test("schema validation: isValidBatchJournal rejects invalid, unsupported, and contradictory records", () => {
  const validJournal: BatchJournal = {
    schemaVersion: 1,
    batchId: "b-valid",
    attemptId: "att-valid",
    createdAt: 1730332800000,
    nextRevision: 1,
    state: "PREPARED",
    message: null,
    entries: [
      {
        draftId: "d-1",
        actionId: "a-1",
        content: {
          step_type: "EXPLANATION",
          content_latex: "x=1",
          explanation_text: null,
          artifact: null,
        },
        state: "QUEUED",
        frozen: null,
        beforeStepIds: null,
        serverStepId: null,
        serverRevision: null,
        error: null,
        errorCode: null,
      },
    ],
  };

  assert.equal(isValidBatchJournal(validJournal), true);
  assert.equal(validateBatchJournal(validJournal), validJournal);

  // Rejects null, primitives, arrays
  assert.equal(isValidBatchJournal(null), false);
  assert.equal(isValidBatchJournal(undefined), false);
  assert.equal(isValidBatchJournal("not an object"), false);
  assert.equal(isValidBatchJournal([]), false);

  // Rejects unsupported schema versions
  assert.equal(isValidBatchJournal({ ...validJournal, schemaVersion: 2 }), false);
  assert.equal(isValidBatchJournal({ ...validJournal, schemaVersion: 0 }), false);
  assert.equal(isValidBatchJournal({ ...validJournal, schemaVersion: "1" }), false);

  // Rejects missing or blank attemptId/batchId
  assert.equal(isValidBatchJournal({ ...validJournal, attemptId: "" }), false);
  assert.equal(isValidBatchJournal({ ...validJournal, attemptId: "   " }), false);
  assert.equal(isValidBatchJournal({ ...validJournal, batchId: "" }), false);

  // Rejects invalid createdAt or nextRevision
  assert.equal(isValidBatchJournal({ ...validJournal, createdAt: -1 }), false);
  assert.equal(isValidBatchJournal({ ...validJournal, createdAt: NaN }), false);
  assert.equal(isValidBatchJournal({ ...validJournal, nextRevision: -1 }), false);
  assert.equal(isValidBatchJournal({ ...validJournal, nextRevision: 1.5 }), false);

  // Rejects invalid states
  assert.equal(isValidBatchJournal({ ...validJournal, state: "UNKNOWN_STATE" as any }), false);

  // Rejects duplicate actionId or draftId across entries
  const duplicateAction: BatchJournal = {
    ...validJournal,
    entries: [
      validJournal.entries[0],
      { ...validJournal.entries[0], draftId: "d-2" },
    ],
  };
  assert.equal(isValidBatchJournal(duplicateAction), false);

  const duplicateDraft: BatchJournal = {
    ...validJournal,
    entries: [
      validJournal.entries[0],
      { ...validJournal.entries[0], actionId: "a-2" },
    ],
  };
  assert.equal(isValidBatchJournal(duplicateDraft), false);

  // Rejects duplicate serverStepIds across entries
  const duplicateServerStepId: BatchJournal = {
    ...validJournal,
    entries: [
      {
        ...validJournal.entries[0],
        state: "COMMITTED",
        frozen: {
          expected_attempt_revision: 1,
          client_action_id: "a-1",
          step_type: "EXPLANATION",
          content_latex: "x=1",
          explanation_text: null,
          artifact: null,
        },
        beforeStepIds: [],
        serverStepId: "step-duplicate",
        serverRevision: 2,
      },
      {
        ...validJournal.entries[0],
        draftId: "d-2",
        actionId: "a-2",
        state: "COMMITTED",
        frozen: {
          expected_attempt_revision: 2,
          client_action_id: "a-2",
          step_type: "EXPLANATION",
          content_latex: "x=1",
          explanation_text: null,
          artifact: null,
        },
        beforeStepIds: ["step-duplicate"],
        serverStepId: "step-duplicate", // DUPLICATE serverStepId!
        serverRevision: 3,
      },
    ],
  };
  assert.equal(isValidBatchJournal(duplicateServerStepId), false);

  // Rejects contradictory QUEUED entry with frozen non-null or serverStepId non-null
  const badQueued: BatchJournal = {
    ...validJournal,
    entries: [
      {
        ...validJournal.entries[0],
        frozen: {
          expected_attempt_revision: 1,
          client_action_id: "a-1",
          step_type: "EXPLANATION",
          content_latex: "x=1",
          explanation_text: null,
          artifact: null,
        },
      },
    ],
  };
  assert.equal(isValidBatchJournal(badQueued), false);

  // Rejects contradictory COMMITTED entry without serverStepId
  const badCommitted: BatchJournal = {
    ...validJournal,
    entries: [
      {
        ...validJournal.entries[0],
        state: "COMMITTED",
        frozen: {
          expected_attempt_revision: 1,
          client_action_id: "a-1",
          step_type: "EXPLANATION",
          content_latex: "x=1",
          explanation_text: null,
          artifact: null,
        },
        beforeStepIds: [],
        serverStepId: null,
        serverRevision: 2,
      },
    ],
  };
  assert.equal(isValidBatchJournal(badCommitted), false);

  // Rejects contradictory frozen request with mismatched client_action_id
  const mismatchedAction: BatchJournal = {
    ...validJournal,
    entries: [
      {
        ...validJournal.entries[0],
        state: "SENDING",
        beforeStepIds: [],
        frozen: {
          expected_attempt_revision: 1,
          client_action_id: "DIFFERENT_ACTION_ID",
          step_type: "EXPLANATION",
          content_latex: "x=1",
          explanation_text: null,
          artifact: null,
        },
      },
    ],
  };
  assert.equal(isValidBatchJournal(mismatchedAction), false);

  // Rejects contradictory frozen request with mismatched content
  const mismatchedContent: BatchJournal = {
    ...validJournal,
    entries: [
      {
        ...validJournal.entries[0],
        state: "SENDING",
        beforeStepIds: [],
        frozen: {
          expected_attempt_revision: 1,
          client_action_id: "a-1",
          step_type: "EXPLANATION",
          content_latex: "TAMPERED_LATEX",
          explanation_text: null,
          artifact: null,
        },
      },
    ],
  };
  assert.equal(isValidBatchJournal(mismatchedContent), false);

  // Rejects COMPLETE journal when an entry is not COMMITTED
  const badComplete: BatchJournal = {
    ...validJournal,
    state: "COMPLETE",
    entries: [validJournal.entries[0]], // still QUEUED
  };
  assert.equal(isValidBatchJournal(badComplete), false);

  // validateBatchJournal throws BATCH_JOURNAL_CORRUPT
  assert.throws(() => validateBatchJournal(badComplete), /BATCH_JOURNAL_CORRUPT/);
});

test("T6_B: realistic post-commit disk crash preserves SENDING on disk; resume idempotently recovers", async () => {
  const { api, store, lock } = setup();
  // Write 1: initial plan (PREPARED)
  // Write 2: step 0 SENDING (frozen persisted)
  // Write 3: step 0 COMMITTED -> FAILS!
  store.failOnWrite = 3;

  const mgr1 = new SequentialBatchManager(api, store, lock);
  const out = await mgr1.start("attempt", "batch-crash", approved(2));

  // Memory result indicates PAUSED due to persistence failure after commit
  assert.equal(out.status, "PAUSED");
  assert.equal(out.journal?.state, "PAUSED");
  assert.equal(out.journal?.message, "BATCH_PERSISTENCE_FAILED_AFTER_COMMIT");
  // Step 0 was committed on the server
  assert.equal(api.attempt.steps?.length, 1);

  // CRUCIAL: On disk, Write 3 threw, so store.saved STILL has the Write 2 state (step 0 SENDING with frozen request)!
  assert.equal(store.saved?.entries[0].state, "SENDING");
  assert.notEqual(store.saved?.entries[0].frozen, null);
  assert.equal(store.saved?.entries[0].serverStepId, null);

  // Simulate tab refresh / process restart: New manager instance, disk failure resolved
  store.failOnWrite = null;
  const mgr2 = new SequentialBatchManager(api, store, lock);

  // Calling resume() reads step 0 in SENDING, replays the exact frozen request to api.addStep
  const resumed = await mgr2.resume("attempt");
  assert.equal(resumed.status, "COMPLETE");

  // Server history detected the replayed client_action_id and returned the idempotent cached step:
  // EXACTLY 2 steps exist on server (no duplicates created!)
  assert.equal(api.attempt.steps?.length, 2);
  assert.deepEqual(api.calls.map((c) => c.client_action_id), [
    "action-0", // initial attempt
    "action-0", // idempotent replay on recovery
    "action-1", // second step
  ]);
  // Both steps successfully committed in final journal
  assert.equal(store.saved?.state, "COMPLETE");
  assert.equal(store.saved?.entries.every((e) => e.state === "COMMITTED"), true);
});

test("T6_C: persistence failure on final COMPLETE pauses; subsequent resume successfully completes", async () => {
  const { api, store, lock } = setup();
  // Approved 1 step:
  // Write 1: initial PREPARED
  // Write 2: step 0 SENDING
  // Write 3: step 0 COMMITTED
  // Write 4: batch COMPLETE -> FAILS!
  store.failOnWrite = 4;

  const mgr = new SequentialBatchManager(api, store, lock);
  const out = await mgr.start("attempt", "batch-complete-fail", approved(1));

  assert.equal(out.status, "PAUSED");
  assert.equal(out.journal?.state, "PAUSED");
  assert.equal(out.journal?.message, "BATCH_PERSISTENCE_FAILED_ON_COMPLETE");
  assert.equal(api.attempt.steps?.length, 1);

  // Resolve storage error and resume
  store.failOnWrite = null;
  const resumed = await mgr.resume("attempt");
  assert.equal(resumed.status, "COMPLETE");
  assert.equal(store.saved?.state, "COMPLETE");
});

test("IndexedDbBatchJournal and BrowserBatchLock fail closed when browser APIs are unavailable", async () => {
  const { IndexedDbBatchJournal, BrowserBatchLock } = await import("../src/features/math-workspace/utils/batch-journal.js");
  const store = new IndexedDbBatchJournal();
  await assert.rejects(() => store.load("att-1"), /BATCH_INDEXEDDB_UNAVAILABLE/);
  await assert.rejects(() => store.save({} as any), /BATCH_INDEXEDDB_UNAVAILABLE/);

  const lock = new BrowserBatchLock();
  const lockResult = await lock.runExclusive("att-1", async () => "executed");
  assert.equal(lockResult, null);
});
