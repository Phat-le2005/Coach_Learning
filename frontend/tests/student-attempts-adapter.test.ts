import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPaginationViewModel,
  filterAndSortAttempts,
  getAttemptStatusMeta,
  parseAttemptsPageParam,
  parseAttemptsStatusParam,
  selectContinueLearningAttempts,
  toAttemptCardViewModel,
  toStudentAttemptsViewModel,
} from "../src/features/student-attempts/adapter.js";
import { createApiClient } from "../src/lib/api/client.js";
import type { SolutionAttemptRead } from "../src/lib/api/contracts.js";

test("getAttemptStatusMeta localizes all backend SolutionAttemptStatus values in Vietnamese", () => {
  assert.deepEqual(getAttemptStatusMeta("DRAFT"), {
    code: "DRAFT",
    label: "Bản nháp",
    tone: "draft",
    actionLabel: "Mở bản nháp",
    isResumable: true,
  });

  assert.deepEqual(getAttemptStatusMeta("IN_PROGRESS"), {
    code: "IN_PROGRESS",
    label: "Đang thực hiện",
    tone: "inProgress",
    actionLabel: "Tiếp tục làm bài",
    isResumable: true,
  });

  assert.deepEqual(getAttemptStatusMeta("SUBMITTED"), {
    code: "SUBMITTED",
    label: "Đã nộp",
    tone: "submitted",
    actionLabel: "Xem lại lời giải",
    isResumable: false,
  });

  assert.deepEqual(getAttemptStatusMeta("EVALUATED"), {
    code: "EVALUATED",
    label: "Đã đánh giá",
    tone: "evaluated",
    actionLabel: "Xem kết quả",
    isResumable: false,
  });

  assert.deepEqual(getAttemptStatusMeta("ABANDONED"), {
    code: "ABANDONED",
    label: "Đã khép lại",
    tone: "abandoned",
    actionLabel: "Xem bản lưu",
    isResumable: false,
  });

  const unknown = getAttemptStatusMeta("FUTURE_STATE");
  assert.equal(unknown.label, "Trạng thái: FUTURE_STATE");
  assert.equal(unknown.isResumable, false);
});

test("toAttemptCardViewModel derives truthful date-based labels without inventing problem titles", () => {
  const attempt: SolutionAttemptRead = {
    id: "8a3f1200-1111-4222-8333-444455556666",
    question_id: "q-001",
    status: "IN_PROGRESS",
    context_type: "SELF_PRACTICE",
    current_revision: 3,
    created_at: "2026-10-25T13:15:00Z",
    updated_at: "2026-10-25T13:40:00Z",
    steps: [
      {
        id: "s1",
        step_index: 1,
        step_type: "DERIVATIVE_CALCULATION",
        content_latex: "f'(x)=3x^2-3",
        explanation_text: null,
        step_revision_number: 1,
      },
      {
        id: "s2",
        step_index: 2,
        step_type: "ROOT_FINDING",
        content_latex: "x = \\pm 1",
        explanation_text: null,
        step_revision_number: 1,
      },
    ],
  };

  const vm = toAttemptCardViewModel(attempt);
  assert.equal(vm.shortCode, "8A3F1200");
  assert.equal(vm.href, "/student/attempts/8a3f1200-1111-4222-8333-444455556666");
  assert.ok(vm.title.startsWith("Phiên tự luyện · "));
  assert.equal(vm.stepCount, 2);
  assert.equal(vm.stepSummaryLabel, "2 bước lời giải đã lưu");

  const withoutTimestamp: SolutionAttemptRead = {
    id: "ab12cd34-1111-4222-8333-444455556666",
    question_id: null,
    status: "DRAFT",
    context_type: "CLASSROOM_ASSIGNMENT",
    current_revision: 1,
    created_at: "",
  };
  const fallbackVm = toAttemptCardViewModel(withoutTimestamp);
  assert.equal(fallbackVm.title, "Bài tập lớp học #AB12CD34");
  assert.equal(fallbackVm.stepSummaryLabel, "Phiên bản #1");
});

test("selectContinueLearningAttempts prioritizes IN_PROGRESS over DRAFT and deduplicates", () => {
  const items: SolutionAttemptRead[] = [
    {
      id: "sub-1",
      question_id: "q1",
      status: "SUBMITTED",
      current_revision: 4,
      created_at: "2026-10-25T12:00:00Z",
      updated_at: "2026-10-25T12:30:00Z",
    },
    {
      id: "draft-newer",
      question_id: "q2",
      status: "DRAFT",
      current_revision: 1,
      created_at: "2026-10-25T11:00:00Z",
      updated_at: "2026-10-25T11:50:00Z",
    },
    {
      id: "inprog-older",
      question_id: "q3",
      status: "IN_PROGRESS",
      current_revision: 2,
      created_at: "2026-10-25T09:00:00Z",
      updated_at: "2026-10-25T10:30:00Z",
    },
    {
      id: "inprog-newer",
      question_id: "q4",
      status: "IN_PROGRESS",
      current_revision: 3,
      created_at: "2026-10-25T10:00:00Z",
      updated_at: "2026-10-25T11:20:00Z",
    },
    // Duplicate entry from main page pool
    {
      id: "inprog-newer",
      question_id: "q4",
      status: "IN_PROGRESS",
      current_revision: 3,
      created_at: "2026-10-25T10:00:00Z",
      updated_at: "2026-10-25T11:20:00Z",
    },
  ];

  const selected = selectContinueLearningAttempts(items, 3);
  assert.deepEqual(
    selected.map((item) => item.id),
    ["inprog-newer", "inprog-older", "draft-newer"]
  );
});

test("buildPaginationViewModel preserves full backend pagination bounds accurately", () => {
  const pageVm = buildPaginationViewModel({
    items: new Array(12).fill(null).map((_, idx) => ({
      id: `attempt-${idx}`,
      question_id: null,
      status: "SUBMITTED",
      current_revision: 1,
      created_at: "2026-10-20T08:00:00Z",
    })),
    total: 30,
    page: 2,
    size: 12,
    total_pages: 3,
  });

  assert.equal(pageVm.rangeStart, 13);
  assert.equal(pageVm.rangeEnd, 24);
  assert.equal(pageVm.total, 30);
  assert.equal(pageVm.totalPages, 3);
  assert.equal(pageVm.hasPreviousPage, true);
  assert.equal(pageVm.hasNextPage, true);
});

test("filterAndSortAttempts filters only on real fields and sorts accurately", () => {
  const cards = [
    toAttemptCardViewModel({
      id: "aaa11111-0000-0000-0000-000000000001",
      question_id: null,
      status: "DRAFT",
      context_type: "SELF_PRACTICE",
      current_revision: 1,
      created_at: "2026-10-20T08:00:00Z",
      updated_at: "2026-10-24T09:00:00Z",
    }),
    toAttemptCardViewModel({
      id: "bbb22222-0000-0000-0000-000000000002",
      question_id: null,
      status: "SUBMITTED",
      context_type: "CLASSROOM_ASSIGNMENT",
      current_revision: 2,
      created_at: "2026-10-22T08:00:00Z",
      updated_at: "2026-10-22T09:00:00Z",
    }),
  ];

  assert.deepEqual(
    filterAndSortAttempts(cards, "BBB22222", "updated_desc").map((c) => c.shortCode),
    ["BBB22222"]
  );
  assert.deepEqual(
    filterAndSortAttempts(cards, "lớp học", "updated_desc").map((c) => c.shortCode),
    ["BBB22222"]
  );
  assert.deepEqual(
    filterAndSortAttempts(cards, "", "created_desc").map((c) => c.shortCode),
    ["BBB22222", "AAA11111"]
  );
  assert.deepEqual(
    filterAndSortAttempts(cards, "", "created_asc").map((c) => c.shortCode),
    ["AAA11111", "BBB22222"]
  );
});

test("listMathAttempts forwards pagination and status filter query parameters to v2 endpoint", async () => {
  const seenUrls: string[] = [];
  const api = createApiClient({
    baseUrl: "https://api.example.test",
    fetcher: async (input) => {
      const url = new URL(String(input));
      seenUrls.push(`${url.pathname}${url.search}`);
      return Response.json({ items: [], total: 0, page: 2, size: 12, total_pages: 0 });
    },
  });

  await api.listMathAttempts("token-1", { page: 2, size: 12, status: "SUBMITTED" });
  assert.deepEqual(seenUrls, [
    "/api/v2/math-solutions/attempts?page=2&size=12&status=SUBMITTED",
  ]);

  assert.equal(parseAttemptsPageParam("3"), 3);
  assert.equal(parseAttemptsPageParam("-5"), 1);
  assert.equal(parseAttemptsStatusParam("submitted"), "SUBMITTED");
  assert.equal(parseAttemptsStatusParam("invalid"), "ALL");

  const fullVm = toStudentAttemptsViewModel({
    displayName: "Minh Anh",
    subjects: [{ id: "math-12", name: "Toán 12" }],
    subjectsLoaded: true,
    activeStatusFilter: "ALL",
    attemptsPage: { items: [], total: 0, page: 1, size: 12, total_pages: 0 },
    inProgressPage: { items: [], total: 0, page: 1, size: 4, total_pages: 0 },
    draftPage: { items: [], total: 0, page: 1, size: 4, total_pages: 0 },
  });
  assert.equal(fullVm.student.displayName, "Minh Anh");
  assert.equal(fullVm.totalActiveCount, 0);
});
