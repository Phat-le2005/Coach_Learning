"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const strict_1 = __importDefault(require("node:assert/strict"));
const ocr_ink_js_1 = require("../src/features/math-workspace/utils/ocr-ink.js");
(0, node_test_1.default)("OCR sends only nonempty pen strokes, preserving original IDs and order", () => {
    const stroke = (id, tool, points) => ({
        id, tool, color: "#000000", width: 2, points,
    });
    const points = [{ x: 0.1, y: 0.2, pressure: 0.5 }];
    const selected = (0, ocr_ink_js_1.getOcrPenStrokes)([
        stroke("highlight", "HIGHLIGHTER", points),
        stroke("first", "PEN", points),
        stroke("empty", "PEN", []),
        stroke("second", "PEN", points),
    ]);
    strict_1.default.deepEqual(selected.map((item) => item.id), ["first", "second"]);
});
