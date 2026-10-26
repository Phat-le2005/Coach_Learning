"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const strict_1 = __importDefault(require("node:assert/strict"));
const contracts_js_1 = require("../src/lib/api/contracts.js");
const validation_js_1 = require("../src/lib/api/validation.js");
(0, node_test_1.default)("attempt history validates real paginated records", () => {
    const result = (0, contracts_js_1.parseMathAttemptsPageRead)({
        items: [{ id: "attempt-1", question_id: "question-1", status: "DRAFT", attempt_revision_number: 1, started_at: "2026-10-19T00:00:00Z" }],
        total: 1, page: 1, size: 20, total_pages: 1,
    });
    strict_1.default.equal(result.items[0].id, "attempt-1");
    strict_1.default.throws(() => (0, contracts_js_1.parseMathAttemptsPageRead)({ items: [{ id: "attempt-1" }], total: 1, page: 1, size: 20, total_pages: 1 }), validation_js_1.ApiContractError);
});
(0, node_test_1.default)("practice session start validates its real identifiers", () => {
    strict_1.default.deepEqual((0, contracts_js_1.parsePracticeSessionStartRead)({ id: "session-1", subject_id: "subject-1" }), { id: "session-1", subject_id: "subject-1" });
    strict_1.default.throws(() => (0, contracts_js_1.parsePracticeSessionStartRead)({ id: "session-1" }), validation_js_1.ApiContractError);
});
(0, node_test_1.default)("parseInkPoint parses valid point with default pressure", () => {
    const result = (0, contracts_js_1.parseInkPoint)({ x: 0.25, y: 0.75 });
    strict_1.default.equal(result.x, 0.25);
    strict_1.default.equal(result.y, 0.75);
    strict_1.default.equal(result.pressure, 0.5);
});
(0, node_test_1.default)("parseInkPoint parses explicit pressure", () => {
    const result = (0, contracts_js_1.parseInkPoint)({ x: 0.1, y: 0.9, pressure: 0.8 });
    strict_1.default.equal(result.pressure, 0.8);
});
(0, node_test_1.default)("parseInkPoint rejects non-numeric coords", () => {
    strict_1.default.throws(() => (0, contracts_js_1.parseInkPoint)({ x: "invalid", y: 0.5 }), validation_js_1.ApiContractError);
});
(0, node_test_1.default)("parseInkStroke parses valid pen stroke", () => {
    const input = {
        id: "a0000000-0000-0000-0000-000000000001",
        tool: "PEN",
        color: "#0f172a",
        width: 2.5,
        points: [{ x: 0.1, y: 0.1 }, { x: 0.2, y: 0.2 }],
    };
    const result = (0, contracts_js_1.parseInkStroke)(input);
    strict_1.default.equal(result.id, "a0000000-0000-0000-0000-000000000001");
    strict_1.default.equal(result.tool, "PEN");
    strict_1.default.equal(result.color, "#0f172a");
    strict_1.default.equal(result.width, 2.5);
    strict_1.default.equal(result.points.length, 2);
});
(0, node_test_1.default)("parseInkStroke parses highlighter stroke", () => {
    const input = {
        id: "b0000000-0000-0000-0000-000000000002",
        tool: "HIGHLIGHTER",
        color: "#facc15",
        width: 18,
        points: [{ x: 0.5, y: 0.5 }],
    };
    const result = (0, contracts_js_1.parseInkStroke)(input);
    strict_1.default.equal(result.tool, "HIGHLIGHTER");
});
(0, node_test_1.default)("parseInkStroke rejects invalid tool", () => {
    const input = {
        id: "c0000000-0000-0000-0000-000000000003",
        tool: "CRAYON",
        color: "#000000",
        width: 2,
        points: [{ x: 0, y: 0 }],
    };
    strict_1.default.throws(() => (0, contracts_js_1.parseInkStroke)(input), validation_js_1.ApiContractError);
});
(0, node_test_1.default)("parseInkDocumentRead parses document revision and pages summary", () => {
    const input = {
        document_revision: 3,
        pages: [
            {
                page_index: 0,
                stroke_count: 5,
                point_count: 120,
                sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            },
        ],
    };
    const result = (0, contracts_js_1.parseInkDocumentRead)(input);
    strict_1.default.equal(result.document_revision, 3);
    strict_1.default.equal(result.pages.length, 1);
    strict_1.default.equal(result.pages[0].page_index, 0);
    strict_1.default.equal(result.pages[0].stroke_count, 5);
});
(0, node_test_1.default)("parseInkPageRead parses strokes for a specific page", () => {
    const input = {
        document_revision: 2,
        page_index: 1,
        strokes: [
            {
                id: "d0000000-0000-0000-0000-000000000004",
                tool: "PEN",
                color: "#2563eb",
                width: 3,
                points: [{ x: 0.3, y: 0.4 }],
            },
        ],
    };
    const result = (0, contracts_js_1.parseInkPageRead)(input);
    strict_1.default.equal(result.document_revision, 2);
    strict_1.default.equal(result.page_index, 1);
    strict_1.default.equal(result.strokes.length, 1);
});
(0, node_test_1.default)("parseInkSaveRead parses save response with updated revision", () => {
    const input = {
        document_revision: 4,
        page_index: 0,
        sha256: "abc123sha256",
    };
    const result = (0, contracts_js_1.parseInkSaveRead)(input);
    strict_1.default.equal(result.document_revision, 4);
    strict_1.default.equal(result.page_index, 0);
    strict_1.default.equal(result.sha256, "abc123sha256");
});
(0, node_test_1.default)("parseProblemRead parses question content and options", () => {
    const input = {
        id: "e0000000-0000-0000-0000-000000000005",
        content: "Tìm nguyên hàm của f(x) = 2x",
        question_type: "MULTIPLE_CHOICE",
        options: [
            { id: "opt-1", label: "A", content: "F(x) = x^2 + C", order_index: 1 },
            { id: "opt-2", label: "B", content: "F(x) = 2x^2 + C", order_index: 2 },
        ],
    };
    const result = (0, contracts_js_1.parseProblemRead)(input);
    strict_1.default.equal(result.id, "e0000000-0000-0000-0000-000000000005");
    strict_1.default.equal(result.question_type, "MULTIPLE_CHOICE");
    strict_1.default.equal(result.options.length, 2);
    strict_1.default.equal(result.options[0].label, "A");
});
(0, node_test_1.default)("parseSolutionAttemptRead parses attempt status and revision", () => {
    const input = {
        id: "f0000000-0000-0000-0000-000000000006",
        student_id: "s0000000-0000-0000-0000-000000000001",
        question_id: "q0000000-0000-0000-0000-000000000001",
        status: "IN_PROGRESS",
        current_revision: 1,
        created_at: "2026-10-14T10:00:00Z",
        updated_at: "2026-10-14T10:05:00Z",
    };
    const result = (0, contracts_js_1.parseSolutionAttemptRead)(input);
    strict_1.default.equal(result.id, "f0000000-0000-0000-0000-000000000006");
    strict_1.default.equal(result.status, "IN_PROGRESS");
    strict_1.default.equal(result.current_revision, 1);
});
(0, node_test_1.default)("attempt snapshot retains ordered confirmed steps and rejects malformed step data", () => {
    var _a, _b;
    const base = {
        id: "attempt-1", question_id: "question-1", status: "IN_PROGRESS",
        attempt_revision_number: 3, started_at: "2026-10-23T00:00:00Z",
    };
    const step = {
        id: "step-1", step_index: 1, step_type: "EXPLANATION",
        content_latex: "y=x^2", explanation_text: null, step_revision_number: 1,
    };
    const parsed = (0, contracts_js_1.parseSolutionAttemptRead)(Object.assign(Object.assign({}, base), { steps: [step] }));
    strict_1.default.equal((_a = parsed.steps) === null || _a === void 0 ? void 0 : _a[0].content_latex, "y=x^2");
    strict_1.default.equal((_b = parsed.steps) === null || _b === void 0 ? void 0 : _b[0].step_index, 1);
    strict_1.default.throws(() => (0, contracts_js_1.parseSolutionAttemptRead)(Object.assign(Object.assign({}, base), { steps: [Object.assign(Object.assign({}, step), { step_type: "UNKNOWN" })] })), validation_js_1.ApiContractError);
});
(0, node_test_1.default)("parseSolutionAttemptRead parses attempt_revision_number from v2 contract", () => {
    const input = {
        id: "f0000000-0000-0000-0000-000000000007",
        question_id: "q0000000-0000-0000-0000-000000000001",
        status: "IN_PROGRESS",
        attempt_revision_number: 5,
        started_at: "2026-10-14T10:00:00Z",
    };
    const result = (0, contracts_js_1.parseSolutionAttemptRead)(input);
    strict_1.default.equal(result.id, "f0000000-0000-0000-0000-000000000007");
    strict_1.default.equal(result.current_revision, 5);
});
(0, node_test_1.default)("parseOCRRecognizeResponse parses valid recognition output", () => {
    const input = {
        latex: "\\int (3x^2 - 2x + 1) dx = x^3 - x^2 + x + C",
        confidence: 0.96,
        suggested_step_type: "EXPLANATION",
        explanation_text: "Từng bước tính nguyên hàm.",
        detected_symbols: ["\\int", "3x^2", "dx"],
    };
    const result = (0, contracts_js_1.parseOCRRecognizeResponse)(input);
    strict_1.default.equal(result.latex, "\\int (3x^2 - 2x + 1) dx = x^3 - x^2 + x + C");
    strict_1.default.equal(result.confidence, 0.96);
    strict_1.default.equal(result.suggested_step_type, "EXPLANATION");
    strict_1.default.equal(result.explanation_text, "Từng bước tính nguyên hàm.");
    strict_1.default.deepEqual(result.detected_symbols, ["\\int", "3x^2", "dx"]);
    strict_1.default.deepEqual(result.alternative_latex, []);
});
(0, node_test_1.default)("parseOCRRecognizeResponse keeps optional student-reviewed alternatives typed", () => {
    const input = {
        latex: "x^2",
        confidence: 0,
        suggested_step_type: "EXPLANATION",
        explanation_text: null,
        detected_symbols: [],
        alternative_latex: ["x^{2}", String.raw `\chi^2`],
    };
    strict_1.default.deepEqual((0, contracts_js_1.parseOCRRecognizeResponse)(input).alternative_latex, input.alternative_latex);
    strict_1.default.throws(() => (0, contracts_js_1.parseOCRRecognizeResponse)(Object.assign(Object.assign({}, input), { alternative_latex: [42] })));
});
