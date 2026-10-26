"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const strict_1 = __importDefault(require("node:assert/strict"));
const ocr_sync_js_1 = require("../src/features/math-workspace/utils/ocr-sync.js");
(0, node_test_1.default)("OCR skips flush when ink already matches server", async () => {
    let saves = 0;
    const ok = await (0, ocr_sync_js_1.ensureLatestInkSaved)(false, async () => {
        saves += 1;
        return true;
    });
    strict_1.default.equal(ok, true);
    strict_1.default.equal(saves, 0);
});
(0, node_test_1.default)("OCR proceeds only after an unsaved page is persisted", async () => {
    let saves = 0;
    const ok = await (0, ocr_sync_js_1.ensureLatestInkSaved)(true, async () => {
        saves += 1;
        return true;
    });
    strict_1.default.equal(ok, true);
    strict_1.default.equal(saves, 1);
});
(0, node_test_1.default)("OCR must not proceed if save failed or has revision conflict", async () => {
    for (const result of [false]) {
        let saves = 0;
        const ok = await (0, ocr_sync_js_1.ensureLatestInkSaved)(true, async () => {
            saves += 1;
            return result;
        });
        strict_1.default.equal(ok, false);
        strict_1.default.equal(saves, 1);
    }
});
(0, node_test_1.default)("OCR does not swallow storage or network failures", async () => {
    await strict_1.default.rejects((0, ocr_sync_js_1.ensureLatestInkSaved)(true, async () => {
        throw new Error("local draft unavailable");
    }), /local draft unavailable/);
});
