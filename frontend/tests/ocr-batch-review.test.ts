import test from "node:test";
import assert from "node:assert/strict";
import type { SolutionAttemptRead, StepMutationRequest } from "../src/lib/api/contracts.js";
import {
  createBatchApi,
  buildApprovedIntents,
  canStartBatchReview,
  syncRowsFromJournal,
  type ReviewRowLike,
} from "../src/features/math-workspace/utils/ocr-batch-adapter.js";
import {
  SequentialBatchManager,
  type BatchApi,
  type BatchJournal,
  type BatchJournalStore,
  type BatchLock,
} from "../src/features/math-workspace/utils/batch-manager.js";
import {
  createOcrReviewDraft,
  selectOcrDraftKind,
  editOcrReviewDraft,
  approveOcrDraft,
  canApproveOcrDraft,
  applyOcrToDraft,
} from "../src/features/math-workspace/utils/ocr-review-draft.js";

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

class MemoryStore implements BatchJournalStore {
  saved: BatchJournal | null = null;
  async load(): Promise<BatchJournal | null> {
    return this.saved ? clone(this.saved) : null;
  }
  async save(j: BatchJournal): Promise<void> {
    this.saved = clone(j);
  }
}

class FakeLock implements BatchLock {
  async runExclusive<T>(_id: string, work: () => Promise<T>): Promise<T | null> {
    return work();
  }
}

function makeRow(id: string, status: string, latex = `x=${id}`, kind: any = "ROOT_FINDING"): ReviewRowLike {
  let draft = createOcrReviewDraft({ localId: id, pageIndex: 0, regionIds: [id], strokeIds: [id] });
  draft = editOcrReviewDraft(draft, { contentLatex: latex });
  draft = selectOcrDraftKind(draft, kind);
  if (status === "approved") {
    draft = approveOcrDraft(draft);
  }
  return {
    draft,
    actionId: `action-${id}`,
    status,
    serverStepId: null,
    error: null,
  };
}

test("buildApprovedIntents converts approved rows and excludes skipped/saved rows", () => {
  const rows: ReviewRowLike[] = [
    makeRow("1", "saved"),
    makeRow("2", "approved", "y'=2x", "DERIVATIVE_CALCULATION"),
    makeRow("3", "skipped"),
    makeRow("4", "approved", "x=0", "ROOT_FINDING"),
  ];

  const intents = buildApprovedIntents(rows);
  assert.equal(intents.length, 2);
  assert.equal(intents[0].draftId, "2");
  assert.equal(intents[0].actionId, "action-2");
  assert.equal(intents[0].stepType, "DERIVATIVE_CALCULATION");
  assert.equal(intents[0].contentLatex, "y'=2x");

  assert.equal(intents[1].draftId, "4");
  assert.equal(intents[1].actionId, "action-4");
  assert.equal(intents[1].stepType, "ROOT_FINDING");
});

test("canStartBatchReview enforces sequence order and non-empty batch", () => {
  // Empty
  assert.equal(canStartBatchReview([]).canStart, false);

  // Unreviewed row before approved row
  const rowsWithGap: ReviewRowLike[] = [
    makeRow("1", "ready"),
    makeRow("2", "approved"),
  ];
  const gapCheck = canStartBatchReview(rowsWithGap);
  assert.equal(gapCheck.canStart, false);
  assert.match(gapCheck.reason ?? "", /Vùng 1 chưa được duyệt/);

  // Valid sequential: row 1 saved, row 2 approved, row 3 skipped, row 4 approved
  const validRows: ReviewRowLike[] = [
    makeRow("1", "saved"),
    makeRow("2", "approved"),
    makeRow("3", "skipped"),
    makeRow("4", "approved"),
    makeRow("5", "ready"), // later row not yet approved is fine
  ];
  assert.equal(canStartBatchReview(validRows).canStart, true);
});

test("syncRowsFromJournal updates COMMITTED steps to saved and sets serverStepId", () => {
  const rows: ReviewRowLike[] = [
    makeRow("1", "approved"),
    makeRow("2", "approved"),
  ];

  const journal: BatchJournal = {
    schemaVersion: 1,
    batchId: "b1",
    attemptId: "att-1",
    createdAt: Date.now(),
    nextRevision: 2,
    state: "PAUSED",
    message: null,
    entries: [
      {
        draftId: "1",
        actionId: "action-1",
        content: { step_type: "ROOT_FINDING", content_latex: "x=1", explanation_text: null, artifact: null },
        state: "COMMITTED",
        frozen: { expected_attempt_revision: 1, client_action_id: "action-1", step_type: "ROOT_FINDING", content_latex: "x=1", explanation_text: null, artifact: null },
        beforeStepIds: [],
        serverStepId: "step-server-1",
        serverRevision: 2,
        error: null,
      },
      {
        draftId: "2",
        actionId: "action-2",
        content: { step_type: "ROOT_FINDING", content_latex: "x=2", explanation_text: null, artifact: null },
        state: "REJECTED",
        frozen: { expected_attempt_revision: 2, client_action_id: "action-2", step_type: "ROOT_FINDING", content_latex: "x=2", explanation_text: null, artifact: null },
        beforeStepIds: ["step-server-1"],
        serverStepId: null,
        serverRevision: null,
        error: "Validation error",
        errorCode: "INVALID_DRAFT",
      },
    ],
  };

  const synced = syncRowsFromJournal(rows, journal);
  assert.equal(synced[0].status, "saved");
  assert.equal(synced[0].serverStepId, "step-server-1");

  assert.equal(synced[1].status, "manual");
  assert.equal(synced[1].error, "Validation error");
});

test("createBatchApi delegates calls to apiClient", async () => {
  let getAttemptCalled = false;
  let createStepCalled = false;

  const mockClient: any = {
    async getMathAttempt(token: string, id: string) {
      assert.equal(token, "test-token");
      assert.equal(id, "att-1");
      getAttemptCalled = true;
      return { id, status: "DRAFT", current_revision: 1, steps: [] };
    },
    async createMathStep(token: string, id: string, req: StepMutationRequest) {
      assert.equal(token, "test-token");
      assert.equal(id, "att-1");
      assert.equal(req.client_action_id, "action-test");
      createStepCalled = true;
      return { id, status: "IN_PROGRESS", current_revision: 2, steps: [{ id: "s1", step_index: 1, step_type: req.step_type, content_latex: req.content_latex, explanation_text: null, step_revision_number: 1 }] };
    },
  };

  const batchApi = createBatchApi(mockClient, "test-token");
  await batchApi.getAttempt("att-1");
  assert.equal(getAttemptCalled, true);

  await batchApi.addStep("att-1", {
    expected_attempt_revision: 1,
    client_action_id: "action-test",
    step_type: "EXPLANATION",
    content_latex: "x=1",
    explanation_text: null,
  });
  assert.equal(createStepCalled, true);
});

test("End-to-end integration: sequential batch engine executes approved intents via adapter", async () => {
  const store = new MemoryStore();
  const lock = new FakeLock();

  let revision = 1;
  const steps: any[] = [];
  const fakeApi: BatchApi = {
    async getAttempt(id: string) {
      return { id, question_id: null, created_at: "2026-10-31", status: "DRAFT" as const, current_revision: revision, steps: clone(steps) };
    },
    async addStep(id: string, req: StepMutationRequest) {
      assert.equal(req.expected_attempt_revision, revision);
      revision++;
      const step = {
        id: `step-${steps.length + 1}`,
        step_index: steps.length + 1,
        step_type: req.step_type,
        content_latex: req.content_latex ?? null,
        explanation_text: req.explanation_text ?? null,
        step_revision_number: 1,
      };
      steps.push(step);
      return { id, question_id: null, created_at: "2026-10-31", status: "IN_PROGRESS" as const, current_revision: revision, steps: clone(steps) };
    },
  };

  const rows: ReviewRowLike[] = [
    makeRow("r1", "approved", "y'=3x^2-6x", "DERIVATIVE_CALCULATION"),
    makeRow("r2", "approved", "3x^2-6x=0", "ROOT_FINDING"),
  ];

  const intents = buildApprovedIntents(rows);
  const manager = new SequentialBatchManager(fakeApi, store, lock);
  const result = await manager.start("attempt-e2e", "batch-1", intents);

  assert.equal(result.status, "COMPLETE");
  assert.equal(steps.length, 2);

  const synced = syncRowsFromJournal(rows, result.journal);
  assert.equal(synced.every((r) => r.status === "saved"), true);
  assert.equal(synced[0].serverStepId, "step-1");
  assert.equal(synced[1].serverStepId, "step-2");
});

test("ADVERSARIAL 1: Batch 5 bước thành công với đầy đủ xâu chuỗi revision", async () => {
  const store = new MemoryStore();
  const lock = new FakeLock();
  let revision = 1;
  const steps: any[] = [];
  const api: BatchApi = {
    async getAttempt(id) {
      return { id, question_id: null, created_at: "2026-10-31", status: "DRAFT", current_revision: revision, steps: clone(steps) };
    },
    async addStep(id, req) {
      assert.equal(req.expected_attempt_revision, revision);
      revision++;
      steps.push({ id: `step-${steps.length + 1}`, step_index: steps.length + 1, step_type: req.step_type, content_latex: req.content_latex ?? null, explanation_text: req.explanation_text ?? null, step_revision_number: 1 });
      return { id, question_id: null, created_at: "2026-10-31", status: "IN_PROGRESS", current_revision: revision, steps: clone(steps) };
    },
  };

  const rows = [
    makeRow("1", "approved", "D=R", "ASSUMPTION"),
    makeRow("2", "approved", "y'=3x^2-6x", "DERIVATIVE_CALCULATION"),
    makeRow("3", "approved", "3x^2-6x=0", "ROOT_FINDING"),
    makeRow("4", "manual", "", "VARIATION_TABLE"),
    makeRow("5", "approved", "Ham so dong bien", "CONCLUSION"),
  ];
  rows[3].draft = editOcrReviewDraft(rows[3].draft, { explanationText: "x | -inf 0 2 +inf" });
  rows[3].draft = approveOcrDraft(rows[3].draft);
  rows[3].status = "approved";

  const intents = buildApprovedIntents(rows);
  assert.equal(intents.length, 5);
  const manager = new SequentialBatchManager(api, store, lock);
  const res = await manager.start("att-5", "b-5", intents);
  assert.equal(res.status, "COMPLETE");
  assert.equal(steps.length, 5);
  assert.equal(revision, 6);
});

test("ADVERSARIAL 2: Một bước ABSTAIN chưa chọn loại -> không thể duyệt và không thể lưu", () => {
  let abstainDraft = createOcrReviewDraft({ localId: "abs", pageIndex: 0, regionIds: ["abs"], strokeIds: ["abs"] });
  abstainDraft = editOcrReviewDraft(abstainDraft, { contentLatex: "x = 2" }); // ambiguous -> ABSTAIN
  assert.equal(abstainDraft.classification.status, "ABSTAIN");
  assert.equal(abstainDraft.selectedStepKind, null);
  assert.equal(canApproveOcrDraft(abstainDraft), false);

  const row: ReviewRowLike = {
    draft: abstainDraft,
    actionId: "act-abs",
    status: "manual",
    serverStepId: null,
    error: null,
  };

  // canStartBatchReview returns false because row is not approved/skipped/saved
  const check = canStartBatchReview([row]);
  assert.equal(check.canStart, false);
  assert.equal(buildApprovedIntents([row]).length, 0);
});

test("ADVERSARIAL 3: Một bước SKIPPED -> không được đưa vào batch intent và không gửi lên server", () => {
  const rows = [
    makeRow("1", "approved", "y'=2x", "DERIVATIVE_CALCULATION"),
    makeRow("2", "skipped", "do-not-send"),
    makeRow("3", "approved", "x=0", "ROOT_FINDING"),
  ];
  const intents = buildApprovedIntents(rows);
  assert.equal(intents.length, 2);
  assert.equal(intents.some((i) => i.draftId === "2"), false);
});

test("ADVERSARIAL 4 & 5: Mất response sau server commit và F5 giữa batch -> retry không duplicate bước", async () => {
  const store = new MemoryStore();
  const lock = new FakeLock();
  let revision = 1;
  const steps: any[] = [];
  const history = new Map<string, any>();
  let failAfterCommit = true;

  const api: BatchApi = {
    async getAttempt(id) {
      return { id, question_id: null, created_at: "2026-10-31", status: "DRAFT", current_revision: revision, steps: clone(steps) };
    },
    async addStep(id, req) {
      const prior = history.get(req.client_action_id);
      if (prior) return clone(prior);
      assert.equal(req.expected_attempt_revision, revision);
      revision++;
      const step = { id: `step-${steps.length + 1}`, step_index: steps.length + 1, step_type: req.step_type, content_latex: req.content_latex, explanation_text: null, step_revision_number: 1 };
      steps.push(step);
      const res = { id, question_id: null, created_at: "2026-10-31", status: "IN_PROGRESS", current_revision: revision, steps: clone(steps) };
      history.set(req.client_action_id, clone(res));
      if (failAfterCommit && req.client_action_id === "action-2") {
        throw new Error("Network lost after commit on step 2");
      }
      return res;
    },
  };

  const rows = [
    makeRow("1", "approved", "y'=2x", "DERIVATIVE_CALCULATION"),
    makeRow("2", "approved", "2x=0", "ROOT_FINDING"),
    makeRow("3", "approved", "x=0", "ROOT_FINDING"),
  ];

  const mgr1 = new SequentialBatchManager(api, store, lock);
  const out1 = await mgr1.start("att-f5", "b-f5", buildApprovedIntents(rows));
  assert.equal(out1.status, "PAUSED");
  // Step 2 was committed on server before network drop
  assert.equal(steps.length, 2);

  // F5 Reload: new manager instance reading from store
  failAfterCommit = false;
  const mgr2 = new SequentialBatchManager(api, store, lock);
  const out2 = await mgr2.resume("att-f5");
  assert.equal(out2.status, "COMPLETE");
  // Zero duplicate steps: EXACTLY 3 steps on server!
  assert.equal(steps.length, 3);
});

test("ADVERSARIAL 6: HTTP 422 ở bước thứ 3 -> dừng và bảo toàn 2 bước trước", async () => {
  const store = new MemoryStore();
  const lock = new FakeLock();
  let revision = 1;
  const steps: any[] = [];
  const api: BatchApi = {
    async getAttempt(id) {
      return { id, question_id: null, created_at: "2026-10-31", status: "DRAFT", current_revision: revision, steps: clone(steps) };
    },
    async addStep(id, req) {
      if (req.client_action_id === "action-3") {
        throw { status: 422, code: "INVALID_DRAFT" };
      }
      revision++;
      steps.push({ id: `step-${steps.length + 1}`, step_index: steps.length + 1, step_type: req.step_type, content_latex: req.content_latex, explanation_text: null, step_revision_number: 1 });
      return { id, question_id: null, created_at: "2026-10-31", status: "IN_PROGRESS", current_revision: revision, steps: clone(steps) };
    },
  };

  const rows = [
    makeRow("1", "approved", "y'=2x", "DERIVATIVE_CALCULATION"),
    makeRow("2", "approved", "2x=0", "ROOT_FINDING"),
    makeRow("3", "approved", "invalid-syntax", "ROOT_FINDING"),
  ];

  const mgr = new SequentialBatchManager(api, store, lock);
  const res = await mgr.start("att-422", "b-422", buildApprovedIntents(rows));
  assert.equal(res.status, "PAUSED");
  assert.equal(steps.length, 2); // Steps 1 and 2 preserved

  // Abandon uncommitted step 3
  const abandoned = await mgr.abandonRejected("att-422");
  assert.equal(abandoned?.state, "ABANDONED");
  // Steps 1 and 2 remain on server intact
  assert.equal(steps.length, 2);
});

test("ADVERSARIAL 7: HTTP 409 revision conflict dừng ngay mà không gửi bước tiếp theo", async () => {
  const store = new MemoryStore();
  const lock = new FakeLock();
  let calls = 0;
  const api: BatchApi = {
    async getAttempt(id) {
      return { id, question_id: null, created_at: "2026-10-31", status: "DRAFT", current_revision: 1, steps: [] };
    },
    async addStep() {
      calls++;
      throw { status: 409, code: "SOLUTION_REVISION_CONFLICT" };
    },
  };

  const rows = [
    makeRow("1", "approved"),
    makeRow("2", "approved"),
  ];

  const mgr = new SequentialBatchManager(api, store, lock);
  const res = await mgr.start("att-409", "b-409", buildApprovedIntents(rows));
  assert.equal(res.status, "PAUSED");
  assert.equal(calls, 1); // Step 2 was NOT sent!
});

test("ADVERSARIAL 8: CONTENT_MISMATCH fail-closed và cấm tuyệt đối abandon", async () => {
  const store = new MemoryStore();
  const lock = new FakeLock();
  const api: BatchApi = {
    async getAttempt(id) {
      return { id, question_id: null, created_at: "2026-10-31", status: "DRAFT", current_revision: 1, steps: [] };
    },
    async addStep(id, req) {
      // Server stores altered content
      return {
        id,
        question_id: null,
        created_at: "2026-10-31",
        status: "IN_PROGRESS",
        current_revision: 2,
        steps: [{ id: "step-1", step_index: 1, step_type: req.step_type, content_latex: "SERVER_ALTERED_CONTENT", explanation_text: null, step_revision_number: 1 }],
      };
    },
  };

  const rows = [makeRow("1", "approved", "x=0")];
  const mgr = new SequentialBatchManager(api, store, lock);
  const res = await mgr.start("att-mismatch", "b-mismatch", buildApprovedIntents(rows));
  assert.equal(res.status, "PAUSED");
  assert.equal(store.saved?.message, "BATCH_SERVER_CONTENT_MISMATCH");

  // Invariant: MUST NOT be abandonable!
  await assert.rejects(() => mgr.abandonRejected("att-mismatch"), /BATCH_NOT_SAFE_TO_ABANDON/);
});

test("ADVERSARIAL 9: Hai tab cùng thao tác -> trả về LOCKED và không gửi mutation", async () => {
  const store = new MemoryStore();
  const busyLock: BatchLock = {
    async runExclusive() { return null; },
  };
  let addStepCalled = false;
  const api: BatchApi = {
    async getAttempt(id) { return { id, question_id: null, created_at: "2026-10-31", status: "DRAFT", current_revision: 1, steps: [] }; },
    async addStep() { addStepCalled = true; throw new Error("Should not be called"); },
  };

  const mgr = new SequentialBatchManager(api, store, busyLock);
  const res = await mgr.start("att-lock", "b-lock", buildApprovedIntents([makeRow("1", "approved")]));
  assert.equal(res.status, "LOCKED");
  assert.equal(addStepCalled, false);
});

test("ADVERSARIAL 10: IndexedDbBatchJournal throws BATCH_INDEXEDDB_UNAVAILABLE in non-browser environment", async () => {
  const { IndexedDbBatchJournal } = await import("../src/features/math-workspace/utils/batch-journal.js");
  const store = new IndexedDbBatchJournal();
  await assert.rejects(() => store.load("att-unavail"), /BATCH_INDEXEDDB_UNAVAILABLE/);
});

test("ADVERSARIAL 11: Đổi attempt khi còn pending batch -> ném BATCH_PENDING_RECOVERY_REQUIRED", async () => {
  const store = new MemoryStore();
  const lock = new FakeLock();
  const api: BatchApi = {
    async getAttempt(id) { return { id, question_id: null, created_at: "2026-10-31", status: "DRAFT", current_revision: 1, steps: [] }; },
    async addStep() { throw new Error("Offline"); },
  };

  const mgr = new SequentialBatchManager(api, store, lock);
  await mgr.start("same-att", "b1", buildApprovedIntents([makeRow("1", "approved")]));
  // A second batch on the same unfinished attempt must fail
  await assert.rejects(() => mgr.start("same-att", "b2", buildApprovedIntents([makeRow("2", "approved")])), /BATCH_PENDING_RECOVERY_REQUIRED/);
});

test("ADVERSARIAL 12: Không ghi đè công thức và loại bước do học sinh sửa thủ công", () => {
  let draft = createOcrReviewDraft({ localId: "d", pageIndex: 0, regionIds: ["d"], strokeIds: ["d"] });
  draft = applyOcrToDraft(draft, "y'=3x^2-6x");
  assert.equal(draft.selectedStepKind, "DERIVATIVE_CALCULATION");

  // Student manually edits formula and changes StepKind
  draft = editOcrReviewDraft(draft, { contentLatex: "y'=3x^2+6x" });
  draft = selectOcrDraftKind(draft, "CUSTOM");

  // Subsequent OCR retry arrives with new raw recognition
  const retryDraft = applyOcrToDraft(draft, "x=0");
  assert.equal(retryDraft.contentLatex, "y'=3x^2+6x"); // Preserved!
  assert.equal(retryDraft.rawOcrLatex, "x=0");
  assert.equal(retryDraft.selectedStepKind, "CUSTOM"); // Preserved!
  assert.equal(retryDraft.stepKindSource, "MANUAL");
});

