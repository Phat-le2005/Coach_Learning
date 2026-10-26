"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getOcrConfidenceDisplay = getOcrConfidenceDisplay;
function getOcrConfidenceDisplay(confidence) {
    if (!Number.isFinite(confidence) || confidence <= 0) {
        return { label: "Chưa có điểm tin cậy", known: false, percent: null };
    }
    const percentage = Math.round(Math.min(1, confidence) * 100);
    return { label: `${percentage}% tin cậy (tham khảo)`, known: true, percent: percentage };
}
