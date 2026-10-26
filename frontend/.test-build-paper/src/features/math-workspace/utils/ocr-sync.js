"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ensureLatestInkSaved = ensureLatestInkSaved;
/** Do not recognize stale server ink after an unsuccessful local save. */
async function ensureLatestInkSaved(hasUnsavedInk, flushPage) {
    if (!hasUnsavedInk)
        return true;
    return flushPage();
}
