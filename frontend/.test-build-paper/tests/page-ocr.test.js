"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const strict_1 = __importDefault(require("node:assert/strict"));
const page_ocr_js_1 = require("../src/features/math-workspace/utils/page-ocr.js");
function stroke(id, x, y, height = 0.012, tool = "PEN") {
    return { id, tool, color: "#000", width: 2, points: [
            { x, y, pressure: 0.5 }, { x: x + 0.015, y: y + height, pressure: 0.5 },
        ] };
}
// Page OCR regions are suggested visual rows.
(0, node_test_1.default)('blank page has no regions', () => {
    strict_1.default.deepEqual((0, page_ocr_js_1.segmentPageInk)([]), []);
});
(0, node_test_1.default)('page rows preserve every pen stroke exactly once', () => {
    const ink = [stroke('a', 0.1, 0.1), stroke('h', 0.1, 0.1, 0.01, 'HIGHLIGHTER'),
        stroke('c', 0.1, 0.23), stroke('b', 0.5, 0.105)];
    const regions = (0, page_ocr_js_1.segmentPageInk)(ink);
    strict_1.default.deepEqual(regions.map((item) => item.strokes.map((s) => s.id)), [['a', 'b'], ['c']]);
    strict_1.default.deepEqual((0, page_ocr_js_1.segmentPageInk)(ink), regions);
});
(0, node_test_1.default)('a full page of twenty handwritten lines keeps all regions in visual order', () => {
    const ink = Array.from({ length: 20 }, (_, line) => [
        stroke(`line-${line}-left`, 0.1, 0.03 + line * 0.043),
        stroke(`line-${line}-right`, 0.55, 0.034 + line * 0.043),
    ]).flat();
    const regions = (0, page_ocr_js_1.segmentPageInk)(ink);
    strict_1.default.equal(regions.length, 20);
    strict_1.default.deepEqual(regions.map((item) => item.strokes.length), Array(20).fill(2));
    strict_1.default.deepEqual(new Set(regions.flatMap((item) => item.strokes.map((s) => s.id))).size, 40);
    strict_1.default.ok(regions.every((item, index) => index === 0 || item.bounds.top > regions[index - 1].bounds.top));
});
(0, node_test_1.default)('merge and split preserve every stroke and its page order', () => {
    const ink = [stroke('first', 0.1, 0.1), stroke('second', 0.3, 0.15), stroke('third', 0.1, 0.4)];
    const segmented = (0, page_ocr_js_1.segmentPageInk)(ink);
    const merged = (0, page_ocr_js_1.mergePageOcrRegions)(segmented, 0, ink);
    strict_1.default.deepEqual(merged[0].strokes.map((s) => s.id), ['first', 'second']);
    const restored = (0, page_ocr_js_1.splitPageOcrRegion)(merged, 0, 0.14);
    strict_1.default.deepEqual(restored.flatMap((item) => item.strokes.map((s) => s.id)), ['first', 'second', 'third']);
    strict_1.default.equal((0, page_ocr_js_1.splitPageOcrRegion)(merged, 0, 0), merged);
});
