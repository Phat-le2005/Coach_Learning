"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createVariationTableDraft = createVariationTableDraft;
exports.trendForSign = trendForSign;
exports.addVariationPoint = addVariationPoint;
exports.removeVariationPoint = removeVariationPoint;
exports.validateVariationTable = validateVariationTable;
exports.toVariationTablePayload = toVariationTablePayload;
const blankPoint = () => ({ x: "", derivative: "", y: "" });
const blankInterval = () => ({ sign: "", trend: "UNKNOWN" });
function createVariationTableDraft() {
    return { points: [blankPoint(), blankPoint(), blankPoint()],
        intervals: [blankInterval(), blankInterval()] };
}
function trendForSign(sign) {
    return sign === "+" ? "UP" : sign === "-" ? "DOWN" : sign === "0" ? "FLAT" : "UNKNOWN";
}
function addVariationPoint(draft) {
    if (draft.points.length >= 12)
        return draft;
    return {
        points: [...draft.points.slice(0, -1), blankPoint(), draft.points[draft.points.length - 1]],
        intervals: [...draft.intervals.slice(0, -1), blankInterval(), blankInterval()],
    };
}
function removeVariationPoint(draft) {
    if (draft.points.length <= 2)
        return draft;
    return {
        points: [...draft.points.slice(0, -2), draft.points[draft.points.length - 1]],
        intervals: [...draft.intervals.slice(0, -2), blankInterval()],
    };
}
function validateVariationTable(draft) {
    if (draft.points.length < 2 || draft.points.length > 12 || draft.intervals.length !== draft.points.length - 1) {
        return "TABLE_COLUMNS_INVALID";
    }
    const xs = draft.points.map((point) => point.x.trim());
    if (xs.some((value) => !value || value.length > 80) || new Set(xs).size !== xs.length) {
        return "TABLE_X_REQUIRED_OR_DUPLICATE";
    }
    if (draft.points.some((point) => point.y.length > 80))
        return "TABLE_VALUE_TOO_LONG";
    if (draft.intervals.some((interval) => !interval.sign || interval.trend !== trendForSign(interval.sign))) {
        return "TABLE_SIGNS_REQUIRED";
    }
    return null;
}
function toVariationTablePayload(draft) {
    const error = validateVariationTable(draft);
    if (error)
        throw new Error(error);
    return {
        version: 1,
        points: draft.points.map((point) => ({ x: point.x.trim(), derivative: point.derivative, y: point.y.trim() })),
        intervals: draft.intervals.map((interval) => ({
            sign: interval.sign, trend: trendForSign(interval.sign),
        })),
    };
}
