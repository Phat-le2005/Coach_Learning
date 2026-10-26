"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const strict_1 = __importDefault(require("node:assert/strict"));
const handwritten_ocr_js_1 = require("../src/features/math-workspace/utils/handwritten-ocr.js");
const makeStroke = (tool, x, y) => ({
    id: tool + x,
    tool,
    color: "#000000",
    width: 2,
    points: [{ x, y, pressure: 0.5 }],
});
(0, node_test_1.default)("CoMER input preserves pen order and page geometry without question hints", () => {
    const result = (0, handwritten_ocr_js_1.toModelStrokes)([
        makeStroke("HIGHLIGHTER", 0.1, 0.2),
        makeStroke("PEN", 0.25, 0.5),
        makeStroke("PEN", 0.75, 1.2),
    ]);
    strict_1.default.equal(result.length, 2);
    strict_1.default.deepEqual(result.map((stroke) => stroke.points[0]), [
        { x: 198.5, y: 561.5 },
        { x: 595.5, y: 1123 },
    ]);
    strict_1.default.deepEqual(result.map((stroke) => stroke.lineWidth), [3, 3]);
});
(0, node_test_1.default)("empty ink abstains without loading model or inventing a formula", async () => {
    await strict_1.default.rejects((0, handwritten_ocr_js_1.recognizeHandwrittenMath)([]), /OCR_NOT_RECOGNIZED/);
});
