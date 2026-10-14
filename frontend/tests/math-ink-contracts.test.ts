import test from "node:test";
import assert from "node:assert/strict";

import {
  parseInkPoint,
  parseInkStroke,
  parseInkPageSummary,
  parseInkDocumentRead,
  parseInkPageRead,
  parseInkSaveRead,
  parseProblemOptionRead,
  parseProblemRead,
  parseSolutionAttemptRead,
  parseOCRRecognizeResponse,
} from "../src/lib/api/contracts.js";
import { ApiContractError } from "../src/lib/api/validation.js";

test("parseInkPoint parses valid point with default pressure", () => {
  const result = parseInkPoint({ x: 0.25, y: 0.75 });
  assert.equal(result.x, 0.25);
  assert.equal(result.y, 0.75);
  assert.equal(result.pressure, 0.5);
});

test("parseInkPoint parses explicit pressure", () => {
  const result = parseInkPoint({ x: 0.1, y: 0.9, pressure: 0.8 });
  assert.equal(result.pressure, 0.8);
});

test("parseInkPoint rejects non-numeric coords", () => {
  assert.throws(() => parseInkPoint({ x: "invalid", y: 0.5 }), ApiContractError);
});

test("parseInkStroke parses valid pen stroke", () => {
  const input = {
    id: "a0000000-0000-0000-0000-000000000001",
    tool: "PEN",
    color: "#0f172a",
    width: 2.5,
    points: [{ x: 0.1, y: 0.1 }, { x: 0.2, y: 0.2 }],
  };
  const result = parseInkStroke(input);
  assert.equal(result.id, "a0000000-0000-0000-0000-000000000001");
  assert.equal(result.tool, "PEN");
  assert.equal(result.color, "#0f172a");
  assert.equal(result.width, 2.5);
  assert.equal(result.points.length, 2);
});

test("parseInkStroke parses highlighter stroke", () => {
  const input = {
    id: "b0000000-0000-0000-0000-000000000002",
    tool: "HIGHLIGHTER",
    color: "#facc15",
    width: 18,
    points: [{ x: 0.5, y: 0.5 }],
  };
  const result = parseInkStroke(input);
  assert.equal(result.tool, "HIGHLIGHTER");
});

test("parseInkStroke rejects invalid tool", () => {
  const input = {
    id: "c0000000-0000-0000-0000-000000000003",
    tool: "CRAYON",
    color: "#000000",
    width: 2,
    points: [{ x: 0, y: 0 }],
  };
  assert.throws(() => parseInkStroke(input), ApiContractError);
});

test("parseInkDocumentRead parses document revision and pages summary", () => {
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
  const result = parseInkDocumentRead(input);
  assert.equal(result.document_revision, 3);
  assert.equal(result.pages.length, 1);
  assert.equal(result.pages[0].page_index, 0);
  assert.equal(result.pages[0].stroke_count, 5);
});

test("parseInkPageRead parses strokes for a specific page", () => {
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
  const result = parseInkPageRead(input);
  assert.equal(result.document_revision, 2);
  assert.equal(result.page_index, 1);
  assert.equal(result.strokes.length, 1);
});

test("parseInkSaveRead parses save response with updated revision", () => {
  const input = {
    document_revision: 4,
    page_index: 0,
    sha256: "abc123sha256",
  };
  const result = parseInkSaveRead(input);
  assert.equal(result.document_revision, 4);
  assert.equal(result.page_index, 0);
  assert.equal(result.sha256, "abc123sha256");
});

test("parseProblemRead parses question content and options", () => {
  const input = {
    id: "e0000000-0000-0000-0000-000000000005",
    content: "Tìm nguyên hàm của f(x) = 2x",
    question_type: "MULTIPLE_CHOICE",
    options: [
      { id: "opt-1", label: "A", content: "F(x) = x^2 + C", order_index: 1 },
      { id: "opt-2", label: "B", content: "F(x) = 2x^2 + C", order_index: 2 },
    ],
  };
  const result = parseProblemRead(input);
  assert.equal(result.id, "e0000000-0000-0000-0000-000000000005");
  assert.equal(result.question_type, "MULTIPLE_CHOICE");
  assert.equal(result.options.length, 2);
  assert.equal(result.options[0].label, "A");
});

test("parseSolutionAttemptRead parses attempt status and revision", () => {
  const input = {
    id: "f0000000-0000-0000-0000-000000000006",
    student_id: "s0000000-0000-0000-0000-000000000001",
    question_id: "q0000000-0000-0000-0000-000000000001",
    status: "IN_PROGRESS",
    current_revision: 1,
    created_at: "2026-10-14T10:00:00Z",
    updated_at: "2026-10-14T10:05:00Z",
  };
  const result = parseSolutionAttemptRead(input);
  assert.equal(result.id, "f0000000-0000-0000-0000-000000000006");
  assert.equal(result.status, "IN_PROGRESS");
  assert.equal(result.current_revision, 1);
});

test("parseSolutionAttemptRead parses attempt_revision_number from v2 contract", () => {
  const input = {
    id: "f0000000-0000-0000-0000-000000000007",
    question_id: "q0000000-0000-0000-0000-000000000001",
    status: "IN_PROGRESS",
    attempt_revision_number: 5,
    started_at: "2026-10-14T10:00:00Z",
  };
  const result = parseSolutionAttemptRead(input);
  assert.equal(result.id, "f0000000-0000-0000-0000-000000000007");
  assert.equal(result.current_revision, 5);
});

test("parseOCRRecognizeResponse parses valid recognition output", () => {
  const input = {
    latex: "\\int (3x^2 - 2x + 1) dx = x^3 - x^2 + x + C",
    confidence: 0.96,
    suggested_step_type: "EXPLANATION",
    explanation_text: "Từng bước tính nguyên hàm.",
    detected_symbols: ["\\int", "3x^2", "dx"],
  };
  const result = parseOCRRecognizeResponse(input);
  assert.equal(result.latex, "\\int (3x^2 - 2x + 1) dx = x^3 - x^2 + x + C");
  assert.equal(result.confidence, 0.96);
  assert.equal(result.suggested_step_type, "EXPLANATION");
  assert.equal(result.explanation_text, "Từng bước tính nguyên hàm.");
  assert.deepEqual(result.detected_symbols, ["\\int", "3x^2", "dx"]);
});
