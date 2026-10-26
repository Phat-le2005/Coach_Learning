"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const adapter_js_1 = require("../src/features/student-attempts/adapter.js");
const client_js_1 = require("../src/lib/api/client.js");
(0, node_test_1.default)("getAttemptStatusMeta localizes all backend SolutionAttemptStatus values in Vietnamese", () => {
    strict_1.default.deepEqual((0, adapter_js_1.getAttemptStatusMeta)("DRAFT"), {
        code: "DRAFT",
        label: "Bản nháp",
        tone: "draft",
        actionLabel: "Mở bản nháp",
        isResumable: true,
    });
    strict_1.default.deepEqual((0, adapter_js_1.getAttemptStatusMeta)("IN_PROGRESS"), {
        code: "IN_PROGRESS",
        label: "Đang thực hiện",
        tone: "inProgress",
        actionLabel: "Tiếp tục làm bài",
        isResumable: true,
    });
    strict_1.default.deepEqual((0, adapter_js_1.getAttemptStatusMeta)("SUBMITTED"), {
        code: "SUBMITTED",
        label: "Đã nộp",
        tone: "submitted",
        actionLabel: "Xem lại lời giải",
        isResumable: false,
    });
    strict_1.default.deepEqual((0, adapter_js_1.getAttemptStatusMeta)("EVALUATED"), {
        code: "EVALUATED",
        label: "Đã đánh giá",
        tone: "evaluated",
        actionLabel: "Xem kết quả",
        isResumable: false,
    });
    strict_1.default.deepEqual((0, adapter_js_1.getAttemptStatusMeta)("ABANDONED"), {
        code: "ABANDONED",
        label: "Đã khép lại",
        tone: "abandoned",
        actionLabel: "Xem bản lưu",
        isResumable: false,
    });
    const unknown = (0, adapter_js_1.getAttemptStatusMeta)("FUTURE_STATE");
    strict_1.default.equal(unknown.label, "Trạng thái: FUTURE_STATE");
    strict_1.default.equal(unknown.isResumable, false);
});
(0, node_test_1.default)("toAttemptCardViewModel derives truthful date-based labels without inventing problem titles", () => {
    const attempt = {
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
    const vm = (0, adapter_js_1.toAttemptCardViewModel)(attempt);
    strict_1.default.equal(vm.shortCode, "8A3F1200");
    strict_1.default.equal(vm.href, "/student/attempts/8a3f1200-1111-4222-8333-444455556666");
    strict_1.default.ok(vm.title.startsWith("Phiên tự luyện · "));
    strict_1.default.equal(vm.stepCount, 2);
    strict_1.default.equal(vm.stepSummaryLabel, "2 bước lời giải đã lưu");
    const withoutTimestamp = {
        id: "ab12cd34-1111-4222-8333-444455556666",
        question_id: null,
        status: "DRAFT",
        context_type: "CLASSROOM_ASSIGNMENT",
        current_revision: 1,
        created_at: "",
    };
    const fallbackVm = (0, adapter_js_1.toAttemptCardViewModel)(withoutTimestamp);
    strict_1.default.equal(fallbackVm.title, "Bài tập lớp học #AB12CD34");
    strict_1.default.equal(fallbackVm.stepSummaryLabel, "Phiên bản #1");
});
(0, node_test_1.default)("selectContinueLearningAttempts prioritizes IN_PROGRESS over DRAFT and deduplicates", () => {
    const items = [
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
    const selected = (0, adapter_js_1.selectContinueLearningAttempts)(items, 3);
    strict_1.default.deepEqual(selected.map((item) => item.id), ["inprog-newer", "inprog-older", "draft-newer"]);
});
(0, node_test_1.default)("buildPaginationViewModel preserves full backend pagination bounds accurately", () => {
    const pageVm = (0, adapter_js_1.buildPaginationViewModel)({
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
    strict_1.default.equal(pageVm.rangeStart, 13);
    strict_1.default.equal(pageVm.rangeEnd, 24);
    strict_1.default.equal(pageVm.total, 30);
    strict_1.default.equal(pageVm.totalPages, 3);
    strict_1.default.equal(pageVm.hasPreviousPage, true);
    strict_1.default.equal(pageVm.hasNextPage, true);
});
(0, node_test_1.default)("filterAndSortAttempts filters only on real fields and sorts accurately", () => {
    const cards = [
        (0, adapter_js_1.toAttemptCardViewModel)({
            id: "aaa11111-0000-0000-0000-000000000001",
            question_id: null,
            status: "DRAFT",
            context_type: "SELF_PRACTICE",
            current_revision: 1,
            created_at: "2026-10-20T08:00:00Z",
            updated_at: "2026-10-24T09:00:00Z",
        }),
        (0, adapter_js_1.toAttemptCardViewModel)({
            id: "bbb22222-0000-0000-0000-000000000002",
            question_id: null,
            status: "SUBMITTED",
            context_type: "CLASSROOM_ASSIGNMENT",
            current_revision: 2,
            created_at: "2026-10-22T08:00:00Z",
            updated_at: "2026-10-22T09:00:00Z",
        }),
    ];
    strict_1.default.deepEqual((0, adapter_js_1.filterAndSortAttempts)(cards, "BBB22222", "updated_desc").map((c) => c.shortCode), ["BBB22222"]);
    strict_1.default.deepEqual((0, adapter_js_1.filterAndSortAttempts)(cards, "lớp học", "updated_desc").map((c) => c.shortCode), ["BBB22222"]);
    strict_1.default.deepEqual((0, adapter_js_1.filterAndSortAttempts)(cards, "", "created_desc").map((c) => c.shortCode), ["BBB22222", "AAA11111"]);
    strict_1.default.deepEqual((0, adapter_js_1.filterAndSortAttempts)(cards, "", "created_asc").map((c) => c.shortCode), ["AAA11111", "BBB22222"]);
});
(0, node_test_1.default)("listMathAttempts forwards pagination and status filter query parameters to v2 endpoint", async () => {
    const seenUrls = [];
    const api = (0, client_js_1.createApiClient)({
        baseUrl: "https://api.example.test",
        fetcher: async (input) => {
            const url = new URL(String(input));
            seenUrls.push(`${url.pathname}${url.search}`);
            return Response.json({ items: [], total: 0, page: 2, size: 12, total_pages: 0 });
        },
    });
    await api.listMathAttempts("token-1", { page: 2, size: 12, status: "SUBMITTED" });
    strict_1.default.deepEqual(seenUrls, [
        "/api/v2/math-solutions/attempts?page=2&size=12&status=SUBMITTED",
    ]);
    strict_1.default.equal((0, adapter_js_1.parseAttemptsPageParam)("3"), 3);
    strict_1.default.equal((0, adapter_js_1.parseAttemptsPageParam)("-5"), 1);
    strict_1.default.equal((0, adapter_js_1.parseAttemptsStatusParam)("submitted"), "SUBMITTED");
    strict_1.default.equal((0, adapter_js_1.parseAttemptsStatusParam)("invalid"), "ALL");
    const fullVm = (0, adapter_js_1.toStudentAttemptsViewModel)({
        displayName: "Minh Anh",
        subjects: [{ id: "math-12", name: "Toán 12" }],
        subjectsLoaded: true,
        activeStatusFilter: "ALL",
        attemptsPage: { items: [], total: 0, page: 1, size: 12, total_pages: 0 },
        inProgressPage: { items: [], total: 0, page: 1, size: 4, total_pages: 0 },
        draftPage: { items: [], total: 0, page: 1, size: 4, total_pages: 0 },
    });
    strict_1.default.equal(fullVm.student.displayName, "Minh Anh");
    strict_1.default.equal(fullVm.totalActiveCount, 0);
});
