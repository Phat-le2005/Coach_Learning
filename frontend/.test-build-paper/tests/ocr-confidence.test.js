"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const strict_1 = __importDefault(require("node:assert/strict"));
const ocr_confidence_js_1 = require("../src/features/math-workspace/utils/ocr-confidence.js");
(0, node_test_1.default)("uncalibrated OCR confidence must never be shown as 0 percent correct", () => {
    strict_1.default.deepEqual((0, ocr_confidence_js_1.getOcrConfidenceDisplay)(0), {
        label: "Chưa có điểm tin cậy", known: false, percent: null,
    });
});
(0, node_test_1.default)("positive calibrated scores have explicit reference-only label", () => {
    const actual = (0, ocr_confidence_js_1.getOcrConfidenceDisplay)(0.856);
    strict_1.default.equal(actual.known, true);
    strict_1.default.equal(actual.percent, 86);
    strict_1.default.match(actual.label, /86%/);
    strict_1.default.match(actual.label, /tham khảo/);
});
(0, node_test_1.default)("invalid confidence is always treated as unknown", () => {
    for (const value of [-0.5, Number.NaN, Infinity]) {
        strict_1.default.equal((0, ocr_confidence_js_1.getOcrConfidenceDisplay)(value).known, false);
    }
});
