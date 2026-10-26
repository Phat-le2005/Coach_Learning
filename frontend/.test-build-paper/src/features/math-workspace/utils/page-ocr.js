"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.segmentPageInk = segmentPageInk;
exports.mergePageOcrRegions = mergePageOcrRegions;
exports.splitPageOcrRegion = splitPageOcrRegion;
const ocr_ink_1 = require("./ocr-ink");
function strokeBounds(stroke) {
    const xs = stroke.points.map((point) => point.x);
    const ys = stroke.points.map((point) => point.y);
    return { left: Math.min(...xs), top: Math.min(...ys), right: Math.max(...xs), bottom: Math.max(...ys) };
}
function region(id, strokes) {
    const boxes = strokes.map(strokeBounds);
    return { id, strokes, bounds: {
            left: Math.min(...boxes.map((box) => box.left)),
            top: Math.min(...boxes.map((box) => box.top)),
            right: Math.max(...boxes.map((box) => box.right)),
            bottom: Math.max(...boxes.map((box) => box.bottom)),
        } };
}
/** Visual rows are suggestions; the student may merge or split them before saving. */
function segmentPageInk(strokes) {
    const pen = (0, ocr_ink_1.getOcrPenStrokes)(strokes);
    if (!pen.length)
        return [];
    const entries = pen.map((stroke, originalIndex) => {
        const bounds = strokeBounds(stroke);
        return { stroke, bounds, originalIndex, center: (bounds.top + bounds.bottom) / 2 };
    });
    const heights = entries.map((entry) => entry.bounds.bottom - entry.bounds.top).filter((height) => height > 0).sort((a, b) => a - b);
    const medianHeight = heights.length ? heights[Math.floor(heights.length / 2)] : 0;
    const tolerance = Math.max(0.018, Math.min(0.04, medianHeight * 1.4));
    const rows = [];
    for (const entry of [...entries].sort((a, b) => a.center - b.center || a.bounds.left - b.bounds.left || a.originalIndex - b.originalIndex)) {
        const matching = rows
            .map((items, index) => ({ index, distance: Math.abs(entry.center - items.reduce((sum, item) => sum + item.center, 0) / items.length) }))
            .filter((item) => item.distance <= tolerance)
            .sort((a, b) => a.distance - b.distance || a.index - b.index)[0];
        if (matching)
            rows[matching.index].push(entry);
        else
            rows.push([entry]);
    }
    return rows
        .map((items) => items.sort((a, b) => a.originalIndex - b.originalIndex))
        .sort((a, b) => Math.min(...a.map((item) => item.center)) - Math.min(...b.map((item) => item.center)))
        .map((items) => region(items[0].stroke.id, items.map((item) => item.stroke)));
}
/** Merge neighbors and restore the original pen stroke order. */
function mergePageOcrRegions(regions, index, pageStrokes) {
    if (index < 0 || index >= regions.length - 1)
        return regions;
    const ids = new Set([...regions[index].strokes, ...regions[index + 1].strokes].map((stroke) => stroke.id));
    const merged = region(regions[index].id, (0, ocr_ink_1.getOcrPenStrokes)(pageStrokes).filter((stroke) => ids.has(stroke.id)));
    return [...regions.slice(0, index), merged, ...regions.slice(index + 2)];
}
/** Explicit cut: stacked formulae and tall symbols cannot be split reliably by line spacing. */
function splitPageOcrRegion(regions, index, cutY) {
    const selected = regions[index];
    if (!selected || !Number.isFinite(cutY))
        return regions;
    const upper = selected.strokes.filter((stroke) => {
        const box = strokeBounds(stroke);
        return (box.top + box.bottom) / 2 < cutY;
    });
    const upperIds = new Set(upper.map((stroke) => stroke.id));
    const lower = selected.strokes.filter((stroke) => !upperIds.has(stroke.id));
    if (!upper.length || !lower.length)
        return regions;
    return [...regions.slice(0, index), region(selected.id + ":a", upper), region(selected.id + ":b", lower), ...regions.slice(index + 1)];
}
